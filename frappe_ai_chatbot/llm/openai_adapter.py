"""
OpenAI Adapter

OpenAI GPT API integration for GPT-4o, GPT-4 Turbo, and GPT-3.5 models.

Key Features:
	- Large context windows (128K for GPT-4o, 16K for GPT-3.5)
	- Function calling with parallel tool execution support
	- Streaming responses with delta updates
	- JSON mode for structured outputs
	- Vision capabilities (GPT-4o models)

Model Characteristics:
	- gpt-4o: Best overall model, 128K context, vision support
	- gpt-4o-mini: Faster/cheaper version of GPT-4o
	- gpt-4-turbo: Previous generation, still highly capable
	- gpt-3.5-turbo: Fastest and cheapest, good for simple tasks

Tool Calling Format:
	OpenAI uses "function_calling" format with "parameters" instead of "input_schema".
	Functions are defined with JSON Schema for parameters.
	Supports parallel function calls (multiple tools in one response).
"""

from openai import OpenAI, OpenAIError, AuthenticationError, RateLimitError, APIConnectionError
from typing import Dict, List, Optional, Generator, Any
import json

from frappe_ai_chatbot.llm.base_adapter import (
	BaseLLMAdapter,
	LLMMessage,
	LLMResponse,
	LLMTool,
	LLMConnectionError,
	LLMRateLimitError,
	LLMAuthenticationError,
	LLMInvalidRequestError
)


