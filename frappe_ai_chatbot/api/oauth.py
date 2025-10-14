"""
OAuth 2.0 Authorization Code Flow for Frappe Assistant Core integration.

This module implements the proper OAuth flow for users to authorize the chatbot
to access Frappe Assistant Core on their behalf.
"""

import frappe
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode
import httpx


@frappe.whitelist()
def get_authorization_url():
	"""
	Generate OAuth authorization URL with PKCE challenge.
	
	Frontend calls this to get the URL to redirect user for authorization.
	
	Returns:
		dict: Contains authorization_url and state for CSRF protection
	"""
	# Get settings
	settings = frappe.get_doc("AI Chatbot Settings", "AI Chatbot Settings")
	
	if not settings.mcp_oauth_client_id:
		frappe.throw("OAuth Client ID not configured. Please configure in AI Chatbot Settings.")
	
	# Get OAuth endpoints from FAC discovery
	site_url = frappe.utils.get_url()
	
	# Generate PKCE code verifier (43-128 characters)
	code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
	
	# Generate code challenge (SHA256 hash of verifier)
	code_challenge = base64.urlsafe_b64encode(
		hashlib.sha256(code_verifier.encode('utf-8')).digest()
	).decode('utf-8').rstrip('=')
	
	# Generate state for CSRF protection
	state = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
	
	# Store code_verifier and state in session temporarily (10 minutes)
	frappe.cache().set_value(
		f"oauth_verifier_{frappe.session.user}_{state}",
		code_verifier,
		expires_in_sec=600
	)
	
	# Build authorization URL
	redirect_uri = f"{site_url}/api/method/frappe_ai_chatbot.api.oauth.handle_callback"
	
	params = {
		"response_type": "code",
		"client_id": settings.mcp_oauth_client_id,
		"redirect_uri": redirect_uri,
		"scope": "all openid",
		"code_challenge": code_challenge,
		"code_challenge_method": "S256",
		"state": state
	}
	
	# Use Frappe's OAuth authorize endpoint
	authorization_url = f"{site_url}/api/method/frappe.integrations.oauth2.authorize?{urlencode(params)}"
	
	return {
		"authorization_url": authorization_url,
		"state": state
	}


@frappe.whitelist(allow_guest=False)
def handle_callback():
	"""
	Handle OAuth callback after user authorization.
	
	This endpoint receives the authorization code, exchanges it for tokens,
	and stores them for the user.
	
	User must be logged in (Frappe session maintained across OAuth redirect).
	
	Query Parameters:
		code: Authorization code from OAuth server
		state: State parameter for CSRF validation
	"""
	# Get parameters from request
	code = frappe.form_dict.get("code")
	state = frappe.form_dict.get("state")
	error = frappe.form_dict.get("error")
	
	if error:
		frappe.respond_as_web_page(
			"Authorization Failed",
			f"OAuth authorization failed: {error}",
			http_status_code=400
		)
		return
	
	if not code or not state:
		frappe.respond_as_web_page(
			"Invalid Request",
			"Missing authorization code or state parameter",
			http_status_code=400
		)
		return
	
	# User should still be logged in from the authorization flow
	# Frappe maintains session across OAuth redirect
	user = frappe.session.user
	
	if user == "Guest":
		frappe.respond_as_web_page(
			"Authentication Required",
			"Please log in to complete the authorization.",
			http_status_code=401
		)
		return
	
	# Retrieve code_verifier from cache using user and state
	cache_key = f"oauth_verifier_{user}_{state}"
	code_verifier = frappe.cache().get_value(cache_key)
	
	if not code_verifier:
		frappe.respond_as_web_page(
			"Session Expired",
			"Authorization session expired. Please try again.",
			http_status_code=400
		)
		return
	
	# Delete cache key after retrieval (one-time use)
	frappe.cache().delete_value(cache_key)
	
	# Exchange authorization code for tokens
	try:
		tokens = exchange_code_for_tokens(code, code_verifier)
		
		# Store tokens for user
		store_user_tokens(tokens)
		
		# Redirect back to chatbot with success
		redirect_url = f"{frappe.utils.get_url()}/app/ai-assistant?oauth_success=1"
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = redirect_url
		
	except Exception as e:
		frappe.log_error(f"OAuth token exchange failed: {str(e)}", "OAuth Callback Error")
		frappe.respond_as_web_page(
			"Token Exchange Failed",
			f"Failed to exchange authorization code for tokens: {str(e)}",
			http_status_code=500
		)


