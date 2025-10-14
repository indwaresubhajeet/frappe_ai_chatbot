"""
AI Chat Message DocType Controller

DocType:
- Stores individual messages in conversation
- Linked to AI Chat Session (parent session)
- Supports all roles (user, assistant, system, tool)

Key Fields:
- session: Foreign key to AI Chat Session
- role: user / assistant / system / tool
- content: Message text (user query or assistant response)
- tool_calls: JSON string (assistant tool calls, e.g., [{"name": "search", "arguments": {...}}])
- tool_call_id: ID for tool result messages (role=tool)
- name: Tool name for tool result messages (role=tool)
- token_count: Tokens used in this message
- timestamp: Message creation time

Use Cases:
- Created by api/chat.py for each user/assistant/tool message
- Loaded by utils/context_manager.py for conversation context
- Auto-updates parent session (increment_message_count, add_tokens)
"""

import frappe
from frappe.model.document import Document
from datetime import datetime
import json


class AIChatMessage(Document):
	"""
	AI Chat Message DocType.
	
	Responsibilities:
	- Store message content and metadata
	- Validate JSON fields (tool_calls, metadata)
	- Update parent session after insert (message count, token count, last activity)
	"""
	
	def validate(self):
		"""
		Validation logic (called before save).
		
		Checks:
		- Auto-set timestamp if not set
		- Validate tool_calls JSON (must be valid JSON string)
		- Validate metadata JSON (must be valid JSON string)
		"""
		if not self.timestamp:
			self.timestamp = datetime.now()
		
		# Validate tool_calls JSON (assistant tool calling messages)
		if self.tool_calls:
			try:
				if isinstance(self.tool_calls, str):
					json.loads(self.tool_calls)  # Parse to validate
			except json.JSONDecodeError:
				frappe.throw("Invalid JSON in tool_calls field")
		
		# Validate metadata JSON (custom metadata)
		if self.metadata:
			try:
				if isinstance(self.metadata, str):
					json.loads(self.metadata)  # Parse to validate
			except json.JSONDecodeError:
				frappe.throw("Invalid JSON in metadata field")
	
	def after_insert(self):
		"""
		After insert hook (called after message saved to database).
		
		Updates parent session:
		- Increment message count
		- Update last activity timestamp
		- Add token count to session total
		
		Errors are logged but don't break message creation.
		"""
		# Update parent session (increment counters, update timestamp)
		try:
			session = frappe.get_doc("AI Chat Session", self.session)
			session.increment_message_count()  # total_messages += 1
			session.update_activity()  # last_activity = now()
			
			if self.token_count:
				session.add_tokens(self.token_count)  # total_tokens += token_count
		except Exception as e:
			# Log error but don't fail (message creation should succeed even if session update fails)
			frappe.log_error(
				f"Error updating session after message insert: {str(e)}",
				"AI Chat Message"
			)


@frappe.whitelist()
def get_session_messages(session_id: str, limit: int = 50, offset: int = 0):
	"""
	Get messages for a session (API endpoint for frontend).
	
	Supports pagination (limit + offset for lazy loading).
	Parses tool_calls JSON to native dict/list.
	
	Args:
		session_id: AI Chat Session ID
		limit: Max messages to return (default 50)
		offset: Skip first N messages (default 0)
	
	Returns:
		List of message dicts
	"""
	messages = frappe.get_all(
		"AI Chat Message",
		filters={"session": session_id},
		fields=["name", "role", "content", "timestamp", "token_count", "tool_calls"],
		order_by="timestamp asc",  # Chronological order (oldest first)
		limit=limit,
		start=offset
	)
	
	# Parse JSON fields (tool_calls string → dict/list)
	for msg in messages:
		if msg.get("tool_calls"):
			try:
				msg["tool_calls"] = json.loads(msg["tool_calls"])
			except Exception:
				msg["tool_calls"] = None  # Ignore malformed JSON
	
	return messages


@frappe.whitelist()
def delete_session_messages(session_id: str):
	"""
	Delete all messages for a session (API endpoint for "Clear History" button).
	
	Hard delete (removes from database, not archival).
	Use with caution (cannot be undone).
	"""
	frappe.db.delete("AI Chat Message", {"session": session_id})
	frappe.db.commit()
	
	return {"success": True}