class OpenAIAdapter(BaseLLMAdapter):
	"""
	OpenAI GPT API adapter implementation.
	
	Responsibilities:
		- Convert messages to OpenAI format (all roles in messages array)
		- Convert tools to function_calling format
		- Handle streaming responses with delta updates
		- Parse function_call responses
		- Calculate costs using OpenAI pricing
	"""
	
	# Pricing per 1M tokens (USD, as of Jan 2024)
	# Format: {"model": {"input": price_per_1M_input_tokens, "output": price_per_1M_output_tokens}}
	PRICING = {
		"gpt-4o": {"input": 2.50, "output": 10.00},
		"gpt-4o-mini": {"input": 0.15, "output": 0.60},
		"gpt-4-turbo": {"input": 10.00, "output": 30.00},
		"gpt-3.5-turbo": {"input": 0.50, "output": 1.50}
	}
	
	# Max context window tokens per model
	MAX_TOKENS = {
		"gpt-4o": 128000,         # 128K context
		"gpt-4o-mini": 128000,    # 128K context
		"gpt-4-turbo": 128000,    # 128K context
		"gpt-3.5-turbo": 16385    # 16K context (much smaller)
	}
	
	def __init__(self, api_key: str, model: str, **kwargs):
		"""
		Initialize OpenAI adapter with API credentials and configuration.
		
		Args:
			api_key: OpenAI API key (starts with sk-)
			model: Model name (gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo)
			**kwargs: Additional configuration (temperature, max_tokens, top_p)
		"""
		super().__init__(api_key, model, **kwargs)
		self.client = OpenAI(api_key=api_key)
		self.temperature = kwargs.get("temperature", 0.7)
		self.max_tokens = kwargs.get("max_tokens", 4096)
		self.top_p = kwargs.get("top_p", 0.9)
	
	def chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> LLMResponse:
		"""
		Send non-streaming chat request to OpenAI API.
		
		OpenAI Message Format:
			[
				{"role": "system", "content": "You are a helpful assistant"},
				{"role": "user", "content": "Hello"},
				{"role": "assistant", "content": "Hi!", "tool_calls": [...]},
				{"role": "tool", "tool_call_id": "...", "content": "result"}
			]
		
		Unlike Claude, system prompts are included in messages array (not separate).
		Tools use function_calling format with "parameters" instead of "input_schema".
		Supports parallel tool calls (multiple functions in one response).
		
		Args:
			messages: Conversation history
			tools: Available tools/functions (optional)
			system_prompt: System instructions (optional)
			**kwargs: Override temperature, max_tokens, top_p
		
		Returns:
			LLMResponse with content, tool_calls, tokens, cost
		
		Raises:
			LLMAuthenticationError: Invalid API key
			LLMRateLimitError: Rate limit exceeded
			LLMConnectionError: Network/API errors
			LLMInvalidRequestError: Bad request parameters
		"""
		try:
			# Convert to OpenAI message format (includes system prompt)
			openai_messages = self._convert_messages(messages, system_prompt)
			
			# Build request arguments
			request_args = {
				"model": self.model,
				"messages": openai_messages,
				"temperature": kwargs.get("temperature", self.temperature),
				"max_tokens": kwargs.get("max_tokens", self.max_tokens),
				"top_p": kwargs.get("top_p", self.top_p)
			}
			
			# Add function calling tools if provided
			if tools:
				request_args["tools"] = tools
				request_args["tool_choice"] = "auto"  # Let model decide when to call
			
			# Call OpenAI chat completions API
			response = self.client.chat.completions.create(**request_args)
			
			# Parse and return normalized response
			return self._parse_response(response)
		
		except AuthenticationError as e:
			raise LLMAuthenticationError(f"OpenAI authentication failed: {str(e)}")
		
		except RateLimitError as e:
			raise LLMRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
		
		except APIConnectionError as e:
			raise LLMConnectionError(f"Failed to connect to OpenAI: {str(e)}")
		
		except OpenAIError as e:
			raise LLMInvalidRequestError(f"OpenAI API error: {str(e)}")
		
		except Exception as e:
			raise LLMConnectionError(f"Unexpected error: {str(e)}")
	
	def stream_chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> Generator[Dict[str, Any], None, None]:
		"""
		Send streaming chat request to OpenAI API.
		
		OpenAI Streaming Format:
			Each chunk is a delta update with:
			- delta.content: Text content chunk (if text)
			- delta.tool_calls: Tool call deltas (if function calling)
			- finish_reason: Why stream stopped (stop, tool_calls, length)
		
		Unlike Claude (6 event types), OpenAI uses simple delta updates.
		Tool calls arrive incrementally: id, then name, then arguments JSON.
		
		Yields:
			Dict events:
				{"type": "content", "content": "text chunk"}
				{"type": "tool_call", "tool": {"id": "...", "name": "...", "arguments": {...}}}
				{"type": "done", "tokens": 123, "cost": 0.05}
				{"type": "error", "error": "error message"}
		
		Args:
			messages: Conversation history
			tools: Available tools/functions (optional)
			system_prompt: System instructions (optional)
			**kwargs: Override temperature, max_tokens, top_p
		"""
		try:
			# Convert to OpenAI message format
			openai_messages = self._convert_messages(messages, system_prompt)
			
			# Build request with stream=True
			request_args = {
				"model": self.model,
				"messages": openai_messages,
				"temperature": kwargs.get("temperature", self.temperature),
				"max_tokens": kwargs.get("max_tokens", self.max_tokens),
				"top_p": kwargs.get("top_p", self.top_p),
				"stream": True  # Enable streaming
			}
			
			# Add function calling tools if provided
			if tools:
				request_args["tools"] = tools
				request_args["tool_choice"] = "auto"
			
			# Initialize buffers for accumulating streamed data
			content_buffer = ""
			tool_calls_buffer = {}  # {index: {id, name, arguments}}
			total_tokens = 0
			
			# Start streaming
			stream = self.client.chat.completions.create(**request_args)
			
			# Process each chunk in stream
			for chunk in stream:
				if not chunk.choices:
					continue
				
				choice = chunk.choices[0]
				delta = choice.delta
				
				# Handle text content delta
				if delta.content:
					content_buffer += delta.content
					yield {
						"type": "content",
						"content": delta.content
					}
				
				# Handle tool call deltas (arrive incrementally)
				if delta.tool_calls:
					for tool_call in delta.tool_calls:
						idx = tool_call.index
						
						# Initialize buffer for this tool call index
						if idx not in tool_calls_buffer:
							tool_calls_buffer[idx] = {
								"id": tool_call.id or "",
								"name": "",
								"arguments": ""
							}
						
						# Accumulate function name (usually arrives first)
						if tool_call.function.name:
							tool_calls_buffer[idx]["name"] = tool_call.function.name
						
						# Accumulate function arguments JSON (arrives incrementally)
						if tool_call.function.arguments:
							tool_calls_buffer[idx]["arguments"] += tool_call.function.arguments
				
				# Tool calls complete - parse and yield
				if choice.finish_reason == "tool_calls":
					for tool_call in tool_calls_buffer.values():
						try:
							# Parse accumulated JSON arguments
							arguments = json.loads(tool_call["arguments"])
							yield {
								"type": "tool_call",
								"tool": {
									"id": tool_call["id"],
									"name": tool_call["name"],
									"arguments": arguments
								}
							}
						except json.JSONDecodeError:
							# Malformed JSON in arguments
							yield {
								"type": "error",
								"error": f"Failed to parse tool arguments: {tool_call['arguments']}"
							}
				
				# Stream complete - calculate final stats
				if choice.finish_reason:
					# Estimate tokens (OpenAI doesn't include usage in stream)
					total_tokens = self.count_tokens([
						LLMMessage(role="assistant", content=content_buffer)
					])
					
					# Rough split for input/output (actual split unknown in stream)
					cost = self.estimate_cost(total_tokens // 2, total_tokens // 2)
					
					# Yield final completion event
					yield {
						"type": "done",
						"tokens": total_tokens,
						"cost": cost,
						"model": self.model
					}
		
		except AuthenticationError as e:
			yield {"type": "error", "error": f"Authentication failed: {str(e)}"}
		
		except RateLimitError as e:
			yield {"type": "error", "error": f"Rate limit exceeded: {str(e)}"}
		
		except APIConnectionError as e:
			yield {"type": "error", "error": f"Connection failed: {str(e)}"}
		
		except OpenAIError as e:
			yield {"type": "error", "error": f"API error: {str(e)}"}
		
		except Exception as e:
			yield {"type": "error", "error": f"Unexpected error: {str(e)}"}
	
	def count_tokens(self, messages: List[LLMMessage]) -> int:
		"""
		Count tokens in messages using tiktoken library.
		
		OpenAI provides tiktoken for accurate token counting.
		Uses model-specific encoding or cl100k_base for newer models.
		
		Token count includes:
		- Message overhead (4 tokens per message)
		- Role tokens
		- Content tokens
		- Tool call tokens (JSON serialized)
		- Completion overhead (2 tokens)
		
		Used for:
		- Context window management (128K for GPT-4o, 16K for GPT-3.5)
		- Cost estimation
		- Rate limiting
		
		Args:
			messages: List of LLMMessage objects to count
		
		Returns:
			Token count (or rough estimate if tiktoken unavailable)
		"""
		try:
			import tiktoken
			
			# Get encoding for specific model
			try:
				enc = tiktoken.encoding_for_model(self.model)
			except KeyError:
				# Fallback to cl100k_base for newer models (GPT-4o, etc.)
				enc = tiktoken.get_encoding("cl100k_base")
			
			total_tokens = 0
			
			for msg in messages:
				# Message overhead (OpenAI format)
				total_tokens += 4
				
				# Role tokens
				total_tokens += len(enc.encode(msg.role))
				
				# Content tokens
				if msg.content:
					total_tokens += len(enc.encode(msg.content))
				
				# Tool calls tokens (JSON format)
				if msg.tool_calls:
					for tool_call in msg.tool_calls:
						total_tokens += len(enc.encode(json.dumps(tool_call)))
			
			# Completion overhead
			total_tokens += 2
			
			return total_tokens
		
		except ImportError:
			# Fallback: rough estimation (average 4 characters per token)
			total_chars = sum(len(msg.content or "") for msg in messages)
			return total_chars // 4
	
	def format_tool_for_llm(self, tool: Dict) -> Dict:
		"""
		Convert MCP tool definition to OpenAI function_calling format.
		
		MCP tools use standard JSON Schema for parameters.
		OpenAI expects function_calling format with "parameters" (not "input_schema").
		
		OpenAI Tool Format:
			{
				"type": "function",
				"function": {
					"name": "get_weather",
					"description": "Get current weather",
					"parameters": {
						"type": "object",
						"properties": {
							"location": {"type": "string", "description": "City name"}
						},
						"required": ["location"]
					}
				}
			}
		
		Key difference from Claude: Uses "parameters" instead of "input_schema",
		and wraps in "function" object with "type": "function".
		
		Args:
			tool: MCP tool with name, description, inputSchema
		
		Returns:
			OpenAI-formatted function definition
		"""
		return {
			"type": "function",
			"function": {
				"name": tool["name"],
				"description": tool.get("description", ""),
				"parameters": tool.get("inputSchema", {
					"type": "object",
					"properties": {},
					"required": []
				})
			}
		}
	
	def parse_tool_call(self, response: Any) -> Optional[List[Dict]]:
		"""
		Extract tool calls from OpenAI API response.
		
		OpenAI responses contain:
		- choices[0].message.tool_calls: Array of tool call objects
		- Each tool_call has: id, function.name, function.arguments (JSON string)
		
		OpenAI supports parallel tool calls (multiple functions in one response).
		
		Args:
			response: OpenAI API response object
		
		Returns:
			List of tool calls or None if no tools called
		"""
		if not response.choices:
			return None
		
		choice = response.choices[0]
		message = choice.message
		
		if not message.tool_calls:
			return None
		
		tool_calls = []
		for tool_call in message.tool_calls:
			# Parse JSON arguments string
			tool_calls.append({
				"id": tool_call.id,
				"name": tool_call.function.name,
				"arguments": json.loads(tool_call.function.arguments)
			})
		
		return tool_calls
	
	def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
		"""
		Calculate API cost for request based on OpenAI pricing.
		
		OpenAI Pricing (per million tokens):
		- GPT-4o: $2.50 input / $10.00 output
		- GPT-4o-mini: $0.15 input / $0.60 output
		- GPT-4-turbo: $10.00 input / $30.00 output
		- GPT-3.5-turbo: $0.50 input / $1.50 output
		
		Used for:
		- Cost tracking per conversation
		- Budget alerts
		- Usage analytics
		
		Args:
			input_tokens: Number of input tokens
			output_tokens: Number of output tokens
		
		Returns:
			Estimated cost in USD
		"""
		# Get pricing for model (default to GPT-4o if unknown)
		pricing = self.PRICING.get(self.model, {"input": 2.5, "output": 10.0})
		
		# Calculate costs (pricing is per million tokens)
		input_cost = (input_tokens / 1_000_000) * pricing["input"]
		output_cost = (output_tokens / 1_000_000) * pricing["output"]
		
		return input_cost + output_cost
	
	def get_max_tokens(self) -> int:
		"""
		Get context window size for OpenAI model.
		
		OpenAI Context Windows:
		- GPT-4o: 128K tokens
		- GPT-4o-mini: 128K tokens
		- GPT-4-turbo: 128K tokens
		- GPT-3.5-turbo: 16K tokens (much smaller)
		
		Used for context management (truncating old messages when limit approached).
		
		Returns:
			Maximum tokens (default 16K for GPT-3.5)
		"""
		return self.MAX_TOKENS.get(self.model, 16385)
	
	def _convert_messages(
		self,
		messages: List[LLMMessage],
		system_prompt: Optional[str] = None
	) -> List[Dict]:
		"""
		Convert standard LLMMessage format to OpenAI message format.
		
		Key differences from Claude:
		- System prompt included in messages array (not separate parameter)
		- Tool calls use function format with JSON string arguments (not dict)
		- Tool results use "tool" role with tool_call_id
		
		OpenAI Message Format:
			Simple: {"role": "user", "content": "text"}
			With tools: {"role": "assistant", "content": "...", "tool_calls": [
				{"id": "...", "type": "function", "function": {"name": "...", "arguments": "{...}"}}
			]}
			Tool result: {"role": "tool", "tool_call_id": "...", "content": "result"}
		
		Args:
			messages: List of LLMMessage objects
			system_prompt: Optional system instructions (prepended to messages)
		
		Returns:
			List of OpenAI-formatted message dicts
		"""
		openai_messages = []
		
		# Add system prompt first (OpenAI includes in messages array)
		if system_prompt:
			openai_messages.append({
				"role": "system",
				"content": system_prompt
			})
		
		for msg in messages:
			if msg.role == "tool":
				# Tool result message (sent after tool execution)
				openai_messages.append({
					"role": "tool",
					"tool_call_id": msg.tool_call_id,
					"content": msg.content
				})
			
			elif msg.tool_calls:
				# Assistant message with tool calls
				openai_messages.append({
					"role": "assistant",
					"content": msg.content or None,
					"tool_calls": [
						{
							"id": tc.get("id"),
							"type": "function",
							"function": {
								"name": tc["name"],
								"arguments": json.dumps(tc.get("arguments", {}))  # Must be JSON string
							}
						}
						for tc in msg.tool_calls
					]
				})
			
			else:
				# Regular user/assistant message
				openai_messages.append({
					"role": msg.role,
					"content": msg.content
				})
		
		return openai_messages
	
	def _parse_response(self, response: Any) -> LLMResponse:
		"""
		Parse OpenAI API response into standard LLMResponse format.
		
		OpenAI responses contain:
		- choices[0].message: Content and tool_calls
		- usage: Token counts (prompt_tokens, completion_tokens, total_tokens)
		- model: Model identifier
		- finish_reason: Why generation stopped
		
		Unlike Claude, OpenAI provides exact token usage in non-streaming responses.
		
		Args:
			response: OpenAI API response object
		
		Returns:
			LLMResponse with normalized content, tokens, cost
		"""
		choice = response.choices[0]
		message = choice.message
		
		# Extract content
		content = message.content or ""
		tool_calls = self.parse_tool_call(response)
		
		# Extract token usage (exact counts from OpenAI)
		input_tokens = response.usage.prompt_tokens
		output_tokens = response.usage.completion_tokens
		total_tokens = response.usage.total_tokens
		
		# Calculate cost using exact token counts
		cost = self.estimate_cost(input_tokens, output_tokens)
		
		# Return normalized response
		return LLMResponse(
			content=content,
			model=response.model,
			token_count=total_tokens,
			tool_calls=tool_calls,
			finish_reason=choice.finish_reason,
			cost=cost,
			metadata={
				"input_tokens": input_tokens,
				"output_tokens": output_tokens,
				"finish_reason": choice.finish_reason
			}
		)
