"""
Claude Adapter

Anthropic Claude API integration using the official anthropic SDK.

Claude Features:
	- 200K token context window (all models)
	- Native tool calling support
	- Streaming support
	- JSON mode
	- High quality reasoning

Models Supported:
	- claude-3-5-sonnet-20241022: Best overall (balanced speed/quality)
	- claude-3-5-haiku-20241022: Fastest, cheapest
	- claude-3-opus-20240229: Highest quality (expensive)

Tool Calling Format:
	Claude uses "tool_use" format with stop_reason="tool_use"
	Tools defined with input_schema (JSON Schema)
"""

import anthropic
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


class ClaudeAdapter(BaseLLMAdapter):
	"""
	Anthropic Claude API adapter.
	
	Implements BaseLLMAdapter interface for Claude models.
	Uses official anthropic SDK for API calls.
	
	Key Responsibilities:
		- Convert standard LLMMessage to Claude message format
		- Convert MCP tools to Claude tool_use format
		- Handle streaming responses
		- Parse tool calls from responses
		- Estimate costs based on Claude pricing
	"""
	
	# Pricing per 1M tokens (USD) - as of Jan 2024
	# Format: {"model": {"input": cost, "output": cost}}
	PRICING = {
		"claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},  # $3 input, $15 output
		"claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},    # $0.80 input, $4 output
		"claude-3-opus-20240229": {"input": 15.00, "output": 75.00}      # $15 input, $75 output
	}
	
	# Max context window tokens per model
	MAX_TOKENS = {
		"claude-3-5-sonnet-20241022": 200000,  # 200K tokens
		"claude-3-5-haiku-20241022": 200000,   # 200K tokens
		"claude-3-opus-20240229": 200000       # 200K tokens
	}
	
	def __init__(self, api_key: str, model: str, **kwargs):
		"""
		Initialize Claude adapter with API key and configuration.
		
		Args:
			api_key: Anthropic API key (starts with "sk-ant-")
			model: Claude model name (e.g., "claude-3-5-sonnet-20241022")
			**kwargs: Additional configuration:
				- temperature: Randomness (0.0-1.0, default 0.7)
				- max_tokens: Max response length (default 4096)
				- top_p: Nucleus sampling (default 0.9)
		"""
		super().__init__(api_key, model, **kwargs)
		# Initialize Anthropic client with API key
		self.client = anthropic.Anthropic(api_key=api_key)
		# Extract configuration parameters
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
		Send non-streaming chat request to Claude API.
		
		Converts standard format to Claude format, calls API, parses response.
		
		Claude Message Format:
			[
				{"role": "user", "content": "Hello"},
				{"role": "assistant", "content": "Hi!"},
				{"role": "user", "content": "How are you?"}
			]
		
		System prompts are separate from messages in Claude API.
		Tools use input_schema (JSON Schema) format.
		
		Args:
			messages: Conversation history in standard format
			tools: Available tools in standard format
			system_prompt: System instructions (optional)
			**kwargs: Override default parameters (temperature, max_tokens, etc.)
		
		Returns:
			LLMResponse with parsed content and metadata
		
		Raises:
			LLMAuthenticationError: Invalid API key
			LLMRateLimitError: Rate limit exceeded
			LLMInvalidRequestError: Bad request parameters
			LLMConnectionError: Network/API errors
		"""
		try:
			# Convert from standard LLMMessage format to Claude format
			claude_messages = self._convert_messages(messages)
			
			# Build API request parameters
			request_args = {
				"model": self.model,  # e.g., "claude-3-5-sonnet-20241022"
				"max_tokens": kwargs.get("max_tokens", self.max_tokens),
				"messages": claude_messages,
				"temperature": kwargs.get("temperature", self.temperature),
				"top_p": kwargs.get("top_p", self.top_p)
			}
			
			# Add system prompt (separate from messages in Claude)
			if system_prompt:
				request_args["system"] = system_prompt
			
			# Add tools if provided (already in Claude format)
			if tools:
				request_args["tools"] = tools
			
			# Call Claude Messages API
			response = self.client.messages.create(**request_args)
			
			# Parse response and return in standard format
			return self._parse_response(response)
		
		# Handle Claude-specific exceptions and convert to standard errors
		except anthropic.AuthenticationError as e:
			raise LLMAuthenticationError(f"Claude authentication failed: {str(e)}")
		
		except anthropic.RateLimitError as e:
			raise LLMRateLimitError(f"Claude rate limit exceeded: {str(e)}")
		
		except anthropic.BadRequestError as e:
			raise LLMInvalidRequestError(f"Invalid request to Claude: {str(e)}")
		
		except anthropic.APIConnectionError as e:
			raise LLMConnectionError(f"Failed to connect to Claude: {str(e)}")
		
		except Exception as e:
			raise LLMConnectionError(f"Claude API error: {str(e)}")
	
	def stream_chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> Generator[Dict[str, Any], None, None]:
		"""
		Send streaming chat request to Claude API.
		
		Returns generator that yields events as they arrive from Claude.
		Enables real-time UI updates as response generates.
		
		Claude Streaming Events:
			- message_start: Stream beginning with metadata
			- content_block_start: New content block starting
			- content_block_delta: Content chunk (text or tool_use)
			- content_block_stop: Content block complete
			- message_delta: Token usage update
			- message_stop: Stream complete
		
		Args:
			messages: Conversation history
			tools: Available tools
			system_prompt: System instructions
			**kwargs: Override parameters
		
		Yields:
			Dict events:
				{"type": "content", "content": "accumulated", "delta": "new chunk"}
				{"type": "tool_call", "name": "tool", "parameters": {...}}
				{"type": "done", "tokens": 123, "cost": 0.05}
				{"type": "error", "error": "message"}
		"""
		try:
			# Convert to Claude format
			claude_messages = self._convert_messages(messages)
			
			# Build request with stream=True
			request_args = {
				"model": self.model,
				"max_tokens": kwargs.get("max_tokens", self.max_tokens),
				"messages": claude_messages,
				"temperature": kwargs.get("temperature", self.temperature),
				"top_p": kwargs.get("top_p", self.top_p),
				"stream": True  # Enable streaming
			}
			
			# Add system prompt
			if system_prompt:
				request_args["system"] = system_prompt
			
			# Add tools
			if tools:
				request_args["tools"] = tools
			
			# Start streaming
			content_buffer = ""
			tool_calls_buffer = []
			input_tokens = 0
			output_tokens = 0
			
			# Stream using context manager (auto-closes connection)
			with self.client.messages.stream(**request_args) as stream:
				for event in stream:
					# Event: message_start - Stream beginning with usage info
					if event.type == "message_start":
						input_tokens = event.message.usage.input_tokens
					
					# Event: content_block_start - New content block (text or tool_use)
					elif event.type == "content_block_start":
						if event.content_block.type == "tool_use":
							# Tool use block starting - initialize buffer
							tool_calls_buffer.append({
								"id": event.content_block.id,
								"name": event.content_block.name,
								"input": {}
							})
					
					# Event: content_block_delta - Content chunk arriving
					elif event.type == "content_block_delta":
						if event.delta.type == "text_delta":
							# Text content chunk - accumulate and yield
							content_buffer += event.delta.text
							yield {
								"type": "content",
								"content": event.delta.text
							}
						
						elif event.delta.type == "input_json_delta":
							# Tool input JSON chunk - accumulate partial JSON
							if tool_calls_buffer:
								tool_calls_buffer[-1]["input_partial"] = \
									tool_calls_buffer[-1].get("input_partial", "") + event.delta.partial_json
					
					# Event: content_block_stop - Content block complete
					elif event.type == "content_block_stop":
						# If tool call, parse accumulated JSON and yield
						if tool_calls_buffer and "input_partial" in tool_calls_buffer[-1]:
							tool_call = tool_calls_buffer[-1]
							tool_call["input"] = json.loads(tool_call.pop("input_partial"))
							
							yield {
								"type": "tool_call",
								"tool": {
									"id": tool_call["id"],
									"name": tool_call["name"],
									"arguments": tool_call["input"]
								}
							}
					
					# Event: message_delta - Usage update
					elif event.type == "message_delta":
						output_tokens = event.usage.output_tokens
					
					# Event: message_stop - Stream complete
					elif event.type == "message_stop":
						cost = self.estimate_cost(input_tokens, output_tokens)
						
						yield {
							"type": "done",
							"tokens": input_tokens + output_tokens,
							"cost": cost,
							"model": self.model
						}
		
		except anthropic.AuthenticationError as e:
			yield {"type": "error", "error": f"Authentication failed: {str(e)}"}
		
		except anthropic.RateLimitError as e:
			yield {"type": "error", "error": f"Rate limit exceeded: {str(e)}"}
		
		except anthropic.BadRequestError as e:
			yield {"type": "error", "error": f"Invalid request: {str(e)}"}
		
		except anthropic.APIConnectionError as e:
			yield {"type": "error", "error": f"Connection failed: {str(e)}"}
		
		except Exception as e:
			yield {"type": "error", "error": f"Unexpected error: {str(e)}"}
	
	def count_tokens(self, messages: List[LLMMessage]) -> int:
		"""
		Count tokens in messages using tiktoken approximation.
		
		Claude doesn't provide a native tokenizer, so we use GPT-4's tiktoken
		as a close approximation. Token counts are used for:
		- Context window management (200K limit)
		- Cost estimation
		- Rate limiting
		
		Args:
			messages: List of LLMMessage objects to count
		
		Returns:
			Approximate token count
		"""
		try:
			import tiktoken
			
			# Use GPT-4 tokenizer as close approximation to Claude
			enc = tiktoken.encoding_for_model("gpt-4")
			
			total_tokens = 0
			for msg in messages:
				# Add overhead for message structure (role, formatting, etc.)
				total_tokens += 4
				
				# Count content tokens
				if msg.content:
					total_tokens += len(enc.encode(msg.content))
				
				# Count tool call tokens (JSON serialized)
				if msg.tool_calls:
					for tool_call in msg.tool_calls:
						total_tokens += len(enc.encode(json.dumps(tool_call)))
			
			return total_tokens
		
		except ImportError:
			# Fallback: rough estimation (average 4 characters per token)
			total_chars = sum(len(msg.content or "") for msg in messages)
			return total_chars // 4
	
	def format_tool_for_llm(self, tool: Dict) -> Dict:
		"""
		Convert MCP tool definition to Claude tool_use format.
		
		MCP tools use standard JSON Schema for parameters.
		Claude expects tool_use format with input_schema.
		
		Claude Tool Format:
			{
				"name": "get_weather",
				"description": "Get current weather",
				"input_schema": {
					"type": "object",
					"properties": {
						"location": {"type": "string", "description": "City name"}
					},
					"required": ["location"]
				}
			}
		
		Args:
			tool: MCP tool with name, description, inputSchema
		
		Returns:
			Claude-formatted tool definition
		"""
		return {
			"name": tool["name"],
			"description": tool.get("description", ""),
			"input_schema": tool.get("inputSchema", {
				"type": "object",
				"properties": {},
				"required": []
			})
		}
	
	def parse_tool_call(self, response: Any) -> Optional[List[Dict]]:
		"""
		Extract tool calls from Claude API response.
		
		Claude responses contain content blocks, which can be:
		- text blocks: Normal text response
		- tool_use blocks: Tool/function calls with parameters
		
		Each tool_use block contains:
		- id: Unique call identifier
		- name: Tool/function name
		- input: Tool parameters as dict
		
		Args:
			response: Claude API response object
		
		Returns:
			List of tool calls or None if no tools called
		"""
		tool_calls = []
		
		# Iterate through all content blocks
		for block in response.content:
			if block.type == "tool_use":
				tool_calls.append({
					"id": block.id,
					"name": block.name,
					"arguments": block.input
				})
		
		return tool_calls if tool_calls else None
	
	def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
		"""
		Calculate API cost for request based on Claude pricing.
		
		Claude Pricing (per million tokens):
		- Sonnet: $3 input / $15 output
		- Haiku: $0.25 input / $1.25 output
		- Opus: $15 input / $75 output
		
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
		# Get pricing for model (default to Sonnet if unknown)
		pricing = self.PRICING.get(self.model, {"input": 3.0, "output": 15.0})
		
		# Calculate costs (pricing is per million tokens)
		input_cost = (input_tokens / 1_000_000) * pricing["input"]
		output_cost = (output_tokens / 1_000_000) * pricing["output"]
		
		return input_cost + output_cost
	
	def get_max_tokens(self) -> int:
		"""
		Get context window size for Claude model.
		
		All Claude 3 models support 200K token context window.
		Used for context management (truncating old messages when limit approached).
		
		Returns:
			Maximum tokens (200,000 for all Claude 3 models)
		"""
		return self.MAX_TOKENS.get(self.model, 200000)
	
	def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict]:
		"""
		Convert standard LLMMessage format to Claude message format.
		
		Key conversions:
		- System messages: Removed (handled separately in Claude API)
		- Tool calls: Convert to tool_use content blocks
		- Tool results: Convert to tool_result content blocks
		- Content with tools: Use content array instead of string
		
		Claude Message Format:
			Simple: {"role": "user", "content": "text"}
			With tools: {"role": "assistant", "content": [
				{"type": "text", "text": "..."},
				{"type": "tool_use", "id": "...", "name": "...", "input": {...}}
			]}
		
		Args:
			messages: List of LLMMessage objects
		
		Returns:
			List of Claude-formatted message dicts
		"""
		claude_messages = []
		
		for msg in messages:
			if msg.role == "system":
				# System messages handled separately via system parameter
				continue
			
			# Base message structure
			claude_msg = {
				"role": "user" if msg.role == "user" else "assistant",
				"content": msg.content
			}
			
			# Handle tool calls (assistant making tool calls)
			if msg.tool_calls:
				# Content must be array when tools present
				claude_msg["content"] = []
				if msg.content:
					claude_msg["content"].append({
						"type": "text",
						"text": msg.content
					})
				
				# Add each tool call as tool_use block
				for tool_call in msg.tool_calls:
					claude_msg["content"].append({
						"type": "tool_use",
						"id": tool_call.get("id"),
						"name": tool_call["name"],
						"input": tool_call.get("arguments", {})
					})
			
			# Handle tool results (user providing tool execution results)
			if msg.role == "tool":
				# Tool results always come as user messages with tool_result blocks
				claude_msg = {
					"role": "user",
					"content": [{
						"type": "tool_result",
						"tool_use_id": msg.tool_call_id,
						"content": msg.content
					}]
				}
			
			claude_messages.append(claude_msg)
		
		return claude_messages
	
	def _parse_response(self, response: Any) -> LLMResponse:
		"""
		Parse Claude API response into standard LLMResponse format.
		
		Claude responses contain:
		- content: Array of content blocks (text or tool_use)
		- usage: Token counts (input_tokens, output_tokens)
		- model: Model identifier
		- stop_reason: Why generation stopped
		
		This normalizes to standard format for use in router.
		
		Args:
			response: Claude API response object
		
		Returns:
			LLMResponse with normalized content, tokens, cost
		"""
		content = ""
		tool_calls = None
		
		# Iterate through content blocks
		for block in response.content:
			if block.type == "text":
				# Accumulate text content
				content += block.text
			elif block.type == "tool_use":
				# Extract tool call
				if tool_calls is None:
					tool_calls = []
				tool_calls.append({
					"id": block.id,
					"name": block.name,
					"arguments": block.input
				})
		
		# Extract usage statistics from response
		input_tokens = response.usage.input_tokens
		output_tokens = response.usage.output_tokens
		cost = self.estimate_cost(input_tokens, output_tokens)
		
		# Return normalized response
		return LLMResponse(
			content=content,
			model=response.model,
			token_count=input_tokens + output_tokens,
			tool_calls=tool_calls,
			finish_reason=response.stop_reason,
			cost=cost,
			metadata={
				"input_tokens": input_tokens,
				"output_tokens": output_tokens,
				"stop_reason": response.stop_reason
			}
		)
