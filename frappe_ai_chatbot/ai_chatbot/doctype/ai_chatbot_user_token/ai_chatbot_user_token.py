# Copyright (c) 2025, [Your Company] and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIChatbotUserToken(Document):
	"""Stores OAuth tokens for users to access Frappe Assistant Core."""
	
	def before_insert(self):
		"""Set created_at timestamp on insert."""
		self.created_at = frappe.utils.now_datetime()
	
	def before_save(self):
		"""Update last_refreshed when token is updated."""
		if self.has_value_changed("access_token"):
			self.last_refreshed = frappe.utils.now_datetime()
