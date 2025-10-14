"""
Google Gemini Adapter

Google Gemini API integration with massive context windows and free tier.

Key Features:
	- Massive context windows (2M for Pro, 1M for Flash)
	- Free tier available (60 requests/minute)
	- Function calling with function_declaration format
	- Safety settings for content filtering
	- Vision capabilities (image understanding)
	- Multimodal support (text, images, video, audio)

Model Characteristics:
	- gemini-1.5-pro: Best quality, 2M context window
	- gemini-1.5-flash: Fast and efficient, 1M context window
	- gemini-1.5-flash-8b: Fastest and cheapest, 1M context window
	- gemini-1.0-pro: Previous generation, 32K context

Tool Calling Format:
	Gemini uses "function_declaration" format similar to OpenAI but with schema differences.
	Supports parallel function calls (multiple tools in one response).
	
Pricing:
	Very cost-effective compared to Claude/OpenAI, with generous free tier.
"""

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
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


class GeminiAdapter(BaseLLMAdapter):
	"""
	Google Gemini API adapter implementation.
	
	Responsibilities:
		- Convert messages to Gemini format (contents array)
		- Convert tools to function_declaration format
		- Handle streaming responses with text/function_call parts
		- Parse function_call responses
		- Configure safety settings
		- Calculate costs using Gemini pricing
	"""
	
	# Pricing per 1M tokens (USD, as of Oct 2024)
	# Gemini is very cost-effective compared to Claude/OpenAI
	PRICING = {
		"gemini-1.5-pro": {"input": 1.25, "output": 5.00},        # Best quality
		"gemini-1.5-flash": {"input": 0.075, "output": 0.30},     # Fast & efficient
		"gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15}, # Fastest
		"gemini-1.0-pro": {"input": 0.50, "output": 1.50}         # Previous gen
	}
	
	# Max context window tokens per model
	# Gemini has the largest context windows of all major LLMs
	MAX_TOKENS = {
		"gemini-1.5-pro": 2097152,       # 2M tokens (2 million!)
		"gemini-1.5-flash": 1048576,     # 1M tokens
		"gemini-1.5-flash-8b": 1048576,  # 1M tokens
		"gemini-1.0-pro": 32768           # 32K tokens
	}
	
	def __init__(self, api_key: str, model: str, **kwargs):
		"""
		Initialize Gemini adapter with API credentials and configuration.
		
		Gemini Configuration:
		- API key from https://makersuite.google.com/app/apikey (free tier available)
		- Safety settings to filter harmful content (configurable)
		- top_k parameter (unique to Gemini, controls sampling diversity)
		
		Args:
			api_key: Google AI API key
			model: Model name (gemini-1.5-pro, gemini-1.5-flash, gemini-1.5-flash-8b, gemini-1.0-pro)
			**kwargs: Additional configuration (temperature, max_tokens, top_p, top_k)
		"""
		super().__init__(api_key, model, **kwargs)
		
		# Configure Gemini API with key
		genai.configure(api_key=api_key)
		
		# Generation configuration
		self.temperature = kwargs.get("temperature", 0.7)
		self.max_tokens = kwargs.get("max_tokens", 8192)
		self.top_p = kwargs.get("top_p", 0.95)
		self.top_k = kwargs.get("top_k", 40)  # Unique to Gemini
		
		# Safety settings (set to BLOCK_NONE for permissive business use)
		# Can be made stricter if needed: BLOCK_LOW_AND_ABOVE, BLOCK_MEDIUM_AND_ABOVE, BLOCK_ONLY_HIGH
		self.safety_settings = {
			HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
			HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
			HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
			HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
		}
		
		# Initialize GenerativeModel instance
		self.model_instance = genai.GenerativeModel(
			model_name=model,
			safety_settings=self.safety_settings
		)
	
	def _convert_messages_to_gemini(
		self,
		messages: List[LLMMessage],
		system_prompt: Optional[str] = None
	) -> List[Dict[str, str]]:
		"""
		Convert standard LLMMessage format to Gemini message format.
		
		Gemini Format Differences:
		- Uses "contents" array instead of "messages"
		- Assistant role is "model" instead of "assistant"
		- System prompts converted to user/model exchange (no native system role)
		- Tool calls use "function_call" format in parts
		- Tool results use "function_response" format
		
		Gemini Message Format:
			{
				"role": "user",  # or "model"
				"parts": [
					{"text": "content"},
					{"function_call": {"name": "...", "args": {...}}},
					{"function_response": {"name": "...", "response": {...}}}
				]
			}
		
		Args:
			messages: List of LLMMessage objects
			system_prompt: Optional system instructions (converted to user/model exchange)
		
		Returns:
			List of Gemini-formatted message dicts
		"""
		gemini_messages = []
		
		# Convert system prompt to user/model exchange (Gemini doesn't have system role)
		if system_prompt:
			gemini_messages.append({
				"role": "user",
				"parts": [{"text": f"System Instructions: {system_prompt}"}]
			})
			gemini_messages.append({
				"role": "model",
				"parts": [{"text": "Understood. I'll follow these instructions."}]
			})
		
		for msg in messages:
			# Convert role (Gemini uses "model" instead of "assistant")
			if msg.role == "user":
				role = "user"
			elif msg.role == "assistant":
				role = "model"  # Gemini's name for assistant
			elif msg.role == "system":
				# System messages converted to user messages
				role = "user"
			elif msg.role == "tool":
				# Tool results come as user messages
				role = "user"
			else:
				continue
			
			# Build message parts
			if msg.tool_calls:
				# Model message with function calls
				parts = []
				if msg.content:
					parts.append({"text": msg.content})
				
				# Add each tool call as function_call part
				for tool_call in msg.tool_calls:
					parts.append({
						"function_call": {
							"name": tool_call.get("name"),
							"args": tool_call.get("parameters", {})
						}
					})
				
				gemini_messages.append({"role": role, "parts": parts})
			
			elif msg.tool_call_id:
				# Tool result message (function_response format)
				gemini_messages.append({
					"role": role,
					"parts": [{
						"function_response": {
							"name": msg.name or "tool_result",
							"response": {"result": msg.content}
						}
					}]
				})
			
			else:
				# Regular text message
				gemini_messages.append({
					"role": role,
					"parts": [{"text": msg.content}]
				})
		
		return gemini_messages
	
	def _convert_tools_to_gemini(self, tools: List[LLMTool]) -> List[Dict]:
		"""
		Convert MCP tool definitions to Gemini function_declaration format.
		
		Gemini uses function_declaration format similar to OpenAI.
		Each function has name, description, and parameters (JSON Schema).
		
		Gemini Function Format:
			{
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
		
		Args:
			tools: List of LLMTool objects with MCP format
		
		Returns:
			List of Gemini function declarations
		"""
		if not tools:
			return []
		
		gemini_tools = []
		for tool in tools:
			gemini_tools.append({
				"name": tool.name,
				"description": tool.description,
				"parameters": tool.parameters
			})
		
		return gemini_tools
	
	def chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> LLMResponse:
		"""
		Send non-streaming chat request to Gemini API.
		
		Gemini Chat Flow:
		1. Convert messages to Gemini format (user/model roles, parts array)
		2. Start chat with history (all messages except last)
		3. Send last message to generate response
		4. Extract text and function_call parts from response
		5. Calculate tokens and cost
		
		Gemini supports:
		- Massive context windows (up to 2M tokens for Pro)
		- Function calling with parallel execution
		- Safety filtering (configurable)
		- Multimodal inputs (text, images, video, audio)
		
		Args:
			messages: Conversation history
			tools: Available functions (optional)
			system_prompt: System instructions (optional, converted to user/model exchange)
			**kwargs: Override temperature, max_tokens, top_p, top_k
		
		Returns:
			LLMResponse with content, tool_calls, tokens, cost
		
		Raises:
			Various Gemini API exceptions (converted to LLM exceptions)
		"""
		try:
			# Convert to Gemini message format
			gemini_messages = self._convert_messages_to_gemini(messages, system_prompt)
			
			# Build generation configuration
			generation_config = {
				"temperature": kwargs.get("temperature", self.temperature),
				"max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
				"top_p": kwargs.get("top_p", self.top_p),
				"top_k": kwargs.get("top_k", self.top_k)  # Unique to Gemini
			}
			
			# Add function declarations if tools provided
			if tools:
				gemini_tools = self._convert_tools_to_gemini(tools)
				generation_config["tools"] = [{"function_declarations": gemini_tools}]
			
			# Start chat with history (all messages except last)
			chat = self.model_instance.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
			
			# Send last message to generate response
			response = chat.send_message(
				gemini_messages[-1]["parts"],
				generation_config=generation_config,
				safety_settings=self.safety_settings
			)
			
			# Extract content and tool calls from response parts
			content = ""
			tool_calls = []
			
			if response.parts:
				for part in response.parts:
					# Text content part
					if hasattr(part, 'text') and part.text:
						content += part.text
					# Function call part
					elif hasattr(part, 'function_call') and part.function_call:
						tool_calls.append({
							"name": part.function_call.name,
							"parameters": dict(part.function_call.args)
						})
			
			# Extract token usage (Gemini provides exact counts)
			input_tokens = response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0
			output_tokens = response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0
			total_tokens = input_tokens + output_tokens
			
			# Calculate cost using Gemini pricing
			cost = self._calculate_cost(input_tokens, output_tokens)
			
			# Return normalized response
			return LLMResponse(
				content=content,
				model=self.model,
				token_count=total_tokens,
				tool_calls=tool_calls if tool_calls else None,
				finish_reason=str(response.candidates[0].finish_reason) if response.candidates else None,
				cost=cost,
				metadata={
					"input_tokens": input_tokens,
					"output_tokens": output_tokens,
					"safety_ratings": [
						{
							"category": str(rating.category),
							"probability": str(rating.probability)
						}
						for rating in response.candidates[0].safety_ratings
					] if response.candidates and hasattr(response.candidates[0], 'safety_ratings') else []
				}
			)
		
		# Handle Gemini-specific exceptions
		except genai.types.BlockedPromptException as e:
			raise LLMInvalidRequestError(f"Prompt blocked by safety filters: {str(e)}")
		except genai.types.StopCandidateException as e:
			raise LLMInvalidRequestError(f"Response generation stopped: {str(e)}")
		except Exception as e:
			# Parse generic exceptions to determine error type
			error_str = str(e).lower()
			if "api key" in error_str or "authentication" in error_str:
				raise LLMAuthenticationError(f"Gemini authentication failed: {str(e)}")
			elif "quota" in error_str or "rate limit" in error_str:
				raise LLMRateLimitError(f"Gemini rate limit exceeded: {str(e)}")
			elif "connection" in error_str or "network" in error_str:
				raise LLMConnectionError(f"Gemini connection failed: {str(e)}")
			else:
				raise LLMInvalidRequestError(f"Gemini request failed: {str(e)}")
	
	def stream_chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> Generator[Dict[str, Any], None, None]:
		"""
		Send streaming chat request to Gemini API.
		
		Gemini Streaming:
		- Each chunk contains parts (text or function_call)
		- Token usage accumulated in final chunks
		- Similar structure to non-streaming but yields incrementally
		
		Yields:
			Dict events:
				{"type": "content", "content": "text chunk"}
				{"type": "tool_call", "tool_call": {"name": "...", "parameters": {...}}}
				{"type": "done", "tokens": 123, "cost": 0.05}
				{"type": "error", "error": "error message"}
		
		Args:
			messages: Conversation history
			tools: Available functions (optional)
			system_prompt: System instructions (optional)
			**kwargs: Override temperature, max_tokens, top_p, top_k
		"""
		try:
			# Convert to Gemini format
			gemini_messages = self._convert_messages_to_gemini(messages, system_prompt)
			
			# Build generation configuration
			generation_config = {
				"temperature": kwargs.get("temperature", self.temperature),
				"max_output_tokens": kwargs.get("max_tokens", self.max_tokens),
				"top_p": kwargs.get("top_p", self.top_p),
				"top_k": kwargs.get("top_k", self.top_k)
			}
			
			# Add function declarations if tools provided
			if tools:
				gemini_tools = self._convert_tools_to_gemini(tools)
				generation_config["tools"] = [{"function_declarations": gemini_tools}]
			
			# Start chat with history
			chat = self.model_instance.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
			
			# Stream response (stream=True)
			response_stream = chat.send_message(
				gemini_messages[-1]["parts"],
				generation_config=generation_config,
				safety_settings=self.safety_settings,
				stream=True
			)
			
			# Accumulate content and tokens
			accumulated_content = ""
			total_input_tokens = 0
			total_output_tokens = 0
			
			# Process each chunk in stream
			for chunk in response_stream:
				# Extract parts from chunk
				if chunk.parts:
					for part in chunk.parts:
						# Text content part
						if hasattr(part, 'text') and part.text:
							accumulated_content += part.text
							yield {
								"type": "content",
								"content": part.text
							}
						
						# Function call part
						elif hasattr(part, 'function_call') and part.function_call:
							tool_call = {
								"id": f"call_{part.function_call.name}",
								"name": part.function_call.name,
								"arguments": dict(part.function_call.args)
							}
							yield {
								"type": "tool_call",
								"tool": tool_call
							}
				
				# Track token usage (updated in final chunks)
				if hasattr(chunk, 'usage_metadata'):
					total_input_tokens = chunk.usage_metadata.prompt_token_count
					total_output_tokens = chunk.usage_metadata.candidates_token_count
			
			# Calculate final cost
			cost = self._calculate_cost(total_input_tokens, total_output_tokens)
			
			# Yield final completion event
			yield {
				"type": "done",
				"content": accumulated_content,
				"token_count": total_input_tokens + total_output_tokens,
				"cost": cost,
				"metadata": {
					"input_tokens": total_input_tokens,
					"output_tokens": total_output_tokens
				}
			}
		
		# Handle Gemini-specific exceptions
		except genai.types.BlockedPromptException as e:
			yield {
				"type": "error",
				"error": f"Prompt blocked by safety filters: {str(e)}"
			}
		except genai.types.StopCandidateException as e:
			yield {
				"type": "error",
				"error": f"Response generation stopped: {str(e)}"
			}
		except Exception as e:
			# Parse generic exceptions to determine error type
			error_str = str(e).lower()
			if "api key" in error_str or "authentication" in error_str:
				yield {"type": "error", "error": f"Authentication failed: {str(e)}"}
			elif "quota" in error_str or "rate limit" in error_str:
				yield {"type": "error", "error": f"Rate limit exceeded: {str(e)}"}
			else:
				yield {"type": "error", "error": f"Request failed: {str(e)}"}
	
	def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
		"""
		Calculate API cost for request based on Gemini pricing.
		
		Gemini Pricing (per million tokens):
		- Gemini 1.5 Pro: $1.25 input / $5.00 output
		- Gemini 1.5 Flash: $0.075 input / $0.30 output (very cheap!)
		- Gemini 1.5 Flash-8B: $0.0375 input / $0.15 output (cheapest)
		- Gemini 1.0 Pro: $0.50 input / $1.50 output
		
		Gemini is significantly cheaper than Claude/OpenAI, especially Flash models.
		
		Args:
			input_tokens: Number of input tokens
			output_tokens: Number of output tokens
		
		Returns:
			Estimated cost in USD
		"""
		# Get pricing for model (default to free if unknown)
		pricing = self.PRICING.get(self.model, {"input": 0, "output": 0})
		
		# Calculate costs (pricing is per million tokens)
		input_cost = (input_tokens / 1_000_000) * pricing["input"]
		output_cost = (output_tokens / 1_000_000) * pricing["output"]
		
		return input_cost + output_cost
	
	def count_tokens(self, messages: List[LLMMessage]) -> int:
		"""
		Count tokens in messages using Gemini's native tokenizer.
		
		Gemini provides a native count_tokens() method for accurate counting.
		This is more accurate than tiktoken approximations.
		
		Args:
			messages: List of messages to count tokens for
		
		Returns:
			Exact token count
		"""
		try:
			# Convert messages to text for counting
			text = "\n".join([msg.content for msg in messages if msg.content])
			# Use Gemini's native tokenizer
			result = self.model_instance.count_tokens(text)
			return result.total_tokens
		except Exception:
			# Fallback: rough estimation (4 chars per token)
			total_chars = sum(len(msg.content or "") for msg in messages)
			return total_chars // 4
	
	def get_context_window(self) -> int:
		"""
		Get context window size for Gemini model.
		
		Gemini Context Windows (largest of all LLMs):
		- Gemini 1.5 Pro: 2M tokens (2,097,152)
		- Gemini 1.5 Flash: 1M tokens (1,048,576)
		- Gemini 1.5 Flash-8B: 1M tokens
		- Gemini 1.0 Pro: 32K tokens
		
		Returns:
			Maximum context window tokens
		"""
		return self.MAX_TOKENS.get(self.model, 32768)
	
	def format_tool_for_llm(self, tool: Dict) -> Dict:
		"""
		Convert MCP tool format to Gemini function_declaration format.
		
		MCP tools use inputSchema, Gemini uses parameters.
		Both follow JSON Schema but with different structure.
		
		Args:
			tool: MCP tool definition with inputSchema
		
		Returns:
			Gemini function_declaration format
		"""
		return {
			"name": tool.get("name"),
			"description": tool.get("description", ""),
			"parameters": tool.get("inputSchema", tool.get("parameters", {}))
		}
	
	def parse_tool_call(self, response: Any) -> Optional[List[Dict]]:
		"""
		Parse tool calls from Gemini response.
		
		Gemini returns function_call in parts array.
		Extract and normalize to standard format.
		
		Args:
			response: Gemini response object
		
		Returns:
			List of tool calls or None
		"""
		if not response or not hasattr(response, 'parts'):
			return None
		
		tool_calls = []
		for part in response.parts:
			if hasattr(part, 'function_call') and part.function_call:
				tool_calls.append({
					"id": f"call_{part.function_call.name}",
					"name": part.function_call.name,
					"arguments": dict(part.function_call.args)
				})
		
		return tool_calls if tool_calls else None
