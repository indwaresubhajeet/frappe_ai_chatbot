"""
LLM Router

Routes requests to appropriate LLM provider and handles conversation flow.
Abstracts provider-specific implementation details behind a common interface.
Manages tool calling, context windows, and multi-turn conversations.
"""

import frappe
from typing import Dict, List, Optional, Generator, Any
from frappe_ai_chatbot.llm.base_adapter import (
	BaseLLMAdapter,
	LLMMessage,
	LLMResponse,
	LLMError
)


class LLMRouter:
	"""
	Central orchestrator for LLM interactions.
	
	Responsibilities:
		- Select and initialize correct LLM adapter based on settings
		- Manage conversation context (windowing based on context_window_size)
		- Orchestrate tool calling flow (multi-turn conversations)
		- Provide both streaming and non-streaming interfaces
		- Handle errors and fallback behavior
	"""
	
	def __init__(self):
		"""
		Initialize router with current AI Chatbot Settings.
		Automatically selects and configures appropriate LLM adapter.
		"""
		self.settings = frappe.get_single("AI Chatbot Settings")
		self.adapter: Optional[BaseLLMAdapter] = None
		self._initialize_adapter()  # Create provider-specific adapter
	
	def _initialize_adapter(self):
		"""
		Initialize the appropriate LLM adapter based on llm_provider setting.
		
		Supported providers:
			- claude: Anthropic Claude (via anthropic SDK)
			- openai: OpenAI GPT models (via openai SDK)
			- gemini: Google Gemini (via google-generativeai SDK)
			- local: Local models via Ollama (HTTP API)
		
		Raises:
			frappe.throw: If provider is unknown or configuration is invalid
		"""
		provider = self.settings.llm_provider
		
		# Lazy import adapters to avoid circular dependencies
		# Each adapter implements BaseLLMAdapter interface
		if provider.lower() == "claude":
			from frappe_ai_chatbot.llm.claude_adapter import ClaudeAdapter
			self.adapter = ClaudeAdapter(
				api_key=self.settings.get_password("claude_api_key"),  # Secure password retrieval
				model=self.settings.claude_model,  # e.g., "claude-3-5-sonnet-20241022"
				temperature=self.settings.temperature,  # Randomness (0.0-1.0)
				max_tokens=self.settings.max_tokens  # Max response length
			)
		elif provider.lower() == "openai":
			from frappe_ai_chatbot.llm.openai_adapter import OpenAIAdapter
			self.adapter = OpenAIAdapter(
				api_key=self.settings.get_password("openai_api_key"),
				model=self.settings.openai_model,  # e.g., "gpt-4o"
				temperature=self.settings.temperature,
				max_tokens=self.settings.max_tokens
			)
		elif provider.lower() == "gemini":
			from frappe_ai_chatbot.llm.gemini_adapter import GeminiAdapter
			self.adapter = GeminiAdapter(
				api_key=self.settings.get_password("gemini_api_key"),
				model=self.settings.gemini_model,  # e.g., "gemini-1.5-flash"
				temperature=self.settings.temperature,
				max_tokens=self.settings.max_tokens
			)
		elif provider.lower() == "local":
			from frappe_ai_chatbot.llm.local_adapter import LocalAdapter
			self.adapter = LocalAdapter(
				base_url=self.settings.ollama_base_url,  # Ollama server URL
				model=self.settings.local_model,  # e.g., "llama2"
				temperature=self.settings.temperature,
				max_tokens=self.settings.max_tokens
			)
		else:
			frappe.throw(f"Unsupported LLM provider: {provider}")
		
		# Validate adapter has required credentials and configuration
		if not self.adapter.validate_config():
			frappe.throw(f"Invalid configuration for {provider} provider")
	
	def chat(self, session_id: str, user_message: str) -> Dict:
		"""
		Process a non-streaming chat request and return complete response.
		
		Flow:
			1. Load conversation history (windowed by context_window_size)
			2. Add current user message to context
			3. Load available tools if tool_calling is enabled
			4. Call LLM adapter with context + tools
			5. If LLM wants to use tools, orchestrate tool execution
			6. Return final response with content + metadata
		
		Args:
			session_id: AI Chat Session ID (for loading history)
			user_message: User's input message
		
		Returns:
			Dict containing:
				- content: Final assistant response text
				- model: Model name used (e.g., "claude-3-5-sonnet")
				- token_count: Total tokens consumed
				- tool_calls: List of tools executed (if any)
				- cost: Estimated API cost in USD
				- finish_reason: Why generation stopped (stop, length, tool_use)
		"""
		try:
			# Load recent messages for context (respects context_window_size)
			messages = self._get_conversation_context(session_id)
			
			# Append user's new message to conversation
			messages.append(LLMMessage(role="user", content=user_message))
			
			# Load MCP tools if feature is enabled
			tools = None
			if self.settings.enable_tool_calling:
				tools = self._get_available_tools()  # Loads from MCP client
			
			# Get system instructions (defines assistant behavior)
			system_prompt = self.settings.system_prompt
			
			# Call LLM adapter (provider-specific implementation)
			response = self.adapter.chat(
				messages=messages,
				tools=tools,
				system_prompt=system_prompt
			)
			
			# If LLM requested tool execution, handle recursively
			if response.tool_calls and self.settings.enable_tool_calling:
				response = self._handle_tool_calls(
					messages=messages,
					response=response,
					tools=tools,
					system_prompt=system_prompt
				)
			
			# Return structured response
			return {
				"content": response.content,
				"model": response.model,
				"token_count": response.token_count,
				"tool_calls": response.tool_calls,  # List of tools used
				"cost": response.cost,  # Estimated USD cost
				"finish_reason": response.finish_reason  # stop/length/tool_use
			}
		
		except LLMError as e:
			frappe.log_error(f"LLM Error: {str(e)}", "LLM Router")
			frappe.throw(f"AI Error: {str(e)}")
		
		except Exception as e:
			# Log unexpected errors for debugging
			frappe.log_error(f"Unexpected error in chat: {str(e)}", "LLM Router")
			frappe.throw("An unexpected error occurred. Please try again.")
	
	def stream_chat(
		self,
		session_id: str,
		user_message: str
	) -> Generator[Dict[str, Any], None, None]:
		"""
		Process a streaming chat request and yield events as they occur.
		
		Streaming provides real-time feedback to users as LLM generates response.
		Events are yielded immediately as received from LLM provider.
		
		Flow:
			1. Load conversation history (windowed)
			2. Add user message to context
			3. Load available tools if enabled
			4. Stream LLM response (yields content chunks)
			5. When tool calls are made, execute and stream results
			6. Yield final completion event
		
		Args:
			session_id: AI Chat Session ID
			user_message: User's input message
		
		Yields:
			Dict events with:
				- type: "content" | "tool_call" | "tool_result" | "error" | "done"
				- data: Event-specific payload
		
		Example events:
			{"type": "content", "data": {"content": "Hello", "delta": "Hello"}}
			{"type": "tool_call", "data": {"tool_name": "get_document", "args": {...}}}
			{"type": "tool_result", "data": {"result": {...}}}
			{"type": "done", "data": {"finish_reason": "stop"}}
		"""
		try:
			# Load conversation history (respects context_window_size)
			messages = self._get_conversation_context(session_id)
			
			# Add user's message to conversation
			messages.append(LLMMessage(role="user", content=user_message))
			
			# Load MCP tools if feature is enabled
			tools = None
			if self.settings.enable_tool_calling:
				tools = self._get_available_tools()
			
			# Get system instructions
			system_prompt = self.settings.system_prompt
			
			# Stream LLM response (yields events as they arrive)
			tool_calls_made = []  # Track all tool calls for potential second LLM call
			assistant_content = ""  # Track any text content
			executed_tool_ids = set()  # Track which tools we've already executed
			all_tool_calls = []  # Collect all tool calls from events
			
			for event in self.adapter.stream_chat(
				messages=messages,
				tools=tools,
				system_prompt=system_prompt
			):
				# If LLM wants to call a tool, execute it
				if event.get("type") == "tool_call" and self.settings.enable_tool_calling:
					tool_call = event["tool"]
					tool_id = tool_call.get("id")
					
					print(f"[ROUTER] Tool call event received: {tool_call.get('name')} (ID: {tool_id})")
					
					# Yield the tool_call event first (so UI shows "Executing...")
					yield event
					
					# Execute tool if not already executed
					if tool_id not in executed_tool_ids:
						try:
							print(f"[ROUTER] Executing tool: {tool_call['name']} (ID: {tool_id})")
							tool_result = self._execute_tool(tool_call)
							executed_tool_ids.add(tool_id)
							
							# Track this tool call for second LLM pass
							tool_calls_made.append({
								"call": tool_call,
								"result": tool_result
							})
							
							print(f"[ROUTER] Tool executed successfully: {tool_call['name']}")
							
							# Yield tool execution result as event
							yield {
								"type": "tool_result",
								"tool": tool_call["name"],
								"result": tool_result
							}
						except Exception as tool_error:
							print(f"[ROUTER] Tool execution failed: {tool_call['name']} - {str(tool_error)}")
							import traceback
							print(traceback.format_exc())
							# Still track the failed tool call
							executed_tool_ids.add(tool_id)
							# Yield error result
							yield {
								"type": "tool_result",
								"tool": tool_call["name"],
								"result": {"error": str(tool_error), "success": False},
								"isError": True
							}
					else:
						print(f"[ROUTER] Skipping already executed tool: {tool_call['name']} (ID: {tool_id})")
					
					# Track all tool calls
					all_tool_calls.append(tool_call)
				
				elif event.get("type") == "content":
					# Track content for potential second pass
					content = event.get("content", "")
					assistant_content += content
					# Forward content event
					yield event
				
				elif event.get("type") == "done":
					print("[ROUTER] Done event received from adapter")
					print(f"[ROUTER] Executed tool IDs: {executed_tool_ids}")
					print(f"[ROUTER] Tool calls made: {len(tool_calls_made)}")
					
					# Check if done event contains tool_calls we haven't executed yet
					done_tool_calls = event.get("data", {}).get("tool_calls", [])
					print(f"[ROUTER] Done event tool_calls: {len(done_tool_calls)}")
					
					if done_tool_calls and self.settings.enable_tool_calling:
						for tool_call in done_tool_calls:
							tool_id = tool_call.get("id")
							print(f"[ROUTER] Checking tool from done event: {tool_call.get('name')} (ID: {tool_id})")
							
							# Execute any tools from done event that we haven't seen yet
							if tool_id not in executed_tool_ids:
								print(f"[ROUTER] Executing missed tool from done event: {tool_call.get('name')}")
								
								# Yield tool_call event first
								yield {
									"type": "tool_call",
									"tool": tool_call
								}
								
								try:
									# Execute the tool
									tool_result = self._execute_tool(tool_call)
									executed_tool_ids.add(tool_id)
									
									# Track for second LLM pass
									tool_calls_made.append({
										"call": tool_call,
										"result": tool_result
									})
									
									# Yield result
									yield {
										"type": "tool_result",
										"tool": tool_call["name"],
										"result": tool_result
									}
									
									# Track all tool calls
									all_tool_calls.append(tool_call)
									
									print(f"[ROUTER] Missed tool executed successfully: {tool_call.get('name')}")
								except Exception as tool_error:
									print(f"[ROUTER] Missed tool execution failed: {str(tool_error)}")
									import traceback
									print(traceback.format_exc())
									executed_tool_ids.add(tool_id)
									yield {
										"type": "tool_result",
										"tool": tool_call["name"],
										"result": {"error": str(tool_error), "success": False},
										"isError": True
									}
							else:
								print(f"[ROUTER] Tool already executed: {tool_call.get('name')} (ID: {tool_id})")
					
					# Forward the done event
					yield event
				
				else:
					# Forward all other events (error, etc.)
					yield event
			
			# If tools were called, we need to call LLM again with results
			# Keep looping until LLM stops requesting tools
			while tool_calls_made and self.settings.enable_tool_calling:
				print(f"\n[ROUTER] ========================================")
				print(f"[ROUTER] CALLING LLM WITH {len(tool_calls_made)} tool results")
				print(f"[ROUTER] ========================================\n")
				
				# Add assistant's tool call message to conversation
				messages.append(LLMMessage(
					role="assistant",
					content="",  # No text content, just tool calls
					tool_calls=[tc["call"] for tc in tool_calls_made]
				))
				
				# Add tool results as messages
				for tc in tool_calls_made:
					messages.append(LLMMessage(
						role="tool",
						content=str(tc["result"]),
						tool_call_id=tc["call"].get("id"),
						name=tc["call"]["name"]
					))
				
				# Clear tool_calls_made for next iteration
				tool_calls_made = []
				
				# Stream LLM response with tool results
				# LLM might request MORE tools, or generate final response
				for event in self.adapter.stream_chat(
					messages=messages,
					tools=tools,  # Tools still available if needed
					system_prompt=system_prompt
				):
					print(f"[ROUTER] Loop iteration - Event received: type={event.get('type')}")
					
					# Handle tool calls (LLM might need more tools!)
					if event.get("type") == "tool_call" and self.settings.enable_tool_calling:
						tool_call = event["tool"]
						tool_id = tool_call.get("id")
						
						print(f"[ROUTER] Loop iteration - Tool call event received: {tool_call.get('name')} (ID: {tool_id})")
						
						# Yield the tool_call event first
						yield event
						
						# Execute tool if not already executed
						if tool_id not in executed_tool_ids:
							try:
								print(f"[ROUTER] Loop iteration - Executing tool: {tool_call['name']} (ID: {tool_id})")
								tool_result = self._execute_tool(tool_call)
								executed_tool_ids.add(tool_id)
								
								# Track this tool call for next iteration
								tool_calls_made.append({
									"call": tool_call,
									"result": tool_result
								})
								
								print(f"[ROUTER] Loop iteration - Tool executed successfully: {tool_call['name']}")
								
								# Yield tool execution result
								yield {
									"type": "tool_result",
									"tool": tool_call["name"],
									"result": tool_result
								}
							except Exception as tool_error:
								print(f"[ROUTER] Loop iteration - Tool execution failed: {tool_call['name']} - {str(tool_error)}")
								import traceback
								print(traceback.format_exc())
								executed_tool_ids.add(tool_id)
								yield {
									"type": "tool_result",
									"tool": tool_call["name"],
									"result": {"error": str(tool_error), "success": False},
									"isError": True
								}
						else:
							print(f"[ROUTER] Loop iteration - Skipping already executed tool: {tool_call['name']} (ID: {tool_id})")
					
					elif event.get("type") == "content":
						# Forward content events (final response!)
						print(f"[ROUTER] Loop iteration - Content event: {event.get('content', '')[:100]}...")
						yield event
					
					elif event.get("type") == "done":
						# Done event - check if we need to loop again
						print(f"[ROUTER] Loop iteration - Done event received")
						print(f"[ROUTER] Loop iteration - Tool calls made in this iteration: {len(tool_calls_made)}")
						
						# Don't yield done yet if we have more tools to execute
						if not tool_calls_made:
							# No more tools - this is the final done event
							print("[ROUTER] No more tools needed - streaming complete!")
							yield event
					
					else:
						# Forward all other events (error, etc.)
						print(f"[ROUTER] Loop iteration - Forwarding event type: {event.get('type')}")
						yield event
		
		except LLMError as e:
			# Log and yield LLM-specific errors
			frappe.log_error(f"LLM Error: {str(e)}", "LLM Router")
			yield {
				"type": "error",
				"error": str(e)
			}
		
		except Exception as e:
			# Log and yield unexpected errors
			frappe.log_error(f"Unexpected error in stream_chat: {str(e)}", "LLM Router")
			
			# Check for specific OAuth/authorization errors
			error_msg = str(e)
			if "No OAuth tokens found" in error_msg or "AI Chatbot User Token DocType not found" in error_msg:
				yield {
					"type": "error",
					"error": "Authorization required. Please authorize the AI Assistant to access Frappe Assistant Core.",
					"action": "authorize",
					"details": "Click the authorization dialog that will appear to connect to Frappe Assistant Core."
				}
			elif "authorization" in error_msg.lower() or "authenticate" in error_msg.lower():
				yield {
					"type": "error",
					"error": "Authentication error. Please reload the page and authorize again.",
					"action": "reload",
					"details": error_msg
				}
			else:
				yield {
					"type": "error",
					"error": f"An unexpected error occurred: {error_msg}"
				}
	
	def _get_conversation_context(self, session_id: str) -> List[LLMMessage]:
		"""
		Load conversation history with windowing to fit within context limits.
		
		Uses ContextManager to load recent messages from database.
		Respects context_window_size setting to avoid exceeding LLM limits.
		
		Args:
			session_id: AI Chat Session ID
		
		Returns:
			List of LLMMessage objects (ordered chronologically)
		"""
		from frappe_ai_chatbot.utils.context_manager import ContextManager
		
		# ContextManager handles message windowing based on context_window_size
		context_mgr = ContextManager(self.settings.context_window_size)
		return context_mgr.get_context(session_id)
	
	def _get_available_tools(self) -> List[Dict]:
		"""
		Load available tools from MCP client and format for LLM provider.
		
		Flow:
			1. MCPClient lists tools from connected MCP servers
			2. Each tool has: name, description, input_schema (JSON Schema)
			3. Adapter converts tool to provider-specific format:
				- Claude: Uses tool_use format
				- OpenAI: Uses function_calling format
				- Gemini: Uses function_declaration format
		
		Returns:
			List of tool definitions in provider-specific format
		"""
		from frappe_ai_chatbot.mcp.client import MCPClient
		
		try:
			# Get tools from MCP servers (via JSON-RPC 2.0)
			mcp_client = MCPClient()
			mcp_tools = mcp_client.list_tools()  # Returns list of MCPTool objects
			
			# Convert each MCP tool to provider-specific format
			llm_tools = []
			for tool in mcp_tools:
				# Adapter handles provider-specific formatting
				llm_tool = self.adapter.format_tool_for_llm(tool)
				llm_tools.append(llm_tool)
			
			return llm_tools
		
		except Exception as e:
			error_msg = str(e)
			
			# Check if this is an OAuth/authorization error
			if "No OAuth tokens found" in error_msg or "AI Chatbot User Token DocType not found" in error_msg:
				frappe.throw(
					msg="Authorization required. Please authorize the AI Assistant to access Frappe Assistant Core. "
					"The chatbot will prompt you to authorize - click 'Authorize Now' and follow the OAuth flow.",
					title="Authorization Required"
				)
			elif "DocType" in error_msg and "not found" in error_msg:
				frappe.throw(
					msg="Setup incomplete. Please run: bench --site your-site migrate\n\n"
					"This will create the required AI Chatbot User Token DocType. "
					"After migration, restart your server and authorize the chatbot.",
					title="Migration Required"
				)
			else:
				# Re-raise original error for other cases
				frappe.log_error(f"Error loading MCP tools: {error_msg}", "LLM Router")
				raise
	
	def _execute_tool(self, tool_call: Dict) -> Dict:
		"""
		Execute a tool via MCP executor.
		
		Sends JSON-RPC request to MCP server to execute tool.
		Handles errors and formats response for LLM.
		
		Args:
			tool_call: Dict containing:
				- name: Tool name (e.g., "get_document")
				- arguments: Tool arguments (dict)
		
		Returns:
			Tool execution result (formatted for LLM)
		"""
		from frappe_ai_chatbot.mcp.executor import MCPExecutor
		
		# MCPExecutor handles JSON-RPC communication with MCP server
		executor = MCPExecutor()
		result = executor.execute(
			name=tool_call["name"],
			arguments=tool_call["arguments"]
		)
		
		return result
	
	def _handle_tool_calls(
		self,
		messages: List[LLMMessage],
		response: LLMResponse,
		tools: List[Dict],
		system_prompt: str
	) -> LLMResponse:
		"""
		Orchestrate multi-turn tool calling conversation.
		
		When LLM wants to use tools, this function:
			1. Executes each tool call
			2. Adds tool results to conversation
			3. Calls LLM again with results
			4. Recursively handles if LLM makes more tool calls
		
		This enables complex workflows like:
			- LLM uses get_document to fetch data
			- LLM analyzes data and uses update_document
			- LLM confirms update with final message
		
		Args:
			messages: Conversation history (will be mutated)
			response: LLM response containing tool_calls
			tools: Available tools (passed to subsequent LLM calls)
			system_prompt: System instructions
		
		Returns:
			Final LLM response after all tools executed (no tool_calls)
		"""
		# Add assistant's tool-calling message to conversation
		messages.append(LLMMessage(
			role="assistant",
			content=response.content,  # May be empty or explanation
			tool_calls=response.tool_calls  # List of tools to execute
		))
		
		# Execute each tool sequentially
		for tool_call in response.tool_calls:
			result = self._execute_tool(tool_call)
			
			# Add tool result as message (LLM will see this)
			messages.append(LLMMessage(
				role="tool",
				content=str(result),  # JSON-serialized result
				tool_call_id=tool_call.get("id"),  # Links to tool call
				name=tool_call["name"]  # Tool that was executed
			))
		
		# Call LLM again with tool results in context
		final_response = self.adapter.chat(
			messages=messages,
			tools=tools,  # Still available for further calls
			system_prompt=system_prompt
		)
		
		# Recursive: If LLM makes more tool calls, handle them
		if final_response.tool_calls:
			return self._handle_tool_calls(
				messages=messages,  # Already contains previous tool results
				response=final_response,
				tools=tools,
				system_prompt=system_prompt
			)
		
		# Base case: No more tool calls, return final response
		return final_response
	
	def get_adapter(self) -> BaseLLMAdapter:
		"""
		Get the current LLM adapter instance.
		
		Used for direct access to adapter methods if needed.
		
		Returns:
			Current adapter (ClaudeAdapter, OpenAIAdapter, etc.)
		"""
		return self.adapter
	
	def count_tokens(self, text: str) -> int:
		"""
		Count tokens in text using provider-specific tokenizer.
		
		Different providers have different tokenization:
			- Claude: Uses Anthropic's tokenizer
			- OpenAI: Uses tiktoken
			- Gemini: Uses Google's tokenizer
			- Local: Depends on model
		
		Args:
			text: Text to count tokens for
		
		Returns:
			Token count (approximate for some providers)
		"""
		# Wrap text as a user message for counting
		messages = [LLMMessage(role="user", content=text)]
		return self.adapter.count_tokens(messages)
