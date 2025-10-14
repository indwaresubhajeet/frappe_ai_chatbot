"""
Add tool_call_id field to AI Chat Message DocType
This field is needed to link tool results back to their tool calls
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
	"""Add tool_call_id field to AI Chat Message"""
	
	# Check if field already exists
	if frappe.db.exists("Custom Field", {"dt": "AI Chat Message", "fieldname": "tool_call_id"}):
		print("tool_call_id field already exists, skipping...")
		return
	
	custom_fields = {
		"AI Chat Message": [
			{
				"fieldname": "tool_call_id",
				"label": "Tool Call ID",
				"fieldtype": "Data",
				"insert_after": "role",
				"read_only": 1,
				"description": "ID linking tool result messages to their tool calls"
			}
		]
	}
	
	create_custom_fields(custom_fields, update=True)
	print("✅ Added tool_call_id field to AI Chat Message")