def exchange_code_for_tokens(code, code_verifier):
	"""
	Exchange authorization code for access and refresh tokens.
	
	Args:
		code: Authorization code from OAuth callback
		code_verifier: PKCE code verifier stored during authorization
		
	Returns:
		dict: Token response with access_token, refresh_token, expires_in
	"""
	settings = frappe.get_doc("AI Chatbot Settings", "AI Chatbot Settings")
	
	site_url = frappe.utils.get_url()
	token_url = settings.mcp_oauth_token_url
	if not token_url.startswith("http"):
		token_url = f"{site_url}{token_url}"
	
	redirect_uri = f"{site_url}/api/method/frappe_ai_chatbot.api.oauth.handle_callback"
	
	# Prepare token request
	data = {
		"grant_type": "authorization_code",
		"code": code,
		"redirect_uri": redirect_uri,
		"code_verifier": code_verifier,
		"client_id": settings.mcp_oauth_client_id
	}
	
	# Add client_secret if configured (for confidential clients)
	if settings.mcp_oauth_client_secret:
		data["client_secret"] = settings.get_password("mcp_oauth_client_secret")
	
	# Make token request
	response = httpx.post(
		token_url,
		data=data,
		timeout=30.0
	)
	
	if response.status_code != 200:
		raise Exception(f"Token request failed: {response.status_code} - {response.text}")
	
	return response.json()


def store_user_tokens(tokens):
	"""
	Store OAuth tokens for the current user.
	
	Args:
		tokens: Token response dict with access_token, refresh_token, expires_in
	"""
	user = frappe.session.user
	
	# Check if user already has tokens stored
	existing = frappe.db.exists("AI Chatbot User Token", {"user": user})
	
	if existing:
		doc = frappe.get_doc("AI Chatbot User Token", existing)
	else:
		doc = frappe.new_doc("AI Chatbot User Token")
		doc.user = user
	
	# Store tokens
	doc.access_token = tokens.get("access_token")
	doc.refresh_token = tokens.get("refresh_token")
	
	# Calculate expiry time (use frappe.utils.now_datetime() for UTC)
	expires_in = tokens.get("expires_in", 3600)  # Default 1 hour
	from frappe.utils import now_datetime
	doc.expires_at = now_datetime() + timedelta(seconds=expires_in)
	
	doc.save(ignore_permissions=True)
	frappe.db.commit()


@frappe.whitelist()
def get_user_token_status():
	"""
	Check if current user has valid OAuth tokens.
	
	Returns:
		dict: Contains has_token (bool) and is_valid (bool)
	"""
	user = frappe.session.user
	
	token_doc = frappe.db.exists("AI Chatbot User Token", {"user": user})
	
	if not token_doc:
		return {
			"has_token": False,
			"is_valid": False
		}
	
	doc = frappe.get_doc("AI Chatbot User Token", token_doc)
	
	# Check if token is expired (use UTC time)
	from frappe.utils import now_datetime
	is_valid = doc.expires_at > now_datetime() if doc.expires_at else False
	
	return {
		"has_token": True,
		"is_valid": is_valid,
		"expires_at": doc.expires_at.isoformat() if doc.expires_at else None
	}


@frappe.whitelist()
def revoke_user_tokens():
	"""
	Revoke and delete OAuth tokens for current user.
	
	Used when user wants to disconnect or re-authorize.
	"""
	user = frappe.session.user
	
	token_doc = frappe.db.exists("AI Chatbot User Token", {"user": user})
	
	if token_doc:
		frappe.delete_doc("AI Chatbot User Token", token_doc, ignore_permissions=True)
		frappe.db.commit()
		return {"success": True, "message": "Tokens revoked successfully"}
	
	return {"success": False, "message": "No tokens found"}
