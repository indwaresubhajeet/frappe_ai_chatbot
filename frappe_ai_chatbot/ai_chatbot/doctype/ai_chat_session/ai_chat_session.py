"""
AI Chat Session DocType Controller

DocType:
- Stores chat session metadata (user, status, timestamps)
- Tracks usage stats (total_messages, total_tokens, estimated_cost)
- Lifecycle: Active → Closed → Archived

Key Fields:
- user: Owner of session (frappe.session.user)
- status: Active / Closed / Archived
- started_at: Session creation time
- last_activity: Last message timestamp (for timeout detection)
- total_messages: Message count (incremented on each message)
- total_tokens: Token usage (for cost tracking)
- estimated_cost: USD cost estimate

Use Cases:
- Created by api/chat.py when starting new chat
- Updated by api/chat.py after each message (update_activity, add_tokens)
- Archived by scheduled task (hourly cleanup of old sessions)
"""

import frappe
from frappe.model.document import Document
from datetime import datetime


class AIChatSession(Document):
	"""
	AI Chat Session DocType.
	
	Responsibilities:
	- Track session lifecycle (Active → Closed → Archived)
	- Monitor usage (messages, tokens, cost)
	- Auto-set timestamps (started_at, last_activity)
	- Generate default title from timestamp
	"""
	
	def validate(self):
		"""
		Validation logic (called before save).
		
		Auto-sets:
		- started_at: Current time if not set
		- last_activity: Current time if not set
		- title: "Chat on [timestamp]" if not set
		"""
		if not self.started_at:
			self.started_at = datetime.now()
		
		if not self.last_activity:
			self.last_activity = datetime.now()
		
		if not self.title:
			# Generate default title from timestamp
			self.title = f"Chat on {frappe.format(self.started_at, {'fieldtype': 'Datetime'})}"
	
	def update_activity(self):
		"""
		Update last activity timestamp (called after each message).
		
		Used for session timeout detection (e.g., close sessions after 1 hour inactive).
		update_modified=False: Don't update modified timestamp (avoid triggering hooks).
		"""
		frappe.db.set_value(
			"AI Chat Session",
			self.name,
			"last_activity",
			datetime.now(),
			update_modified=False  # Don't trigger on_update hooks
		)
	
	def increment_message_count(self):
		"""
		Increment total message count (called after each user/assistant message).
		
		Used for analytics (messages per session, messages per user).
		"""
		frappe.db.set_value(
			"AI Chat Session",
			self.name,
			"total_messages",
			self.total_messages + 1,
			update_modified=False
		)
	
	def add_tokens(self, token_count: int, cost: float = 0.0):
		"""
		Add tokens and cost to session (called after each LLM request).
		
		Tracks usage for:
		- Rate limiting (tokens per day limit)
		- Cost tracking (estimated USD cost)
		- Analytics (token usage per user/session)
		
		Args:
			token_count: Tokens used in this request (prompt + completion)
			cost: Estimated USD cost for this request
		"""
		frappe.db.set_value(
			"AI Chat Session",
			self.name,
			{
				"total_tokens": self.total_tokens + token_count,
				"estimated_cost": self.estimated_cost + cost
			},
			update_modified=False
		)
	
	def on_trash(self):
		"""
		Cascade delete associated messages before deleting session.
		
		Frappe prevents deletion of documents that have linked child documents.
		This method deletes all AI Chat Messages linked to this session first,
		allowing the session to be deleted without constraint violations.
		"""
		# Delete all messages in this session
		messages = frappe.get_all(
			"AI Chat Message",
			filters={"session": self.name},
			pluck="name"
		)
		
		for message_id in messages:
			frappe.delete_doc("AI Chat Message", message_id, ignore_permissions=True, force=True)
		
		frappe.db.commit()


@frappe.whitelist()
def close_session(session_id: str):
	"""
	Close a chat session (API endpoint for frontend "Close Chat" button).
	
	Sets status to "Closed" (prevents further messages).
	Used when user explicitly ends conversation.
	"""
	doc = frappe.get_doc("AI Chat Session", session_id)
	doc.status = "Closed"
	doc.save()
	return {"success": True}


@frappe.whitelist()
def archive_old_sessions(days: int = 30):
	"""
	Archive sessions older than specified days (called by scheduled task).
	
	Finds sessions:
	- Not already archived
	- last_activity older than N days (default 30)
	
	Sets status to "Archived" (soft delete, can be restored).
	Helps keep database clean and performant.
	
	Args:
		days: Archive sessions older than this many days (default 30)
	
	Returns:
		{"archived_count": N}
	"""
	from frappe.utils import add_days, now_datetime
	
	# Calculate cutoff date (e.g., 30 days ago)
	cutoff_date = add_days(now_datetime(), -days)
	
	# Find old sessions (not archived, last activity before cutoff)
	sessions = frappe.get_all(
		"AI Chat Session",
		filters={
			"status": ["!=", "Archived"],  # Not already archived
			"last_activity": ["<", cutoff_date]  # Older than cutoff
		},
		pluck="name"  # Just get IDs
	)
	
	# Archive each session (set status to "Archived")
	for session in sessions:
		frappe.db.set_value("AI Chat Session", session, "status", "Archived")
	
	frappe.db.commit()  # Persist changes
	
	return {"archived_count": len(sessions)}
