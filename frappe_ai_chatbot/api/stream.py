"""
Streaming API

Server-Sent Events (SSE) endpoint for real-time LLM response streaming.
Streams AI responses as they're generated, providing real-time feedback to users.
"""

import frappe
import json


@frappe.whitelist(allow_guest=False)
def stream_chat(session_id: str, message: str):
	"""
	Stream chat response using Server-Sent Events (SSE) protocol.
	
	SSE allows server to push data to browser in real-time over HTTP.
	Connection stays open and events are sent as they occur.
	
	Event types sent:
		- user_message: Confirms user message was saved
		- content: Text chunk from LLM (streamed as generated)
		- tool_call: Tool execution started
		- tool_result: Tool execution completed with result
		- done: Stream complete, includes final message
		- error: Error occurred, includes error details
	
	Args:
		session_id: Chat session ID (e.g., "CHAT-SESSION-00001")
		message: User's message text to send to LLM
		
	Returns:
		Streaming generator that yields SSE formatted strings
	"""
	# Import Response from werkzeug for direct streaming control
	from werkzeug.wrappers import Response
	
	def generate():
		"""Generator function that yields SSE events"""
		yield from _stream_chat_generator(session_id, message)
	
	# Return werkzeug Response object with SSE headers
	# This bypasses Frappe's JSON response wrapper
	return Response(
		generate(),
		mimetype='text/event-stream',
		headers={
			'Cache-Control': 'no-cache, no-transform',
			'Connection': 'keep-alive',
			'X-Accel-Buffering': 'no',
			'Access-Control-Allow-Origin': '*'
		}
	)


