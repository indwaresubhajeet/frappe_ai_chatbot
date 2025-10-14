"""
Chat API

Main API endpoints for chat functionality.
"""

import frappe
from frappe import _
from datetime import datetime
import json
from typing import Dict, List, Optional


@frappe.whitelist()
def get_or_create_session() -> Dict:
	"""
	Get active session for current user or create new one.
	
	Returns:
		dict: Session details including name, user, title, status, timestamps, provider info
	
	Raises:
		frappe.throw: If user doesn't have chatbot enabled or settings are disabled
	"""
	user = frappe.session.user
	
	# Permission check: verify user has chatbot enabled in their User record
	user_doc = frappe.get_doc("User", user)
	if not user_doc.get("enable_ai_chatbot"):
		frappe.throw(_("AI Chatbot is not enabled for your account. Please contact System Manager."))
	
	# Global enable check: verify chatbot is enabled system-wide
	settings = frappe.get_single("AI Chatbot Settings")
	if not settings.enabled:
		frappe.throw(_("AI Chatbot is currently disabled. Please contact System Manager."))
	
	# Search for existing active session for this user
	# Ordered by last_activity to get most recent
	active_sessions = frappe.get_all(
		"AI Chat Session",
		filters={
			"user": user,
			"status": "Active"
		},
		order_by="last_activity desc",
		limit=1
	)
	
	if active_sessions:
		# Found existing session - update activity timestamp and return
		session = frappe.get_doc("AI Chat Session", active_sessions[0].name)
		session.update_activity()  # Updates last_activity without modifying created/modified
		return session.as_dict()
	
	# No active session found - create new one
	session = frappe.new_doc("AI Chat Session")
	session.user = user
	session.title = f"Chat on {frappe.format(datetime.now(), {'fieldtype': 'Datetime'})}"
	session.status = "Active"
	session.started_at = datetime.now()
	session.last_activity = datetime.now()
	session.llm_provider = settings.llm_provider  # Snapshot provider at creation time
	session.model_name = _get_model_name(settings)  # Snapshot model at creation time
	session.insert(ignore_permissions=True)  # System creates on behalf of user
	frappe.db.commit()  # Explicit commit to ensure session is saved
	
	return session.as_dict()


@frappe.whitelist()
def create_new_session() -> Dict:
	"""
	Create a brand new session, closing any existing active sessions.
	
	This is different from get_or_create_session() which returns an existing
	active session if one exists. This always creates a fresh session.
	
	Returns:
		dict: New session details
	
	Raises:
		frappe.throw: If user doesn't have chatbot enabled or settings are disabled
	"""
	user = frappe.session.user
	
	# Permission check: verify user has chatbot enabled in their User record
	user_doc = frappe.get_doc("User", user)
	if not user_doc.get("enable_ai_chatbot"):
		frappe.throw(_("AI Chatbot is not enabled for your account. Please contact System Manager."))
	
	# Global enable check: verify chatbot is enabled system-wide
	settings = frappe.get_single("AI Chatbot Settings")
	if not settings.enabled:
		frappe.throw(_("AI Chatbot is currently disabled. Please contact System Manager."))
	
	# Close all existing active sessions for this user
	active_sessions = frappe.get_all(
		"AI Chat Session",
		filters={
			"user": user,
			"status": "Active"
		},
		pluck="name"
	)
	
	for session_id in active_sessions:
		session = frappe.get_doc("AI Chat Session", session_id)
		session.status = "Closed"
		session.save(ignore_permissions=True)
	
	# Create new session
	session = frappe.new_doc("AI Chat Session")
	session.user = user
	session.title = f"Chat on {frappe.format(datetime.now(), {'fieldtype': 'Datetime'})}"
	session.status = "Active"
	session.started_at = datetime.now()
	session.last_activity = datetime.now()
	session.llm_provider = settings.llm_provider
	session.model_name = _get_model_name(settings)
	session.insert(ignore_permissions=True)
	frappe.db.commit()
	
	return session.as_dict()


@frappe.whitelist()
def send_message(session_id: str, message: str, stream: bool = False) -> Dict:
	"""
	Send a message and get complete (non-streaming) response from LLM.
	
	Args:
		session_id: Chat session ID (e.g., "CHAT-SESSION-00001")
		message: User's message text
		stream: Not used here (use stream_chat API for streaming)
	
	Returns:
		dict: {
			"success": bool,
			"message": AI Chat Message document dict with assistant response,
			"session": Updated session document dict with new statistics
		}
	
	Raises:
		frappe.throw: If access denied, rate limit exceeded, or LLM error
	"""
	# Validate session exists and load full document
	session = frappe.get_doc("AI Chat Session", session_id)
	
	# Permission check: only session owner can send messages
	if session.user != frappe.session.user:
		frappe.throw(_("Access denied"))
	
	# Rate limit check: prevent abuse by limiting messages per user
	if not _check_rate_limit(session.user):
		frappe.throw(_("Rate limit exceeded. Please try again later."))
	
	# Save user message to database immediately
	# Not assigned to variable as we only need it persisted
	_save_message(
		session_id=session_id,
		role="user",
		content=message
	)
	
	# Get LLM response through router (handles provider selection and tool calling)
	from frappe_ai_chatbot.llm.router import LLMRouter
	
	router = LLMRouter()  # Router initialized with current settings
	response = router.chat(session_id, message)  # Blocks until complete response
	
	# Save assistant's response to database
	assistant_msg = _save_message(
		session_id=session_id,
		role="assistant",
		content=response["content"],  # Final text response
		tool_calls=response.get("tool_calls"),  # List of tools used (if any)
		token_count=response.get("token_count"),  # Tokens consumed
		model_used=response.get("model")  # Model that generated response
	)
	
	# Update session statistics (total tokens, cost tracking)
	if response.get("token_count"):
		session.add_tokens(response["token_count"], response.get("cost", 0))
	
	# Return complete response with both message and updated session
	return {
		"success": True,
		"message": assistant_msg.as_dict(),  # Message details
		"session": session.as_dict()  # Updated session with new stats
	}


