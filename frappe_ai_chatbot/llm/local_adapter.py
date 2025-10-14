"""
Local LLM Adapter

Support for locally hosted LLMs via Ollama, LM Studio, or LocalAI.

Key Features:
	- No API keys required (fully local)
	- Free to use (no per-token costs)
	- Privacy-preserving (data never leaves local machine)
	- Support for open-source models (Llama 3, Mistral, Phi, etc.)
	- HTTP API communication (typically localhost:11434 for Ollama)

Supported Backends:
	- Ollama: Most popular, easiest setup (https://ollama.ai)
	- LM Studio: GUI-based, cross-platform (https://lmstudio.ai)
	- LocalAI: OpenAI-compatible API (https://localai.io)

Model Examples:
	- llama3:8b, llama3:70b (Meta's Llama 3)
	- mistral:7b, mixtral:8x7b (Mistral AI)
	- phi3:mini, phi3:medium (Microsoft Phi)
	- codellama:13b (Code generation)

Limitations:
	- Requires local GPU/CPU resources
	- Slower than cloud APIs (depends on hardware)
	- Tool calling support varies by model
	- No usage analytics or token counting
"""

import httpx
from typing import Dict, List, Optional, Generator, Any
import json

from frappe_ai_chatbot.llm.base_adapter import (
	BaseLLMAdapter,
	LLMMessage,
	LLMResponse,
	LLMTool,
	LLMConnectionError,
	LLMInvalidRequestError
)


