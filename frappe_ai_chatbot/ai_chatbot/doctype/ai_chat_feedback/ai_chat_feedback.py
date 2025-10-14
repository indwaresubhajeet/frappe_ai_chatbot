"""
AI Chat Feedback DocType Controller

DocType:
- Stores user feedback for assistant responses
- Linked to AI Chat Session and AI Chat Message
- Supports multiple feedback types (like, dislike, report)

Key Fields:
- session: Foreign key to AI Chat Session
- message: Foreign key to AI Chat Message (specific response being rated)
- feedback_type: like / dislike / report
- rating: 1-5 stars (optional, for detailed feedback)
- comment: Text comment (optional)
- created_at: Feedback timestamp

Use Cases:
- Created by frontend thumbs up/down buttons
- Used for analytics (satisfaction metrics, model performance)
- Helps identify problematic responses (report)
- Can train future models (fine-tuning on user preferences)
"""

import frappe
from frappe.model.document import Document
from datetime import datetime


class AIChatFeedback(Document):
	"""
	AI Chat Feedback DocType.
	
	Responsibilities:
	- Store user feedback (like/dislike/report)
	- Validate rating range (1-5 stars)
	- Auto-set creation timestamp
	"""
	
	def validate(self):
		"""
		Validation logic (called before save).
		
		Checks:
		- Auto-set created_at if not set
		- Validate rating is 1-5 (if provided)
		"""
		if not self.created_at:
			self.created_at = datetime.now()
		
		# Validate rating if provided (1-5 star scale)
		if self.rating and (self.rating < 1 or self.rating > 5):
			frappe.throw("Rating must be between 1 and 5")


@frappe.whitelist()
def submit_feedback(message_id: str, feedback_type: str, rating: int = None, comment: str = None):
	"""
	Submit feedback for a message (API endpoint for thumbs up/down buttons).
	
	Creates AI Chat Feedback record linked to message and session.
	
	Args:
		message_id: AI Chat Message ID (specific response being rated)
		feedback_type: "like" / "dislike" / "report"
		rating: 1-5 stars (optional, for detailed feedback)
		comment: Text comment (optional, for "report" type)
	
	Returns:
		{"success": True, "feedback_id": "..."}
	"""
	# Validate message exists (prevent feedback on deleted messages)
	if not frappe.db.exists("AI Chat Message", message_id):
		frappe.throw("Message not found")
	
	# Get session from message (link feedback to session)
	message = frappe.get_doc("AI Chat Message", message_id)
	
	# Create feedback record
	feedback = frappe.new_doc("AI Chat Feedback")
	feedback.session = message.session  # Link to session
	feedback.message = message_id  # Link to specific message
	feedback.feedback_type = feedback_type  # like / dislike / report
	feedback.rating = rating  # Optional 1-5 stars
	feedback.comment = comment  # Optional text comment
	feedback.created_at = datetime.now()
	feedback.insert(ignore_permissions=True)
	frappe.db.commit()
	
	return {"success": True, "feedback_id": feedback.name}


@frappe.whitelist()
def get_feedback_stats(session_id: str = None):
	"""
	Get feedback statistics (for analytics dashboard).
	
	Calculates:
	- Total feedback count
	- Like/dislike/report counts
	- Average rating (1-5 stars)
	
	Args:
		session_id: Filter by session (optional, None = all sessions)
	
	Returns:
		Dict with stats
	"""
	filters = {}
	if session_id:
		filters["session"] = session_id  # Filter by specific session
	
	# Get all feedback records (or filtered by session)
	feedbacks = frappe.get_all(
		"AI Chat Feedback",
		filters=filters,
		fields=["feedback_type", "rating"]
	)
	
	# Calculate statistics
	stats = {
		"total": len(feedbacks),
		"likes": len([f for f in feedbacks if f.feedback_type == "like"]),
		"dislikes": len([f for f in feedbacks if f.feedback_type == "dislike"]),
		"reports": len([f for f in feedbacks if f.feedback_type == "report"]),
		"average_rating": 0
	}
	
	# Calculate average rating (only for feedback with ratings)
	ratings = [f.rating for f in feedbacks if f.rating]
	if ratings:
		stats["average_rating"] = sum(ratings) / len(ratings)
	
	return stats
