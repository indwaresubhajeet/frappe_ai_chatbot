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
		tool_calls = []  # Track tools used
		
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
					tool_calls.append(tool_data)  # Track for final message
					yield format_sse_message("tool_call", tool_data)
				
			elif chunk.get("type") == "tool_result":
				# Tool execution completed - send result to client
				tool_result = chunk.get("result")
				if tool_result:
					yield format_sse_message("tool_result", tool_result)
				
			elif chunk.get("type") == "error":
				# Error occurred during streaming - notify client and stop
				error_data = chunk.get("error")
				if isinstance(error_data, dict):
					yield format_sse_message("error", error_data)
				else:
					yield format_sse_message("error", {"message": str(error_data)})
				return  # Exit generator, close connection
		
		# Save complete assistant message to database now that streaming is done
		try:
			assistant_msg = _save_message(
				session_id=session_id,
				role="assistant",
				content=assistant_content,  # Full accumulated text
				tool_calls=tool_calls if tool_calls else None  # Tools used (if any)
			)
			
			# Note: Rate limit tracking happens automatically when messages are saved
			# No need to manually record - message count is tracked in database
			
			# Send final completion event with full message details
			yield format_sse_message("done", {
				"name": assistant_msg.name,  # Message ID
				"content": assistant_content,  # Complete response
				"timestamp": str(assistant_msg.timestamp),  # When saved
				"tool_calls": tool_calls  # All tools used
			})
		except Exception as save_error:
			# If saving fails, still send done event without message ID
			frappe.log_error(f"Failed to save assistant message: {str(save_error)}", "Stream Chat")
			yield format_sse_message("done", {
				"name": None,  # No message ID if save failed
				"content": assistant_content,  # Still send the content
				"timestamp": str(frappe.utils.now_datetime()),
				"tool_calls": tool_calls
			})
		
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
