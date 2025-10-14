"""
AI Assistant Page

This page provides a full-screen chat interface similar to Claude Desktop,
but embedded in ERPNext. Users can chat with AI assistants powered by
Claude, OpenAI, or local LLMs, with full access to ERPNext data through
Frappe Assistant Core tools.
"""

import frappe


@frappe.whitelist()
def get_page_context():
	"""
	Get context for the AI Assistant page.
	Returns user information and initial settings.
	"""
	return {
		"user": frappe.session.user,
		"user_image": frappe.db.get_value("User", frappe.session.user, "user_image"),
		"full_name": frappe.utils.get_fullname(frappe.session.user)
	}
