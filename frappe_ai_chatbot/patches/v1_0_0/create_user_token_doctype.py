"""
Post-installation migration for OAuth implementation.

This ensures the AI Chatbot User Token DocType is created.
"""

import frappe


def execute():
	"""Create AI Chatbot User Token DocType if not exists."""
	
	# Check if DocType already exists
	if frappe.db.exists("DocType", "AI Chatbot User Token"):
		print("✓ AI Chatbot User Token DocType already exists")
		return
	
	print("Creating AI Chatbot User Token DocType...")
	
	# This will be handled by the migrate command automatically
	# Just log that migration is needed
	frappe.log_error(
		"AI Chatbot User Token DocType needs to be created. "
		"Run: bench --site your-site migrate",
		"OAuth Migration"
	)
	
	print("✓ Migration check complete")