def _stream_chat_generator(session_id: str, message: str):
	"""
	Internal generator function for streaming chat responses.
	Yields SSE formatted event strings.
	"""
	print(f"\n[STREAM] Starting stream for session: {session_id}, message: {message[:50]}...")
	try:
		print("[STREAM] Validating session...")
		# Validate session exists in database
		if not frappe.db.exists("AI Chat Session", session_id):
			print("[STREAM] ERROR: Invalid session")
			yield format_sse_message("error", {"message": "Invalid session"})
			return
		print("[STREAM] Session valid")
		
		print("[STREAM] Checking permissions...")
		# Permission check: only session owner can stream messages
		session_doc = frappe.get_doc("AI Chat Session", session_id)
		if session_doc.user != frappe.session.user:
			print("[STREAM] ERROR: Permission denied")
			yield format_sse_message("error", {"message": "Permission denied"})
			return
		print("[STREAM] Permission OK")
		
		print("[STREAM] Importing dependencies...")
		# Import here to avoid circular dependency issues
		from frappe_ai_chatbot.llm.router import LLMRouter
		from frappe_ai_chatbot.utils.rate_limiter import check_rate_limit
		print("[STREAM] Dependencies imported")
		
		print("[STREAM] Getting settings...")
		# Get chatbot settings for rate limit check
		settings = frappe.get_single("AI Chatbot Settings")
		print("[STREAM] Settings loaded")
		
		print("[STREAM] Checking rate limit...")
		# Rate limit check: prevent abuse by limiting messages per user
		if not check_rate_limit(frappe.session.user, settings):
			print("[STREAM] ERROR: Rate limit exceeded")
			yield format_sse_message("error", {"message": "Rate limit exceeded. Please try again later."})
			return
		print("[STREAM] Rate limit OK")
		
		print("[STREAM] Saving user message...")
		# Save user message to database immediately
		from frappe_ai_chatbot.api.chat import _save_message
		user_msg = _save_message(
			session_id=session_id,
			role="user",
			content=message
		)
		print(f"[STREAM] User message saved: {user_msg.name}")
		
		print("[STREAM] Sending user_message event...")
		# Send confirmation that user message was saved (first SSE event)
		yield format_sse_message("user_message", {
			"name": user_msg.name,  # Message ID for reference
			"content": message,  # Echo back message
			"timestamp": str(user_msg.timestamp)  # When saved
		})
		print("[STREAM] user_message event sent")
		
		print("[STREAM] Initializing LLM Router...")
		# Initialize LLM router (selects provider based on settings)
		try:
			router = LLMRouter()
			print("[STREAM] LLM Router initialized successfully")
		except Exception as router_error:
			import traceback
			error_trace = traceback.format_exc()
			print("\n" + "="*80)
			print("ERROR: Failed to initialize LLM Router")
			print("="*80)
			print(error_trace)
			print("="*80 + "\n")
			frappe.log_error(f"Failed to initialize LLM Router: {str(router_error)}\n{error_trace}", "Stream Chat")
			yield format_sse_message("error", {"message": f"Failed to initialize AI: {str(router_error)}"})
			return
		
		# Track streamed content to save final message
		assistant_content = ""  # Accumulate text chunks
		tool_calls = []  # Track all tools used (across all iterations)
		all_tool_results = {}  # Track ALL tool results by tool_call_id (across all iterations)
		current_iteration_tool_calls = []  # Track tool calls for current iteration
		current_iteration_tool_results = {}  # Track tool results by tool_call_id for current iteration
		saved_assistant_msg_id = None  # Track saved assistant message ID
		
		print("[STREAM] Starting router.stream_chat()...")
		# Stream response from LLM - yields chunks as they're generated
		try:
			stream_generator = router.stream_chat(session_id=session_id, user_message=message)
			print("[STREAM] Stream generator created")
		except Exception as stream_error:
			import traceback
			error_trace = traceback.format_exc()
			print("\n" + "="*80)
			print("ERROR: Failed to start stream")
			print("="*80)
			print(error_trace)
			print("="*80 + "\n")
			frappe.log_error(f"Failed to start stream: {str(stream_error)}\n{error_trace}", "Stream Chat")
			yield format_sse_message("error", {"message": f"Failed to start chat stream: {str(stream_error)}"})
			return
		
		print("[STREAM] Starting to iterate chunks...")
		for chunk in stream_generator:
			print(f"[STREAM] Received chunk: type={chunk.get('type') if isinstance(chunk, dict) else type(chunk).__name__}")
			# Validate chunk is a dict
			if not isinstance(chunk, dict):
				print("\n" + "="*80)
				print("ERROR: Invalid chunk type")
				print("="*80)
				print(f"Expected: dict")
				print(f"Got: {type(chunk).__name__}")
				print(f"Value: {chunk}")
				print("="*80 + "\n")
				frappe.log_error(f"Invalid chunk type: {type(chunk)} - {chunk}", "Stream Chat")
				yield format_sse_message("error", {"message": f"Invalid response from AI: expected dict, got {type(chunk).__name__}"})
				return
			
			if chunk.get("type") == "content":
				# Text content chunk from LLM - forward immediately to client
				content = chunk.get("content", "")
				assistant_content += content  # Accumulate for final save
				yield format_sse_message("content", {"content": content})
				
			elif chunk.get("type") == "tool_call":
				# LLM requested tool execution - notify client
				tool_data = chunk.get("tool")
				if tool_data:
					tool_calls.append(tool_data)  # Track for overall message
					current_iteration_tool_calls.append(tool_data)  # Track for this iteration
					yield format_sse_message("tool_call", tool_data)
				
			elif chunk.get("type") == "tool_result":
				# Tool execution completed - track result and send to client
				tool_result_data = chunk.get("result")
				tool_name = chunk.get("tool")
				
				# Find the matching tool call to get the tool_call_id
				tool_call_id = None
				for tc in current_iteration_tool_calls:
					if tc.get("name") == tool_name:
						tool_call_id = tc.get("id")
						break
				
				if tool_result_data and tool_call_id:
					# Store result for later saving (after assistant message)
					current_iteration_tool_results[tool_call_id] = {
						"tool_name": tool_name,
						"result": tool_result_data
					}
					# Also track globally for final message save
					all_tool_results[tool_call_id] = {
						"tool_name": tool_name,
						"result": tool_result_data
					}
					# Send tool_result event with tool identification
					yield format_sse_message("tool_result", {
						"tool_name": tool_name,
						"tool_call_id": tool_call_id,
						"result": tool_result_data
					})
			
			elif chunk.get("type") == "done":
				# Done event - save messages in correct order: assistant → tool → tool → tool
				if current_iteration_tool_calls:
					try:
						# Filter out tool calls that don't have results
						# OpenAI API rejects assistant messages with tool_calls that have no corresponding tool result messages
						tool_calls_with_results = [
							tc for tc in current_iteration_tool_calls
							if tc.get("id") in current_iteration_tool_results
						]
						
						# Only save if we have tool calls with actual results
						if tool_calls_with_results:
							# Step 1: Save assistant message with ONLY tool calls that have results
							print(f"[STREAM] Saving assistant message with {len(tool_calls_with_results)} tool calls (filtered from {len(current_iteration_tool_calls)})")
							assistant_msg = _save_message(
								session_id=session_id,
								role="assistant",
								content=assistant_content if assistant_content else "",
								tool_calls=tool_calls_with_results
							)
							saved_assistant_msg_id = assistant_msg.name
							print(f"[STREAM] Assistant message saved: {saved_assistant_msg_id}")
							
							# Step 2: Save tool result messages (in order of tool_calls)
							for tc in tool_calls_with_results:
								tool_call_id = tc.get("id")
								tool_name = tc.get("name")
								
								# Get the result from our tracked results
								result_data = current_iteration_tool_results.get(tool_call_id)
								if result_data:
									print(f"[STREAM] Saving tool result message: {tool_name} (ID: {tool_call_id})")
									_save_message(
										session_id=session_id,
										role="tool",
										content=str(result_data["result"]),
										tool_call_id=tool_call_id,
										tool_name=tool_name
									)
									print(f"[STREAM] Tool result message saved: {tool_name}")
						else:
							print(f"[STREAM] No tool calls with results to save (had {len(current_iteration_tool_calls)} tool calls but none completed)")
						
						# Clear for next iteration
						current_iteration_tool_calls = []
						current_iteration_tool_results = {}
					except Exception as save_error:
						print(f"[STREAM] ERROR: Failed to save messages: {str(save_error)}")
						frappe.log_error(f"Failed to save messages: {str(save_error)}", "Stream Chat")
				
			elif chunk.get("type") == "error":
				# Error occurred during streaming - notify client and stop
				error_data = chunk.get("error")
				if isinstance(error_data, dict):
					yield format_sse_message("error", error_data)
				else:
					yield format_sse_message("error", {"message": str(error_data)})
				return  # Exit generator, close connection
		
		# Save final assistant message to database (if we have content and haven't saved yet)
		# This handles the case where the final response has content but no tool calls
		if assistant_content and not saved_assistant_msg_id:
			try:
				print(f"[STREAM] Saving final assistant message with content: {len(assistant_content)} chars")
				print(f"[STREAM] Tool calls in final message: {len(tool_calls) if tool_calls else 0}")
				
				# Filter tool_calls to only include those with results
				# This prevents OpenAI API errors about orphaned tool_call_ids
				tool_calls_to_save = None
				if tool_calls:
					# Use all_tool_results (global tracker) not current_iteration_tool_results (cleared after each done)
					# Only include tool calls that were actually executed and have results
					tool_calls_to_save = [tc for tc in tool_calls if tc.get("id") in all_tool_results]
					if not tool_calls_to_save:
						tool_calls_to_save = None  # Don't save empty array
					else:
						print(f"[STREAM] Filtered tool_calls: {len(tool_calls_to_save)} out of {len(tool_calls)} have results")
				
				assistant_msg = _save_message(
					session_id=session_id,
					role="assistant",
					content=assistant_content,  # Full accumulated text
					tool_calls=tool_calls_to_save  # Only tool calls that have results
				)
				saved_assistant_msg_id = assistant_msg.name
				print(f"[STREAM] Final assistant message saved: {saved_assistant_msg_id}")
			except Exception as save_error:
				print(f"[STREAM] ERROR: Failed to save final assistant message: {str(save_error)}")
				frappe.log_error(f"Failed to save final assistant message: {str(save_error)}", "Stream Chat")
		
		# Send final completion event with full message details
		try:
			yield format_sse_message("done", {
				"name": saved_assistant_msg_id,  # Message ID (may be None if save failed)
				"content": assistant_content,  # Complete response
				"timestamp": str(frappe.utils.now_datetime()),
				"tool_calls": tool_calls  # All tools used
			})
		except Exception as done_error:
			print(f"[STREAM] ERROR: Failed to send done event: {str(done_error)}")
			frappe.log_error(f"Failed to send done event: {str(done_error)}", "Stream Chat")
		
	except Exception as e:
		# Print error to console
		import traceback
		error_trace = traceback.format_exc()
		print("\n" + "="*80)
		print("ERROR: Stream Chat Exception")
		print("="*80)
		print(error_trace)
		print("="*80 + "\n")
		
		# Log error to Frappe Error Log for debugging
		frappe.log_error(title="Stream Chat Error", message=frappe.get_traceback())
		
		# Check for specific OAuth-related errors
		error_msg = str(e)
		if "No OAuth tokens found" in error_msg or "AI Chatbot User Token DocType not found" in error_msg:
			# User needs to authorize
			yield format_sse_message("error", {
				"message": "Authorization required. Please authorize the chatbot to continue.",
				"action": "authorize",
				"details": "You need to authorize the AI Assistant to access Frappe Assistant Core. The chatbot will prompt you to authorize on the next page load."
			})
		elif "authorization" in error_msg.lower() or "authenticate" in error_msg.lower():
			# Generic auth error
			yield format_sse_message("error", {
				"message": "Authentication error. Please try reloading the page and authorizing again.",
				"action": "reload",
				"details": error_msg
			})
		else:
			# Generic error
			yield format_sse_message("error", {
				"message": str(e),  # Error message
				"traceback": frappe.get_traceback() if frappe.conf.developer_mode else None  # Stack trace only in dev mode
			})


