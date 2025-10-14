"""
Frappe AI Chatbot - Embedded AI Assistant for ERPNext

Frappe Hooks Configuration:
- Defines app metadata (name, title, description, version)
- Includes JavaScript in desk (ai_assistant_launcher.js)
- Post-install hook (calls setup.after_install)
- Scheduled tasks (hourly session cleanup, daily usage reports)
- Fixtures (exports Custom Field for User doctype)

Key Hooks:
1. app_include_js: Loads chat widget launcher on every page
2. after_install: Runs setup.after_install() to create custom fields and settings
3. scheduler_events: Hourly cleanup + daily reports
4. fixtures: Exports enable_ai_chatbot custom field (for migrations)

Use Cases:
- Frappe automatically reads this file during bench start
- Controls what JavaScript/CSS is loaded
- Defines scheduled background tasks
- Exports configuration for bench migrate
"""

from . import __version__ as app_version

# App metadata (shown in desk, used by Frappe)
app_name = "frappe_ai_chatbot"
app_title = "Frappe AI Chatbot"
app_description = "Embedded AI chatbot for ERPNext with LLM integration"
app_icon = "octicon octicon-comment-discussion"  # GitHub Octicon
app_color = "blue"
app_version = app_version

# Includes in <head>
# ------------------

# Include JS in desk.html (loads on every page)
# ai_assistant_launcher.js: Navbar button + keyboard shortcuts (Ctrl+Shift+A) for full-page interface
# ai_chat_widget.js: Floating chat bubble widget (bottom-right corner) - RECOMMENDED PRIMARY UI
app_include_js = [
	# TEMPORARILY DISABLED: Full-page AI Assistant interface (/app/ai-assistant)
	# Uncomment the line below to re-enable navbar button, Ctrl+Shift+A shortcut, and full-page UI
	# Reason for disabling: Floating widget provides better UX, full-page can be revisited later
	# To re-enable: Uncomment line below, run `bench build --app frappe_ai_chatbot`, restart bench
	"/assets/frappe_ai_chatbot/js/ai_assistant_launcher.js",
	
	# ENABLED: Floating chat widget (primary UI)
	# This provides the chat bubble in bottom-right corner on all pages
	"/assets/frappe_ai_chatbot/js/ai_chat_widget.js"
]

# include js, css files in header of web template
# web_include_css = "/assets/frappe_ai_chatbot/css/frappe_ai_chatbot.css"
# web_include_js = "/assets/frappe_ai_chatbot/js/frappe_ai_chatbot.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_ai_chatbot/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jenv = {
#	"methods": [
#		"frappe_ai_chatbot.utils.jinja.method_name"
#	],
#	"filters": [
#		"frappe_ai_chatbot.utils.jinja.filter_name"
#	]
# }

# Installation
# ------------

# Post-install hook: Runs after `bench install-app frappe_ai_chatbot`
# Creates custom fields (enable_ai_chatbot on User) and default settings
after_install = "frappe_ai_chatbot.setup.after_install"

# Uninstallation
# ------------

# before_uninstall = "frappe_ai_chatbot.uninstall.before_uninstall"
# after_uninstall = "frappe_ai_chatbot.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_ai_chatbot.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
#	"*": {
#		"on_update": "method",
#		"on_cancel": "method",
#		"on_trash": "method"
#	}
# }

# Scheduled Tasks
# ---------------

# Background tasks run by Frappe scheduler (bench worker)
scheduler_events = {
	"hourly": [
		"frappe_ai_chatbot.tasks.cleanup_old_sessions"  # Delete expired sessions (session_timeout)
	],
	"daily": [
		"frappe_ai_chatbot.tasks.generate_usage_reports"  # Daily usage analytics (tokens, messages, costs)
	]
}

# Testing
# -------

# before_tests = "frappe_ai_chatbot.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#	"frappe.desk.doctype.event.event.get_events": "frappe_ai_chatbot.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "frappe_ai_chatbot.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

# user_data_fields = [
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"frappe_ai_chatbot.auth.validate"
# ]

# Boot Session
# ----------------

# boot_session = "frappe_ai_chatbot.boot.boot_session"

# Fixtures
# --------

# Fixtures: Export configuration for bench migrate
# These records are exported to JSON files in fixtures/ directory
# Used for migrating configuration between sites (dev → staging → production)
fixtures = [
    {
        "doctype": "Custom Field",  # Export Custom Field records
        "filters": [
            ["dt", "in", ["User"]],  # Only User doctype custom fields
            ["fieldname", "in", ["enable_ai_chatbot"]]  # Only this specific field
        ]
    }
]
