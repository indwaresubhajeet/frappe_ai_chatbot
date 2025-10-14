"""
Base LLM Adapter

Abstract base class defining the interface for all LLM provider implementations.
Uses the Adapter design pattern to provide a uniform interface across different LLM APIs.

Pattern Benefits:
	- Single interface for multiple providers (Claude, OpenAI, Gemini, Local)
	- Easy to add new providers (just implement this interface)
	- Swappable implementations (change provider without changing router code)
	- Testable (can mock adapters)

Responsibilities:
	- Define standard data structures (LLMMessage, LLMResponse, LLMTool)
	- Define abstract methods all adapters must implement
	- Provide utility methods (validation, token counting, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Generator, Any
from dataclasses import dataclass


@dataclass
class LLMMessage:
	"""
	Standard message format for LLM communication.
	
	Normalized format that works across all providers.
	Adapters convert this to provider-specific formats.
	
	Attributes:
		role: Message role (user, assistant, system, tool)
		content: Message text content
		tool_calls: Tool calls requested by assistant (if any)
		tool_call_id: ID linking tool result to tool call
		name: Tool name (for tool result messages)
	"""
	role: str  # user, assistant, system, tool
	content: str
	tool_calls: Optional[List[Dict]] = None
	tool_call_id: Optional[str] = None
	name: Optional[str] = None  # For tool results


@dataclass
class LLMResponse:
	"""
	Standard response format from LLM.
	
	Normalized format that adapters return after calling their respective APIs.
	Contains content, metadata, and optional tool calls.
	
	Attributes:
		content: Generated text response
		model: Model name that generated response (e.g., "claude-3-5-sonnet")
		token_count: Total tokens consumed (prompt + completion)
		tool_calls: Tool calls requested by LLM (if any)
		finish_reason: Why generation stopped (stop, length, tool_use)
		cost: Estimated API cost in USD
		metadata: Provider-specific additional data
	"""
	content: str
	model: str
	token_count: int
	tool_calls: Optional[List[Dict]] = None
	finish_reason: Optional[str] = None
	cost: float = 0.0
	metadata: Optional[Dict] = None


@dataclass
class LLMTool:
	"""
	Standard tool definition format.
	
	Normalized format for tool definitions.
	Adapters convert this to provider-specific formats:
		- Claude: tool_use format
		- OpenAI: function_calling format
		- Gemini: function_declaration format
	
	Attributes:
		name: Tool identifier (e.g., "get_document")
		description: What the tool does
		parameters: JSON Schema defining input parameters
	"""
	name: str
	description: str
	parameters: Dict  # JSON schema


class BaseLLMAdapter(ABC):
	"""
	Abstract base class for LLM provider adapters.
	
	All LLM providers (Claude, OpenAI, Gemini, Local) implement this interface.
	Provides consistent API regardless of underlying LLM provider.
	
	Adapter Pattern Implementation:
		- Target: BaseLLMAdapter (this class)
		- Adaptee: Provider SDKs (anthropic, openai, google-generativeai)
		- Adapter: ClaudeAdapter, OpenAIAdapter, etc.
	
	Required Methods (must be implemented by subclasses):
		- chat(): Non-streaming completion
		- stream_chat(): Streaming completion
		- validate_config(): Check API key and settings
		- count_tokens(): Token counting
		- format_tool_for_llm(): Convert tool to provider format
		- parse_tool_call(): Parse tool call from provider response
	"""
	
	def __init__(self, api_key: Optional[str] = None, model: str = None, **kwargs):
		"""
		Initialize adapter with configuration.
		
		Args:
			api_key: API key for the provider (None for local models)
			model: Model name to use (e.g., "claude-3-5-sonnet-20241022")
			**kwargs: Additional provider-specific configuration:
				- temperature: Randomness (0.0-1.0)
				- max_tokens: Max response length
				- top_p: Nucleus sampling
				- etc.
		"""
		self.api_key = api_key
		self.model = model
		self.config = kwargs
	
	@abstractmethod
	def chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> LLMResponse:
		"""
		Send chat request and get complete response (non-streaming).
		
		Synchronous method that waits for full response before returning.
		Used when streaming is not needed or not supported.
		
		Flow:
			1. Convert LLMMessage list to provider format
			2. Convert tools to provider format (if provided)
			3. Call provider API
			4. Parse response
			5. Return LLMResponse
		
		Args:
			messages: Conversation history (list of LLMMessage)
			tools: Available tools for function calling (optional)
			system_prompt: System instructions (optional)
			**kwargs: Additional parameters (overrides adapter config)
		
		Returns:
			LLMResponse with content and metadata
		"""
		pass
	
	@abstractmethod
	def stream_chat(
		self,
		messages: List[LLMMessage],
		tools: Optional[List[LLMTool]] = None,
		system_prompt: Optional[str] = None,
		**kwargs
	) -> Generator[Dict[str, Any], None, None]:
		"""
		Send chat request and stream response chunks as they arrive.
		
		Generator function that yields events in real-time.
		Used for responsive UI that shows progress as LLM generates.
		
		Flow:
			1. Convert messages and tools to provider format
			2. Call provider streaming API
			3. Yield events as they arrive:
				- content: Text chunks
				- tool_call: Tool execution request
				- done: Stream complete with metadata
				- error: Error occurred
		
		Args:
			messages: Conversation history
			tools: Available tools (optional)
			system_prompt: System instructions (optional)
			**kwargs: Additional parameters
		
		Yields:
			Dict events with type and data:
				{"type": "content", "content": "text chunk", "delta": "chunk"}
				{"type": "tool_call", "name": "tool_name", "parameters": {...}}
				{"type": "done", "tokens": 123, "cost": 0.05, "finish_reason": "stop"}
				{"type": "error", "error": "error message"}
		"""
		pass
	
	@abstractmethod
	def count_tokens(self, messages: List[LLMMessage]) -> int:
		"""
		Count tokens in messages using provider-specific tokenizer.
		
		Different providers have different tokenization:
			- Claude: Anthropic's tokenizer
			- OpenAI: tiktoken
			- Gemini: Google's tokenizer
			- Local: Model-specific
		
		Used for:
			- Context window management
			- Cost estimation
			- Rate limiting
		
		Args:
			messages: List of messages to count
		
		Returns:
			Total token count (approximate for some providers)
		"""
		pass
	
	@abstractmethod
	def format_tool_for_llm(self, tool: Dict) -> Dict:
		"""
		Convert MCP tool format to provider-specific format.
		
		MCP tools use standard JSON Schema format.
		Each provider expects different formats:
			- Claude: tool_use with input_schema
			- OpenAI: function_calling with parameters
			- Gemini: function_declaration with schema
		
		Args:
			tool: Tool in MCP format:
				{
					"name": "get_document",
					"description": "Fetch a document",
					"inputSchema": {"type": "object", "properties": {...}}
				}
		
		Returns:
			Tool in provider-specific format
		"""
		pass
	
	@abstractmethod
	def parse_tool_call(self, response: Any) -> Optional[List[Dict]]:
		"""
		Parse tool calls from provider-specific response.
		
		Each provider returns tool calls differently:
			- Claude: stop_reason="tool_use" with content blocks
			- OpenAI: finish_reason="tool_calls" with tool_calls array
			- Gemini: candidates with function_call
		
		This method normalizes to standard format:
			[
				{
					"id": "call_123",
					"name": "get_document",
					"arguments": {"doctype": "Task", "name": "TASK-001"}
				}
			]
		
		Args:
			response: Provider-specific response object
		
		Returns:
			List of tool calls in normalized format, or None if no tools called
		"""
		pass
	
	def validate_config(self) -> bool:
		"""
		Validate adapter configuration before use.
		
		Checks that required configuration is present:
			- API key (if required by provider)
			- Model name
			- Other provider-specific requirements
		
		Called by router during initialization.
		Prevents runtime errors from missing configuration.
		
		Returns:
			True if configuration is valid, False otherwise
		"""
		if not self.model:
			return False
		return True
	
	def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
		"""
		Estimate API cost for token usage.
		
		Different providers have different pricing:
			- Claude: $3/$15 per million tokens (input/output for Sonnet)
			- OpenAI: $2.50/$10 per million tokens (input/output for GPT-4o)
			- Gemini: Free tier available, then $0.35/$1.05 per million
			- Local: No cost (self-hosted)
		
		Subclasses override with actual pricing for their models.
		Used for cost tracking and budget alerts.
		
		Args:
			input_tokens: Number of prompt tokens
			output_tokens: Number of completion tokens
		
		Returns:
			Estimated cost in USD
		"""
		# Default implementation (override in subclass with actual pricing)
		return 0.0
	
	def get_max_tokens(self) -> int:
		"""
		Get maximum token limit for current model.
		
		Context windows vary by model:
			- Claude 3.5 Sonnet: 200K tokens
			- GPT-4o: 128K tokens
			- Gemini 1.5 Flash: 1M tokens
			- Local models: Varies (often 4K-32K)
		
		Used for context window management.
		Subclasses override with model-specific limits.
		
		Returns:
			Maximum tokens model can handle
		"""
		# Default implementation (override in subclass)
		return 4096
	
	def supports_function_calling(self) -> bool:
		"""
		Check if model supports function calling.
		
		Returns:
			True if supported
		"""
		# Override in subclass
		return True
	
	def supports_streaming(self) -> bool:
		"""
		Check if adapter supports streaming.
		
		Returns:
			True if supported
		"""
		# Override in subclass
		return True


class LLMError(Exception):
	"""Base exception for LLM errors"""
	pass


class LLMConnectionError(LLMError):
	"""Connection error"""
	pass


class LLMRateLimitError(LLMError):
	"""Rate limit exceeded"""
	pass


class LLMInvalidRequestError(LLMError):
	"""Invalid request"""
	pass


class LLMAuthenticationError(LLMError):
	"""Authentication failed"""
	pass
