"""
AI Chatbot Settings DocType Controller

Singleton DocType:
- Only one record exists (configuration for entire chatbot)
- Stores LLM API keys (encrypted in database)
- Configures provider, model, temperature, max_tokens, etc.
- Accessed via frappe.get_single("AI Chatbot Settings")

Key Features:
- Validation: Ensure API keys provided for selected provider
- Range validation: temperature (0-2), top_p (0-1), max_tokens (>0)
- API key security: Stored encrypted, not sent to frontend
- Connection testing: Test LLM provider connectivity

Use Cases:
- Admin configures chatbot settings in desk UI
- llm/router.py loads settings to initialize adapters
- api/chat.py checks settings to validate configuration
"""

import frappe
from frappe.model.document import Document


class AIChatbotSettings(Document):
	"""
	AI Chatbot Settings DocType (Single).
	
	Responsibilities:
	- Validate configuration before save
	- Ensure API keys provided for selected provider
	- Validate numeric ranges (temperature, top_p, max_tokens)
	- Store settings securely (API keys encrypted)
	"""
	
	def validate(self):
		"""
		Validation logic (called before save).
		
		Checks:
		- API keys provided for selected provider (claude_api_key, openai_api_key, local_endpoint)
		- Numeric ranges valid (temperature 0-2, top_p 0-1, max_tokens >0)
		- Displays warnings for missing API keys (msgprint)
		- Throws errors for invalid ranges (frappe.throw)
		"""
		# Validate API keys are provided for selected provider
		if self.llm_provider == "Claude" and not self.claude_api_key:
			frappe.msgprint(
				"Claude API Key is required when using Claude as LLM provider",
				indicator="orange",  # Orange warning
				alert=True  # Show as alert
			)
		
		if self.llm_provider == "OpenAI" and not self.openai_api_key:
			frappe.msgprint(
				"OpenAI API Key is required when using OpenAI as LLM provider",
				indicator="orange",
				alert=True
			)
		
		if self.llm_provider == "Gemini" and not self.gemini_api_key:
			frappe.msgprint(
				"Gemini API Key is required when using Gemini as LLM provider. Get free key at https://makersuite.google.com/app/apikey",
				indicator="orange",
				alert=True
			)
		
		if self.llm_provider == "Local" and not self.local_endpoint:
			frappe.msgprint(
				"Local Endpoint is required when using Local as LLM provider",
				indicator="orange",
				alert=True
			)
		
		# Validate numeric ranges (throw errors for invalid values)
		if self.temperature < 0 or self.temperature > 2:
			frappe.throw("Temperature must be between 0 and 2")
		
		if self.top_p < 0 or self.top_p > 1:
			frappe.throw("Top P must be between 0 and 1")
		
		if self.max_tokens < 1:
			frappe.throw("Max Tokens must be greater than 0")
		
		# Validate OAuth configuration (always required - FAC only accepts OAuth)
		if not self.get("mcp_oauth_client_id"):
			frappe.msgprint(
				"OAuth Client ID is required. Create an OAuth Client in Frappe (OAuth Client DocType) "
				"and enter the Client ID here.",
				indicator="orange",
				alert=True
			)
		
		if not self.get("mcp_oauth_client_secret"):
			frappe.msgprint(
				"OAuth Client Secret is required. Get this from your OAuth Client record.",
				indicator="orange",
				alert=True
			)
		
		if not self.get("mcp_oauth_token_url"):
			frappe.msgprint(
				"OAuth Token URL is required. Default: /api/method/frappe.integrations.oauth2.get_token",
				indicator="orange",
				alert=True
			)


