"""
MCP Client

Client for communicating with Frappe_Assistant_Core's MCP endpoint.
Implements JSON-RPC 2.0 protocol for Model Context Protocol (MCP) communication.

MCP enables LLMs to access tools provided by external servers.
This client connects to Frappe_Assistant_Core's MCP endpoint to:
	- List available tools (get_document, update_document, search, etc.)
	- Execute tools with arguments
	- Get tool results

Protocol: JSON-RPC 2.0 over HTTP
Reference: https://spec.modelcontextprotocol.io/
"""

import frappe
import json
from typing import Dict, List, Optional, Any
import uuid


class MCPClient:
	"""
	JSON-RPC 2.0 client for Model Context Protocol communication.
	
	Responsibilities:
		- Initialize connection with MCP server (handshake)
		- List available tools from server
		- Execute tools with arguments
		- Handle JSON-RPC request/response flow
		- Cache tool definitions for performance
	
	Connection Flow:
		1. Client sends initialize request
		2. Server responds with capabilities and server info
		3. Client can now list tools and execute them
	"""
	
	def __init__(self):
		"""
		Initialize MCP client with endpoint from AI Chatbot Settings.
		
		Loads MCP endpoint URL and retrieves OAuth access token for current user.
		Uses OAuth 2.0 Bearer tokens (required by FAC - no other auth mode supported).
		
		Does not establish connection until first use (lazy initialization).
		"""
		from datetime import datetime
		
		self.settings = frappe.get_single("AI Chatbot Settings")
		self.endpoint = self.settings.mcp_endpoint
		self.initialized = False
		self.server_info = None
		self.access_token = None
		
		# Load user's OAuth tokens from database
		# Wrapped in try-except to handle cases where DocType doesn't exist yet (pre-migration)
		try:
			user = frappe.session.user
			
			# Check if AI Chatbot User Token DocType exists
			if not frappe.db.exists("DocType", "AI Chatbot User Token"):
				frappe.logger().warning("AI Chatbot User Token DocType not found. Run: bench --site your-site migrate")
				return
			
			token_doc_name = frappe.db.exists("AI Chatbot User Token", {"user": user})
			
			if token_doc_name:
				token_doc = frappe.get_doc("AI Chatbot User Token", token_doc_name)
				
				# Check if token is still valid (use UTC time)
				from frappe.utils import now_datetime
				if token_doc.expires_at and token_doc.expires_at > now_datetime():
					self.access_token = token_doc.get_password("access_token")
				else:
					# Token expired, will need to refresh on first use
					frappe.logger().info(f"OAuth token expired for user {user}, will refresh on first request")
			else:
				frappe.logger().info(f"No OAuth token found for user {user}. User needs to authorize via chatbot.")
		
		except Exception as e:
			frappe.logger().error(f"Error loading OAuth tokens: {str(e)}")
			# Don't fail initialization - user can still authorize later
	
	def initialize(self) -> Dict:
		"""
		Perform MCP protocol handshake with server.
		
		Handshake establishes protocol version and exchanges capability information.
		Only performed once (subsequent calls return cached server_info).
		
		JSON-RPC Request:
			{
				"jsonrpc": "2.0",
				"method": "initialize",
				"params": {
					"protocolVersion": "2024-11-05",
					"capabilities": {"roots": {"listChanged": false}},
					"clientInfo": {"name": "frappe_ai_chatbot", "version": "1.0.0"}
				},
				"id": <uuid>
			}
		
		Returns:
			Server info dict containing:
				- protocolVersion: Server's protocol version
				- capabilities: Server's supported features
				- serverInfo: Name and version
		"""
		if self.initialized:
			return self.server_info  # Already initialized, return cached info
		
		try:
			# Construct JSON-RPC 2.0 initialize request
			request = {
				"jsonrpc": "2.0",  # JSON-RPC version
				"method": "initialize",  # MCP handshake method
				"params": {
					"protocolVersion": "2025-03-26",  # MCP protocol version (MUST match FAC)
					"capabilities": {
						"roots": {
							"listChanged": False  # We don't support dynamic root changes
						}
					},
					"clientInfo": {
						"name": "frappe_ai_chatbot",
						"version": "1.0.0"
					}
				},
				"id": self._generate_id()  # Unique request ID
			}
			
			# Send request to MCP endpoint
			response = self._call_endpoint(request)
			
			# Check for JSON-RPC errors
			if "error" in response:
				raise Exception(f"MCP initialization failed: {response['error']}")
			
			# Extract result from JSON-RPC response
			self.server_info = response.get("result", {})
			self.initialized = True
			
			return self.server_info
		
		except Exception as e:
			# Log initialization errors for debugging
			frappe.log_error(f"MCP initialization error: {str(e)}", "MCP Client")
			raise
	
	def list_tools(self, use_cache: bool = True) -> List[Dict]:
		"""
		List all available tools from MCP server.
		
		Tools are operations that LLMs can execute (e.g., get_document, search, update_document).
		Each tool has:
			- name: Tool identifier
			- description: What the tool does
			- inputSchema: JSON Schema defining required/optional parameters
		
		Caching Strategy:
			- Tools are cached per user (tools depend on permissions)
			- Cache key: "mcp_tools_{user}"
			- Cache TTL: Defined in settings
			- Cache can be bypassed with use_cache=False
		
		Args:
			use_cache: If True, return cached tools (if available). If False, fetch fresh from server.
		
		Returns:
			List of tool definitions (each is a dict with name, description, inputSchema)
		"""
		# Check cache first if enabled (performance optimization)
		if use_cache and self.settings.enable_tool_caching:
			cache_key = f"mcp_tools_{frappe.session.user}"  # User-specific cache
			cached_tools = frappe.cache().get_value(cache_key)
			
			if cached_tools:
				return json.loads(cached_tools)  # Return cached tools
		
		try:
			# Ensure connection is initialized before making requests
			if not self.initialized:
				self.initialize()  # Perform handshake if not done yet
			
			# Construct JSON-RPC request to list tools
			request = {
				"jsonrpc": "2.0",
				"method": "tools/list",  # MCP method for listing tools
				"params": {},  # No parameters needed
				"id": self._generate_id()
			}
			
			# Send request to MCP server
			response = self._call_endpoint(request)
			
			# Check for JSON-RPC errors
			if "error" in response:
				raise Exception(f"Failed to list tools: {response['error']}")
			
			# Extract tools from response
			tools = response.get("result", {}).get("tools", [])
			
			# Cache tools if enabled (improves performance on subsequent calls)
			if use_cache and self.settings.enable_tool_caching:
				cache_key = f"mcp_tools_{frappe.session.user}"
				frappe.cache().set_value(
					cache_key,
					json.dumps(tools),  # Serialize for storage
					expires_in_sec=self.settings.tool_cache_ttl  # TTL from settings
				)
			
			return tools
		
		except Exception as e:
			# Log tool listing errors
			frappe.log_error(f"Failed to list tools: {str(e)}", "MCP Client")
			raise
	
	def call_tool(self, name: str, arguments: Dict) -> Any:
		"""
		Execute a tool via MCP server.
		
		Sends JSON-RPC request to execute tool with provided arguments.
		Tool execution happens server-side (Frappe_Assistant_Core).
		
		Flow:
			1. Validate connection (initialize if needed)
			2. Send tools/call JSON-RPC request
			3. Server validates permissions and executes tool
			4. Server returns result or error
			5. Client returns result to LLM router
		
		Example:
			client.call_tool("get_document", {"doctype": "Task", "name": "TASK-001"})
			Returns: {"name": "TASK-001", "subject": "Fix bug", ...}
		
		Args:
			name: Tool name (e.g., "get_document", "search", "update_document")
			arguments: Tool arguments (validated against tool's inputSchema)
		
		Returns:
			Tool execution result (format depends on tool)
			On error: {"error": True, "message": "...", "tool": "..."}
		"""
		try:
			# Ensure connection is initialized
			if not self.initialized:
				self.initialize()
			
			# Construct JSON-RPC request to execute tool
			request = {
				"jsonrpc": "2.0",
				"method": "tools/call",  # MCP method for tool execution
				"params": {
					"name": name,  # Tool to execute
					"arguments": arguments  # Tool arguments
				},
				"id": self._generate_id()
			}
			
			# Send request to MCP server
			response = self._call_endpoint(request)
			
			# Handle JSON-RPC errors (permission denied, invalid arguments, etc.)
			if "error" in response:
				error_msg = response["error"].get("message", "Unknown error")
				frappe.log_error(
					f"Tool execution error: {name} - {error_msg}",
					"MCP Client"
				)
				# Return error in standard format
				return {
					"error": True,
					"message": error_msg,
					"tool": name
				}
			
			# Extract result from JSON-RPC response
			result = response.get("result", {})
			
			# Log successful execution (debug level)
			frappe.logger().debug(f"Tool executed successfully: {name}")
			
			return result
		
		except Exception as e:
			# Log unexpected errors
			frappe.log_error(f"Tool call failed: {name} - {str(e)}", "MCP Client")
			# Return error in standard format
			return {
				"error": True,
				"message": str(e),
				"tool": name
			}
	
	def get_tool_info(self, tool_name: str) -> Optional[Dict]:
		"""
		Get detailed information about a specific tool.
		
		Fetches tool list and searches for tool by name.
		Useful for validating tool exists before execution.
		
		Args:
			tool_name: Tool name to lookup (e.g., "get_document")
		
		Returns:
			Tool definition (name, description, inputSchema) or None if not found
		"""
		# Get all available tools (may use cache)
		tools = self.list_tools()
		
		# Search for tool by name
		for tool in tools:
			if tool.get("name") == tool_name:
				return tool
		
		return None  # Tool not found
	
	def clear_cache(self):
		"""
		Clear tool list cache for current user.
		
		Used when:
			- Settings change (new MCP endpoint)
			- Tools are added/removed on server
			- Cache becomes stale
		"""
		cache_key = f"mcp_tools_{frappe.session.user}"
		frappe.cache().delete_value(cache_key)
	
	def _call_endpoint(self, request: Dict) -> Dict:
		"""
		Send JSON-RPC request to MCP endpoint using OAuth Bearer token.
		
		Makes HTTP POST request with Authorization header containing Bearer token.
		Automatically refreshes token if expired (401 response).
		
		Args:
			request: JSON-RPC 2.0 request
		
		Returns:
			JSON-RPC 2.0 response dict
		"""
		try:
			return self._call_endpoint_oauth(request)
		
		except Exception as e:
			# Log endpoint call failures
			frappe.log_error(f"MCP endpoint call failed: {str(e)}", "MCP Client")
			# Return JSON-RPC error response
			return {
				"jsonrpc": "2.0",
				"error": {
					"code": -32603,
					"message": f"Internal error: {str(e)}"
				},
				"id": request.get("id")
			}
	
	def _call_endpoint_oauth(self, request: Dict) -> Dict:
		"""
		Call MCP endpoint using OAuth 2.0 Bearer token authentication (HTTP).
		
		This mode makes actual HTTP POST request with Authorization header.
		Automatically refreshes access token if expired.
		
		Args:
			request: JSON-RPC 2.0 request
		
		Returns:
			JSON-RPC 2.0 response dict
		"""
		import httpx
		
		# Ensure we have a valid access token
		if not self.access_token:
			try:
				self._refresh_oauth_token()
			except Exception as e:
				# Return user-friendly error message
				error_msg = str(e)
				if "No OAuth tokens found" in error_msg or "DocType not found" in error_msg:
					return {
						"jsonrpc": "2.0",
						"error": {
							"code": -32001,
							"message": "Authorization required. Please authorize the chatbot first.",
							"data": {
								"action": "authorize",
								"details": error_msg
							}
						},
						"id": request.get("id")
					}
				else:
					return {
						"jsonrpc": "2.0",
						"error": {
							"code": -32603,
							"message": f"OAuth token refresh failed: {error_msg}"
						},
						"id": request.get("id")
					}
		
		# Make HTTP POST with Bearer token
		headers = {
			"Authorization": f"Bearer {self.access_token}",
			"Content-Type": "application/json"
		}
		
		try:
			response = httpx.post(
				self.endpoint,
				json=request,
				headers=headers,
				timeout=30.0
			)
			
			# Check for 401 (token expired)
			if response.status_code == 401:
				frappe.logger().info("OAuth token expired, refreshing...")
				self._refresh_oauth_token()
				
				# Retry with new token
				headers["Authorization"] = f"Bearer {self.access_token}"
				response = httpx.post(
					self.endpoint,
					json=request,
					headers=headers,
					timeout=30.0
				)
			
			# Parse JSON response
			if response.status_code == 200:
				return response.json()
			else:
				return {
					"jsonrpc": "2.0",
					"error": {
						"code": -32603,
						"message": f"HTTP {response.status_code}: {response.text[:200]}"
					},
					"id": request.get("id")
				}
		
		except httpx.TimeoutException:
			return {
				"jsonrpc": "2.0",
				"error": {
					"code": -32603,
					"message": "Request timeout (30s)"
				},
				"id": request.get("id")
			}
		except Exception as e:
			return {
				"jsonrpc": "2.0",
				"error": {
					"code": -32603,
					"message": f"HTTP request failed: {str(e)}"
				},
				"id": request.get("id")
			}
	
	def _refresh_oauth_token(self):
		"""
		Refresh OAuth access token using refresh_token grant.
		
		Retrieves stored tokens for current user and refreshes them.
		This uses the proper OAuth Authorization Code Flow with refresh tokens,
		NOT client_credentials (which FAC doesn't support).
		"""
		import httpx
		from datetime import datetime, timedelta
		
		# Get current user
		user = frappe.session.user
		
		# Check if DocType exists (handle pre-migration state)
		if not frappe.db.exists("DocType", "AI Chatbot User Token"):
			raise Exception(
				"AI Chatbot User Token DocType not found. "
				"Please run: bench --site your-site migrate"
			)
		
		# Get user's stored tokens
		token_doc_name = frappe.db.exists("AI Chatbot User Token", {"user": user})
		
		if not token_doc_name:
			raise Exception(
				"No OAuth tokens found for current user. "
				"Please authorize the chatbot first by visiting the AI Assistant page."
			)
		
		token_doc = frappe.get_doc("AI Chatbot User Token", token_doc_name)
		
		# Get refresh token
		refresh_token = token_doc.get_password("refresh_token")
		
		if not refresh_token:
			raise Exception("Refresh token not found. Please re-authorize the chatbot.")
		
		# Get OAuth config from settings
		client_id = self.settings.get("mcp_oauth_client_id")
		client_secret = self.settings.get_password("mcp_oauth_client_secret")
		token_url = self.settings.get("mcp_oauth_token_url")
		
		if not all([client_id, token_url]):
			raise Exception(
				"OAuth configuration incomplete. Please configure OAuth Client ID "
				"and Token URL in AI Chatbot Settings."
			)
		
		# Prepare refresh request
		data = {
			"grant_type": "refresh_token",
			"refresh_token": refresh_token,
			"client_id": client_id
		}
		
		# Add client_secret if configured (for confidential clients)
		if client_secret:
			data["client_secret"] = client_secret
		
		# Request new token
		try:
			response = httpx.post(
				token_url,
				data=data,
				timeout=10.0
			)
			
			if response.status_code == 200:
				token_data = response.json()
				
				# Update stored tokens
				token_doc.access_token = token_data["access_token"]
				
				# Update refresh token if new one provided
				if "refresh_token" in token_data:
					token_doc.refresh_token = token_data["refresh_token"]
				
				# Update expiry time (use UTC time)
				from frappe.utils import now_datetime
				expires_in = token_data.get("expires_in", 3600)
				token_doc.expires_at = now_datetime() + timedelta(seconds=expires_in)
				
				token_doc.save(ignore_permissions=True)
				frappe.db.commit()
				
				# Update instance variable
				self.access_token = token_data["access_token"]
				
				frappe.logger().info(f"OAuth access token refreshed for user: {user}")
			else:
				raise Exception(f"Token refresh failed: HTTP {response.status_code} - {response.text[:200]}")
		
		except Exception as e:
			frappe.log_error(f"OAuth token refresh failed for {user}: {str(e)}", "MCP Client OAuth")
			raise Exception(f"Failed to refresh OAuth token: {str(e)}")
	
	def _generate_id(self) -> str:
		"""
		Generate unique request ID for JSON-RPC requests.
		
		JSON-RPC 2.0 requires unique ID for request/response matching.
		Uses UUID4 for guaranteed uniqueness.
		
		Returns:
			UUID string
		"""
		return str(uuid.uuid4())
	
	def test_connection(self) -> Dict:
		"""
		Test connection to MCP server.
		
		Performs initialize handshake and returns result.
		Useful for:
			- Validating MCP endpoint configuration
			- Checking server availability
			- Debugging connection issues
		
		Returns:
			Dict with:
				- success: True if connection successful
				- message: Human-readable status message
				- server_info: Server capabilities (if success=True)
		"""
		try:
			# Attempt initialize handshake
			info = self.initialize()
			return {
				"success": True,
				"message": "Connected to MCP server successfully",
				"server_info": info
			}
		
		except Exception as e:
			return {
				"success": False,
				"message": f"Failed to connect: {str(e)}"
			}


@frappe.whitelist()
def test_mcp_connection():
	"""
	Test MCP connection (whitelisted API endpoint).
	
	Allows frontend to test MCP connectivity via REST API.
	Used in AI Chatbot Settings page to validate configuration.
	"""
	client = MCPClient()
	return client.test_connection()


@frappe.whitelist()
def get_available_tools():
	"""
	Get available tools (whitelisted API endpoint).
	
	Returns list of all available MCP tools with their schemas.
	Used by frontend to display available tools to users.
	"""
	client = MCPClient()
	return client.list_tools()


@frappe.whitelist()
def clear_tool_cache():
	"""
	Clear tool cache (whitelisted API endpoint).
	
	Forces refresh of tool list on next request.
	Used when tools are added/removed on server or configuration changes.
	"""
	client = MCPClient()
	client.clear_cache()
	return {"success": True}
