"""
Setup module for Frappe AI Chatbot - Handles post-installation tasks

Key Features:
- Automatic post-install setup (after `bench install-app frappe_ai_chatbot`)
- Create custom fields on User doctype (enable_ai_chatbot checkbox)
- Initialize AI Chatbot Settings with sensible defaults
- Database commit to persist changes

Post-Install Tasks:
1. create_custom_fields(): Add enable_ai_chatbot checkbox to User doctype
2. create_default_settings(): Create AI Chatbot Settings with default config
3. Database commit (persist all changes)

Use Cases:
- First-time installation: Automatically configure everything
- Zero manual configuration needed to get started
- User can override defaults in AI Chatbot Settings UI

Frappe Hook:
- after_install hook in hooks.py calls after_install()
- Runs automatically during `bench install-app` command
"""

import frappe
from frappe import _


def after_install():
	"""
	Run after app installation (called by Frappe hooks).
	
	Creates all necessary custom fields and default settings.
	Users can immediately start using chatbot after installation.
	"""
	create_custom_fields()  # Add custom fields to User doctype
	create_default_settings()  # Initialize AI Chatbot Settings
	frappe.db.commit()  # Persist changes to database
	
	print("✅ Frappe AI Chatbot installed successfully!")
	print("📝 Please configure AI Chatbot Settings to set up your LLM provider.")


def create_custom_fields():
	"""
	Create custom fields on User doctype (enable_ai_chatbot checkbox).
	
	Adds checkbox to User form to enable/disable chatbot per user.
	Admin can control which users have access to AI chatbot.
	"""
	# Check if custom field already exists (avoid duplicates)
	if not frappe.db.exists("Custom Field", {"dt": "User", "fieldname": "enable_ai_chatbot"}):
		custom_field = frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "User",  # Add field to User doctype
			"fieldname": "enable_ai_chatbot",
			"label": "Enable AI Chatbot",
			"fieldtype": "Check",  # Boolean checkbox
			"insert_after": "enabled",  # Position in form
			"default": "1",  # Enabled by default
			"description": "Enable AI chatbot widget for this user"
		})
		custom_field.insert(ignore_permissions=True)  # Insert even if no perms


def create_default_settings():
	"""
	Create default AI Chatbot Settings (singleton doctype).
	
	Initializes all settings with sensible defaults:
	- Default provider: Claude (claude-3-5-sonnet-20241022)
	- Streaming enabled, markdown enabled
	- Context window: 10 messages
	- Rate limiting: 50 messages/hour per user
	- Tool caching: 5-minute TTL
	- Comprehensive system prompt with ERPNext context
	
	Users can override any settings in AI Chatbot Settings UI.
	"""
	# Check if settings already exist (singleton, should only have 1 record)
	if not frappe.db.exists("AI Chatbot Settings"):
		settings = frappe.get_doc({
			"doctype": "AI Chatbot Settings",
			"enabled": 1,  # Enabled by default (matches DocType field name)
			"llm_provider": "Gemini",  # Free tier for testing
			"gemini_model": "gemini-1.5-flash",  # Fast and free
			"claude_model": "claude-3-5-sonnet-20241022",  # Latest Sonnet
			"openai_model": "gpt-4o",  # Latest GPT-4o
			"welcome_message": "Hi! I'm your AI assistant. How can I help you today?",
			"max_tokens": 4096,  # Reasonable response length
			"temperature": 0.7,  # Balance creativity and accuracy
			"top_p": 0.9,  # Default top_p
			"context_window_size": 10,  # Last 10 messages
			"enable_streaming": 1,  # Real-time responses (SSE)
			"enable_markdown_rendering": 1,  # Rich formatting (correct field name)
			"enable_tool_calling": 1,  # Enable tool calling
			"enable_rate_limiting": 1,  # Enable rate limiting
			"messages_per_hour": 50,  # 50 messages/hour per user
			"tokens_per_day": 100000,  # 100K tokens per day
			"max_concurrent_requests": 5,  # Max concurrent requests
			"enable_tool_caching": 1,  # Cache tool results
			"tool_cache_ttl": 300,  # 5-minute cache
			"mcp_endpoint": "/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp",  # MCP endpoint
			# OAuth credentials must be configured manually (see README.md for instructions)
			"mcp_oauth_client_id": "",  # Enter your OAuth Client ID
			"mcp_oauth_client_secret": "",  # Enter your OAuth Client Secret  
			"mcp_oauth_token_url": "/api/method/frappe.integrations.oauth2.get_token",  # Frappe's OAuth token endpoint
			"system_prompt": """You are a helpful AI assistant integrated with ERPNext, a comprehensive ERP system.

You have access to various tools that let you interact with the ERP data:
- Create, read, update, and delete documents
- Search and filter data
- Generate reports and analytics
- Execute workflows
- And more

When responding:
1. Be professional and accurate
2. Always verify data before making changes
3. Explain what you're doing when using tools
4. Format responses clearly with proper structure
5. Ask for clarification if user requests are ambiguous

Current user context:
- User: {user}
- Company: {company}
- Role: {role}

Always respect user permissions - you can only access what the user is authorized to see.""",
			"log_level": "INFO"  # Standard logging
		})
		settings.insert(ignore_permissions=True)  # Insert even if no perms