@frappe.whitelist()
def get_settings():
	"""
	Get AI Chatbot Settings (API endpoint for frontend).
	
	Security:
	- Removes API keys before sending to frontend (pop claude_api_key, openai_api_key)
	- Whitelisted (accessible from JavaScript)
	
	Auto-creates settings if not exist (first-time setup).
	"""
	if not frappe.db.exists("AI Chatbot Settings", "AI Chatbot Settings"):
		# Create default settings if not exist (first-time setup)
		doc = frappe.new_doc("AI Chatbot Settings")
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	
	settings = frappe.get_single("AI Chatbot Settings")
	
	# Don't send API keys to frontend (security: prevent leaking keys)
	settings_dict = settings.as_dict()
	settings_dict.pop("claude_api_key", None)  # Remove Claude key
	settings_dict.pop("openai_api_key", None)  # Remove OpenAI key
	
	return settings_dict


@frappe.whitelist()
def test_mcp_connection():
	"""
	Test MCP endpoint connection (API endpoint for UI "Test MCP Connection" button).
	
	Tests connectivity to Frappe_Assistant_Core MCP endpoint.
	Validates authentication mode and returns connection status.
	
	Returns:
	  {"success": True/False, "message": "...", "details": {...}}
	"""
	from frappe_ai_chatbot.mcp.client import MCPClient
	
	try:
		client = MCPClient()
		result = client.test_connection()
		
		if result.get("success"):
			# Get additional info
			details = {
				"auth_mode": client.auth_mode,
				"endpoint": client.endpoint,
				"server_name": result.get("server_info", {}).get("name"),
				"server_version": result.get("server_info", {}).get("version"),
				"protocol_version": result.get("server_info", {}).get("protocolVersion")
			}
			
			return {
				"success": True,
				"message": f"✅ Connected successfully to {details['server_name']} v{details['server_version']}",
				"details": details
			}
		else:
			return result
	
	except Exception as e:
		frappe.log_error(f"MCP connection test failed: {str(e)}", "MCP Connection Test")
		return {
			"success": False,
			"message": f"❌ Connection failed: {str(e)}"
		}


@frappe.whitelist()
def test_llm_connection(provider: str = None):
	"""
	Test LLM provider connection (API endpoint for UI "Test Connection" button).
	
	Tests connectivity for Claude, OpenAI, Gemini, or Local provider.
	Makes minimal test request (10 tokens max) to verify API key and endpoint.
	
	Returns:
	  {"success": True/False, "message": "..."}
	"""
	settings = frappe.get_single("AI Chatbot Settings")
	
	if not provider:
		provider = settings.llm_provider  # Use default provider if not specified
	
	try:
		if provider == "Claude":
			if not settings.claude_api_key:
				return {"success": False, "message": "Claude API Key not configured"}
			
			import anthropic
			# Test Claude API connection
			client = anthropic.Anthropic(api_key=settings.get_password("claude_api_key"))
			response = client.messages.create(
				model=settings.claude_model,
				max_tokens=10,  # Minimal request (cheap test)
				messages=[{"role": "user", "content": "test"}]
			)
			return {"success": True, "message": "Connected to Claude successfully"}
		
		elif provider == "OpenAI":
			if not settings.openai_api_key:
				return {"success": False, "message": "OpenAI API Key not configured"}
			
			from openai import OpenAI
			# Test OpenAI API connection
			client = OpenAI(api_key=settings.get_password("openai_api_key"))
			response = client.chat.completions.create(
				model=settings.openai_model,
				max_tokens=10,  # Minimal request (cheap test)
				messages=[{"role": "user", "content": "test"}]
			)
			return {"success": True, "message": "Connected to OpenAI successfully"}
		
		elif provider == "Local":
			if not settings.local_endpoint:
				return {"success": False, "message": "Local endpoint not configured"}
			
			import httpx
			# Test local endpoint (Ollama /api/tags to list models)
			response = httpx.get(f"{settings.local_endpoint}/api/tags", timeout=5.0)
			if response.status_code == 200:
				return {"success": True, "message": "Connected to local endpoint successfully"}
			else:
				return {"success": False, "message": f"Local endpoint returned status {response.status_code}"}
		
		else:
			return {"success": False, "message": f"Unknown provider: {provider}"}
	
	except Exception as e:
		# Log error and return failure message
		frappe.log_error(f"LLM connection test failed: {str(e)}", "AI Chatbot")
		return {"success": False, "message": f"Connection failed: {str(e)}"}
