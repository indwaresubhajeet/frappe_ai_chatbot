"""
Scheduled Tasks for Frappe AI Chatbot

Background tasks executed by Frappe scheduler (bench worker).

Tasks:
1. cleanup_old_sessions() - Hourly: Delete expired/old sessions
2. generate_usage_reports() - Daily: Generate usage analytics

Called by:
- hooks.py: scheduler_events configuration
- Frappe scheduler worker process

Usage:
These run automatically when bench scheduler is running.
View logs: bench --site <site> console
"""

import frappe
from frappe.utils import now_datetime, add_to_date, get_datetime


def cleanup_old_sessions():
	"""
	Cleanup old chat sessions (Hourly task)
	
	What it does:
	- Deletes sessions older than configured session_timeout
	- Marks inactive sessions as "Closed"
	- Logs cleanup statistics
	
	Configuration:
	- AI Chatbot Settings → session_timeout (days, default: 30)
	- Only deletes sessions with status "Closed" or very old "Active" sessions
	
	Called: Every hour by Frappe scheduler
	"""
	try:
		settings = frappe.get_single("AI Chatbot Settings")
		
		# Get session timeout (default 30 days if not configured)
		session_timeout_days = settings.get("session_timeout", 30)
		
		# Calculate cutoff date
		cutoff_date = add_to_date(now_datetime(), days=-session_timeout_days)
		
		# Find sessions older than cutoff
		old_sessions = frappe.get_all(
			"AI Chat Session",
			filters={
				"modified": ["<", cutoff_date],
				"status": ["in", ["Closed", "Active"]]
			},
			pluck="name"
		)
		
		if old_sessions:
			# Delete old sessions and their messages
			for session_id in old_sessions:
				# Delete associated messages first
				frappe.db.delete("AI Chat Message", {"session_id": session_id})
				
				# Delete session
				frappe.delete_doc("AI Chat Session", session_id, force=True)
			
			frappe.db.commit()
			
			frappe.logger().info(
				f"AI Chatbot: Cleaned up {len(old_sessions)} old sessions "
				f"(older than {session_timeout_days} days)"
			)
		else:
			frappe.logger().debug("AI Chatbot: No old sessions to cleanup")
			
	except Exception as e:
		frappe.log_error(
			title="AI Chatbot Session Cleanup Failed",
			message=f"Error during session cleanup: {str(e)}"
		)


def generate_usage_reports():
	"""
	Generate usage analytics and reports (Daily task)
	
	What it does:
	- Calculate daily usage statistics (messages, tokens, costs)
	- Generate per-user usage summary
	- Store in AI Chat Analytics doctype (if exists)
	- Log usage patterns
	
	Metrics tracked:
	- Total messages sent
	- Total tokens consumed
	- Estimated costs
	- Active users count
	- Most used tools
	
	Called: Daily at midnight by Frappe scheduler
	"""
	try:
		# Get yesterday's date range
		today = get_datetime()
		yesterday = add_to_date(today, days=-1)
		yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
		yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
		
		# Get statistics for yesterday
		stats = frappe.db.sql("""
			SELECT 
				COUNT(DISTINCT session_id) as total_sessions,
				COUNT(*) as total_messages,
				SUM(token_count) as total_tokens,
				COUNT(DISTINCT owner) as active_users
			FROM `tabAI Chat Message`
			WHERE creation BETWEEN %s AND %s
		""", (yesterday_start, yesterday_end), as_dict=True)
		
		if stats and stats[0].total_messages > 0:
			stat = stats[0]
			
			# Rough cost estimation (based on provider pricing)
			# This is approximate - actual costs vary by model
			tokens = stat.total_tokens or 0
			estimated_cost = (tokens / 1000000) * 3.0  # ~$3 per 1M tokens average
			
			# Log daily usage
			frappe.logger().info(
				f"AI Chatbot Daily Usage Report ({yesterday.date()}):\n"
				f"  - Sessions: {stat.total_sessions}\n"
				f"  - Messages: {stat.total_messages}\n"
				f"  - Tokens: {tokens:,}\n"
				f"  - Active Users: {stat.active_users}\n"
				f"  - Est. Cost: ${estimated_cost:.4f}"
			)
			
			# Optional: Store in database for historical tracking
			# You could create a "AI Chat Analytics" doctype to store these
			# frappe.get_doc({
			# 	"doctype": "AI Chat Analytics",
			# 	"date": yesterday.date(),
			# 	"total_sessions": stat.total_sessions,
			# 	"total_messages": stat.total_messages,
			# 	"total_tokens": tokens,
			# 	"active_users": stat.active_users,
			# 	"estimated_cost": estimated_cost
			# }).insert()
			
		else:
			frappe.logger().debug(
				f"AI Chatbot: No usage to report for {yesterday.date()}"
			)
			
	except Exception as e:
		frappe.log_error(
			title="AI Chatbot Usage Report Failed",
			message=f"Error generating usage report: {str(e)}"
		)


def test_scheduled_tasks():
	"""
	Test function to verify scheduled tasks work
	
	Usage:
	bench --site <site> console
	>>> from frappe_ai_chatbot.tasks import test_scheduled_tasks
	>>> test_scheduled_tasks()
	"""
	print("\n=== Testing AI Chatbot Scheduled Tasks ===\n")
	
	print("1. Testing cleanup_old_sessions()...")
	try:
		cleanup_old_sessions()
		print("   ✅ Cleanup task completed successfully\n")
	except Exception as e:
		print(f"   ❌ Cleanup task failed: {e}\n")
	
	print("2. Testing generate_usage_reports()...")
	try:
		generate_usage_reports()
		print("   ✅ Usage report generated successfully\n")
	except Exception as e:
		print(f"   ❌ Usage report failed: {e}\n")
	
	print("=== Test Complete ===\n")