@frappe.whitelist()
def get_messages(session_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
	"""
	Get messages for a session.
	
	Args:
		session_id: Chat session ID
		limit: Number of messages to fetch
		offset: Offset for pagination
	
	Returns:
		list: List of messages
	"""
	# Validate session ownership
	session = frappe.get_doc("AI Chat Session", session_id)
	if session.user != frappe.session.user and not frappe.has_permission("AI Chat Session", ptype="read"):
		frappe.throw(_("Access denied"))
	
	from frappe_ai_chatbot.ai_chatbot.doctype.ai_chat_message.ai_chat_message import get_session_messages
	
	return get_session_messages(session_id, limit, offset)


@frappe.whitelist()
def clear_history(session_id: str) -> Dict:
	"""
	Clear chat history for a session.
	
	Args:
		session_id: Chat session ID
	
	Returns:
		dict: Success response
	"""
	# Validate session ownership
	session = frappe.get_doc("AI Chat Session", session_id)
	if session.user != frappe.session.user:
		frappe.throw(_("Access denied"))
	
	from frappe_ai_chatbot.ai_chatbot.doctype.ai_chat_message.ai_chat_message import delete_session_messages
	
	delete_session_messages(session_id)
	
	# Reset session stats
	session.total_messages = 0
	session.total_tokens = 0
	session.estimated_cost = 0
	session.save(ignore_permissions=True)
	frappe.db.commit()
	
	return {"success": True}


@frappe.whitelist()
def close_session(session_id: str) -> Dict:
	"""
	Close a chat session.
	
	Args:
		session_id: Chat session ID
	
	Returns:
		dict: Success response
	"""
	# Validate session ownership
	session = frappe.get_doc("AI Chat Session", session_id)
	if session.user != frappe.session.user:
		frappe.throw(_("Access denied"))
	
	session.status = "Closed"
	session.save(ignore_permissions=True)
	frappe.db.commit()
	
	return {"success": True}


@frappe.whitelist()
def get_settings() -> Dict:
	"""
	Get chatbot settings (public fields only).
	
	Returns:
		dict: Settings
	"""
	from frappe_ai_chatbot.ai_chatbot.doctype.ai_chatbot_settings.ai_chatbot_settings import get_settings as _get_settings
	
	return _get_settings()


# Helper functions

def _save_message(
	session_id: str,
	role: str,
	content: str,
	tool_calls: Optional[List[Dict]] = None,
	token_count: int = 0,
	model_used: Optional[str] = None,
	tool_call_id: Optional[str] = None,
	tool_name: Optional[str] = None
) -> 'frappe.model.document.Document':
	"""
	Save a message to the database.
	
	Args:
		session_id: Parent chat session ID
		role: Message role ("user", "assistant", "tool")
		content: Message text content
		tool_calls: List of tool calls made (for assistant messages)
		token_count: Number of tokens in this message
		model_used: LLM model that generated this message
		tool_call_id: ID of the tool call this message responds to (for tool role)
		tool_name: Name of the tool that generated this result (for tool role)
	
	Returns:
		Saved AI Chat Message document
	"""
	msg = frappe.new_doc("AI Chat Message")
	msg.session = session_id
	msg.role = role
	msg.content = content
	msg.timestamp = datetime.now()  # Exact time message was created
	msg.token_count = token_count  # For cost tracking
	msg.model_used = model_used  # For auditing which model was used
	
	# Serialize tool calls as JSON string for storage
	# Only save if tool_calls is not None and not empty
	# OpenAI rejects messages with empty tool_calls array
	if tool_calls and len(tool_calls) > 0:
		msg.tool_calls = json.dumps(tool_calls)
	
	# For tool role messages, store the tool_call_id and tool_name
	if role == "tool":
		if tool_call_id:
			msg.tool_call_id = tool_call_id
		if tool_name:
			msg.tool_name = tool_name
	
	msg.insert(ignore_permissions=True)  # System creates on behalf of user
	frappe.db.commit()  # Explicit commit for immediate persistence
	
	return msg


def _check_rate_limit(user: str) -> bool:
	"""
	Check if user has exceeded rate limit.
	
	Args:
		user: User email to check
	
	Returns:
		True if user can send message, False if rate limit exceeded
	"""
	settings = frappe.get_single("AI Chatbot Settings")
	
	# If rate limiting is disabled globally, allow all requests
	if not settings.enable_rate_limiting:
		return True
	
	# Delegate to rate limiter utility (checks Redis cache)
	from frappe_ai_chatbot.utils.rate_limiter import check_rate_limit
	
	return check_rate_limit(user, settings)


def _get_model_name(settings) -> str:
	"""
	Get model name from settings based on provider.
	
	Args:
		settings: AI Chatbot Settings document
	
	Returns:
		Model name string (e.g., "claude-3-5-sonnet-20241022", "gemini-1.5-flash")
	"""
	# Map provider to corresponding model field
	if settings.llm_provider == "Claude":
		return settings.claude_model
	elif settings.llm_provider == "OpenAI":
		return settings.openai_model
	elif settings.llm_provider == "Gemini":
		return settings.gemini_model
	elif settings.llm_provider == "Local":
		return settings.local_model
	else:
		return "unknown"  # Fallback for unknown providers