def format_sse_message(event_type: str, data: dict) -> str:
	"""
	Format a message according to Server-Sent Events protocol.
	
	SSE format requires:
		event: <type>
		data: <json>
		<blank line>
	
	Args:
		event_type: Event type identifier (content, tool_call, tool_result, error, done, user_message)
		data: Event payload (will be JSON serialized)
		
	Returns:
		Formatted SSE message string ready to send to client
	
	Example:
		format_sse_message("content", {"content": "Hello"})
		Returns: "event: content\ndata: {\"content\": \"Hello\"}\n\n"
	"""
	message = f"event: {event_type}\n"  # Event type line
	message += f"data: {json.dumps(data)}\n\n"  # Data line + blank line separator
	return message


@frappe.whitelist()
def test_streaming():
	"""
	Test endpoint for streaming functionality.
	Returns a simple counting stream.
	"""
	import time
	
	frappe.response["type"] = "page"
	frappe.response["page_name"] = "test_stream"
	
	frappe.local.response.http_status_code = 200
	frappe.response.headers = {
		"Content-Type": "text/event-stream",
		"Cache-Control": "no-cache",
		"Connection": "keep-alive"
	}
	
	def generate():
		for i in range(10):
			yield format_sse_message("count", {"number": i})
			time.sleep(0.5)
		yield format_sse_message("done", {"message": "Complete"})
	
	return generate()