class LocalAdapter(BaseLLMAdapter):
	"""
	Local LLM adapter for Ollama, LM Studio, and LocalAI.
	
	Responsibilities:
		- Connect to local HTTP API endpoint (no authentication)
		- Format messages as prompt strings (most local models don't support message format)
		- Parse tool calls from text responses (varies by model)
		- Handle HTTP communication with timeout
		- Provide free, privacy-preserving LLM access
	
	Note: No API key required (api_key=None), no costs, no token tracking.
	"""
	
	def __init__(self, endpoint: str, model: str, **kwargs):
		"""
		Initialize local LLM adapter with endpoint configuration.
		
		Default Endpoints:
		- Ollama: http://localhost:11434
		- LM Studio: http://localhost:1234
		- LocalAI: http://localhost:8080
		
		Args:
			endpoint: Local HTTP API endpoint URL
			model: Model name (llama3, mistral, phi3, etc.)
			**kwargs: Additional configuration (temperature, max_tokens, timeout)
		"""
		super().__init__(api_key=None, model=model, **kwargs)
		self.endpoint = endpoint.rstrip("/")
		self.temperature = kwargs.get("temperature", 0.7)
		self.max_tokens = kwargs.get("max_tokens", 4096)
		self.timeout = kwargs.get("timeout", 120.0)  # Local models can be slow
	
	def chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> LLMResponse:
		"""
		Send non-streaming chat request to local LLM via HTTP API.
		
		Local LLM Communication:
		1. Format messages as single prompt string (most local models don't use message format)
		2. Send HTTP POST to /api/generate endpoint (Ollama format)
		3. Parse text response
		4. Attempt to extract tool calls from text (if tools provided)
		5. Estimate tokens (no accurate counting for local models)
		
		Note:
		- No authentication required
		- No per-token costs
		- Token counting is rough approximation
		- Tool calling support varies by model
		
		Args:
			messages: Conversation history
			tools: Available tools (optional, support varies)
			system_prompt: System instructions (optional)
			**kwargs: Override temperature, max_tokens
		
		Returns:
			LLMResponse with content, estimated tokens, zero cost
		
		Raises:
			LLMConnectionError: Cannot connect to local endpoint
			LLMInvalidRequestError: Request failed
		"""
		try:
			# Format messages as prompt string (local models expect text prompt)
			prompt = self._format_messages(messages, system_prompt, tools)
			
			# Build Ollama-format request
			request_data = {
				"model": self.model,
				"prompt": prompt,
				"stream": False,
				"options": {
					"temperature": kwargs.get("temperature", self.temperature),
					"num_predict": kwargs.get("max_tokens", self.max_tokens)
				}
			}
			
			# Call local API via HTTP
			with httpx.Client(timeout=self.timeout) as client:
				response = client.post(
					f"{self.endpoint}/api/generate",
					json=request_data
				)
				response.raise_for_status()
				result = response.json()
			
			# Extract text content
			content = result.get("response", "")
			
			# Attempt to parse tool calls from text (if tools were provided)
			tool_calls = None
			if tools:
				tool_calls = self._extract_tool_calls(content)
			
			# Estimate tokens (word-based approximation, not accurate)
			token_count = len(content.split()) + len(prompt.split())
			
			# Return response (zero cost for local models)
			return LLMResponse(
				content=content,
				model=self.model,
				token_count=token_count,
				tool_calls=tool_calls,
				finish_reason=result.get("done_reason", "stop"),
				cost=0.0,  # Local LLMs are free
				metadata={
					"total_duration": result.get("total_duration"),
					"load_duration": result.get("load_duration"),
					"eval_count": result.get("eval_count")
				}
			)
		
		# Handle HTTP errors
		except httpx.HTTPStatusError as e:
			raise LLMConnectionError(f"HTTP error from local LLM: {e.response.status_code}")
		
		except httpx.ConnectError:
			raise LLMConnectionError(f"Failed to connect to local LLM at {self.endpoint}")
		
		except httpx.TimeoutException:
			raise LLMConnectionError("Request to local LLM timed out")
		
		except Exception as e:
			raise LLMInvalidRequestError(f"Local LLM error: {str(e)}")
	
	def stream_chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> Generator[Dict[str, Any], None, None]:
		"""
		Send streaming chat request to local LLM via HTTP API.
		
		Local LLM Streaming:
		- Stream=True sends request to /api/generate with streaming enabled
		- Each line contains JSON with incremental response
		- Accumulate text chunks and yield to frontend
		
		Yields:
			Dict events:
				{"type": "content", "content": "text chunk"}
				{"type": "done", "content": "full text", "token_count": 123, "cost": 0.0}
				{"type": "error", "error": "error message"}
		
		Args:
			messages: Conversation history
			tools: Available tools (optional)
			system_prompt: System instructions (optional)
			**kwargs: Override temperature, max_tokens
		"""
		try:
			# Convert messages
			prompt = self._format_messages(messages, system_prompt, tools)
			
			# Prepare request
			request_data = {
				"model": self.model,
				"prompt": prompt,
				"stream": True,
				"options": {
					"temperature": kwargs.get("temperature", self.temperature),
					"num_predict": kwargs.get("max_tokens", self.max_tokens)
				}
			}
			
			# Stream response
			content_buffer = ""
			token_count = 0
			
			with httpx.Client(timeout=self.timeout) as client:
				with client.stream(
					"POST",
					f"{self.endpoint}/api/generate",
					json=request_data
				) as response:
					response.raise_for_status()
					
					for line in response.iter_lines():
						if not line:
							continue
						
						try:
							chunk = json.loads(line)
							
							if "response" in chunk:
								content = chunk["response"]
								content_buffer += content
								token_count += len(content.split())
								
								yield {
									"type": "content",
									"content": content
								}
							
							if chunk.get("done"):
								# Try to extract tool calls from complete response
								if tools:
									tool_calls = self._extract_tool_calls(content_buffer)
									if tool_calls:
										for tool_call in tool_calls:
											yield {
												"type": "tool_call",
												"tool": tool_call
											}
								
								yield {
									"type": "done",
									"tokens": token_count,
									"cost": 0.0,
									"model": self.model
								}
						
						except json.JSONDecodeError:
							continue
		
		except httpx.HTTPStatusError as e:
			yield {"type": "error", "error": f"HTTP error: {e.response.status_code}"}
		
		except httpx.ConnectError as e:
			yield {"type": "error", "error": f"Failed to connect to {self.endpoint}"}
		
		except httpx.TimeoutException as e:
			yield {"type": "error", "error": "Request timed out"}
		
		except Exception as e:
			yield {"type": "error", "error": f"Unexpected error: {str(e)}"}
	
	def count_tokens(self, messages: List[LLMMessage]) -> int:
		"""Estimate token count (rough approximation)"""
		total_words = 0
		
		for msg in messages:
			if msg.content:
				total_words += len(msg.content.split())
			
			if msg.tool_calls:
				for tool_call in msg.tool_calls:
					total_words += len(json.dumps(tool_call).split())
		
		# Rough estimate: 1.3 tokens per word
		return int(total_words * 1.3)
	
	def format_tool_for_llm(self, tool: Dict) -> Dict:
		"""Format tool description for local LLM"""
		# Local LLMs don't have native function calling
		# We return a text description that can be included in prompt
		return {
			"name": tool["name"],
			"description": tool.get("description", ""),
			"parameters": tool.get("inputSchema", {})
		}
	
	def parse_tool_call(self, response: Any) -> Optional[List[Dict]]:
		"""Parse tool calls from response (pattern matching)"""
		# Local LLMs typically don't have structured tool calling
		# This is a best-effort extraction
		return None
	
	def supports_function_calling(self) -> bool:
		"""Local LLMs don't natively support function calling"""
		return False
	
	def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
		"""Local LLMs are free"""
		return 0.0
	
	def validate_config(self) -> bool:
		"""Validate configuration"""
		if not self.endpoint:
			return False
		if not self.model:
			return False
		
		# Try to ping the endpoint
		try:
			with httpx.Client(timeout=5.0) as client:
				response = client.get(f"{self.endpoint}/api/tags")
				return response.status_code == 200
		except:
			return False
	
	def _format_messages(
		self,
		messages: List[LLMMessage],
		system_prompt: Optional[str] = None,
		tools: Optional[List[Dict]] = None
	) -> str:
		"""
		Format messages into a single prompt for local LLM.
		
		Local LLMs typically work with a single prompt string rather than
		structured messages.
		"""
		prompt_parts = []
		
		# Add system prompt
		if system_prompt:
			prompt_parts.append(f"System: {system_prompt}")
		
		# Add tools description if provided
		if tools:
			tools_desc = self._format_tools_description(tools)
			prompt_parts.append(f"\nAvailable Tools:\n{tools_desc}")
		
		# Add conversation messages
		for msg in messages:
			if msg.role == "user":
				prompt_parts.append(f"\nUser: {msg.content}")
			elif msg.role == "assistant":
				prompt_parts.append(f"\nAssistant: {msg.content}")
			elif msg.role == "system":
				prompt_parts.append(f"\nSystem: {msg.content}")
			elif msg.role == "tool":
				prompt_parts.append(f"\nTool Result ({msg.name}): {msg.content}")
		
		# Add assistant prompt
		prompt_parts.append("\nAssistant:")
		
		return "\n".join(prompt_parts)
	
	def _format_tools_description(self, tools: List[Dict]) -> str:
		"""Format tools as text description"""
		descriptions = []
		
		for tool in tools:
			desc = f"- {tool['name']}: {tool.get('description', 'No description')}"
			
			if "parameters" in tool:
				params = tool["parameters"].get("properties", {})
				if params:
					param_list = ", ".join(params.keys())
					desc += f" (parameters: {param_list})"
			
			descriptions.append(desc)
		
		return "\n".join(descriptions)
	
	def _extract_tool_calls(self, content: str) -> Optional[List[Dict]]:
		"""
		Try to extract tool calls from response content.
		
		This looks for patterns like:
		```json
		{"tool": "tool_name", "arguments": {...}}
		```
		
		Or:
		TOOL_CALL: tool_name(arg1="value1", arg2="value2")
		"""
		tool_calls = []
		
		# Try JSON extraction
		try:
			# Look for JSON blocks
			import re
			json_pattern = r'```json\s*(\{.*?\})\s*```'
			matches = re.findall(json_pattern, content, re.DOTALL)
			
			for match in matches:
				try:
					data = json.loads(match)
					if "tool" in data and "arguments" in data:
						tool_calls.append({
							"id": f"local_{len(tool_calls)}",
							"name": data["tool"],
							"arguments": data["arguments"]
						})
				except json.JSONDecodeError:
					continue
		
		except Exception:
			pass
		
		return tool_calls if tool_calls else None
