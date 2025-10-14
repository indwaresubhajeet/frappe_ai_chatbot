"""
MCP Formatter - Formats tool results for LLM consumption

Key Features:
- Format tool results in human-readable text for LLMs
- Handle different data types (list, dict, string, document)
- Create text tables from list of dicts
- Special formatting for Frappe documents (doctype/name)
- Paginated result handling (data/total)
- Length limiting (10 items max, truncate long values)
- Error formatting with ❌ emoji

Use Cases:
- Called by llm/router.py after MCPExecutor returns tool results
- Convert JSON results to natural language text
- Make tool output easy for LLM to understand and use
- Prevent context overflow with truncation

Data Type Handling:
- List: Numbered items (1. 2. 3...), table if list of dicts
- Dict: Check for Frappe document / paginated results / generic key-value
- String: Return as-is
- Error: Format with tool name and error message

Example:
  formatter = MCPFormatter()
  result = {"data": [{"name": "John"}], "total": 100}
  formatted = formatter.format_result("search_users", result)
  # Returns: "Results from search_users:\nname\n----\nJohn\n\nShowing 1 of 100 total results"
"""

import json
from typing import Dict, Any, List
import frappe


class MCPFormatter:
	"""
	Formats MCP tool results for better LLM understanding.
	
	Responsibilities:
	- Detect data type (list/dict/string/document)
	- Apply appropriate formatting strategy
	- Limit output length to prevent context overflow
	- Create human-readable text tables
	- Handle errors gracefully with clear messages
	"""
	
	def format_result(self, tool_name: str, result: Dict[str, Any]) -> str:
		"""
		Format tool result for LLM consumption.
		
		Main formatting entry point. Routes to appropriate formatter based on data type.
		
		Args:
			tool_name: Name of the tool (e.g., "search_documents", "get_report")
			result: Raw tool result from MCPExecutor
		
		Returns:
			Formatted string for LLM (human-readable text)
		"""
		# Handle errors first (error: True, message: "...")
		if result.get("error"):
			return f"❌ Error executing {tool_name}: {result.get('message', 'Unknown error')}"
		
		# Get the actual content (some tools wrap in "content" key)
		content = result.get("content", result)
		
		# Route to appropriate formatter based on type
		if isinstance(content, list):
			return self._format_list(tool_name, content)  # Numbered list or table
		
		elif isinstance(content, dict):
			return self._format_dict(tool_name, content)  # Document / paginated / key-value
		
		elif isinstance(content, str):
			return content  # Already formatted, return as-is
		
		else:
			return str(content)  # Fallback: convert to string
	
	def _format_list(self, tool_name: str, items: List) -> str:
		"""
		Format list results as numbered list or table.
		
		If items are dicts → create text table (columns)
		If items are primitives → create numbered list
		Limit to 10 items to prevent context overflow
		"""
		if not items:
			return f"No results found from {tool_name}"
		
		# Check if items are dicts (table-like data from Frappe queries)
		if items and isinstance(items[0], dict):
			return self._format_table(items)  # Create text table with columns
		
		# Simple list (strings, numbers, etc.)
		formatted = [f"Results from {tool_name}:"]
		for i, item in enumerate(items, 1):
			formatted.append(f"{i}. {item}")  # Numbered list (1. 2. 3...)
		
		# Limit output length (prevent large lists from filling context)
		if len(items) > 10:
			formatted.append(f"\n... and {len(items) - 10} more items")
		
		return "\n".join(formatted)
	
	def _format_dict(self, tool_name: str, data: Dict) -> str:
		"""
		Format dict results with special handling for Frappe patterns.
		
		Detection patterns:
		- Frappe document: Has "doctype" and "name" keys
		- Paginated results: Has "data" (list) and "total" (count)
		- Generic dict: Simple key-value pairs
		"""
		# Check for Frappe document format (e.g., {"doctype": "User", "name": "john@example.com"})
		if "doctype" in data and "name" in data:
			return self._format_document(data)  # Special formatting for Frappe docs
		
		# Check for paginated results (common Frappe pattern: {"data": [...], "total": 100})
		if "data" in data and "total" in data:
			formatted = self._format_list(tool_name, data["data"])  # Format the data list
			# Add pagination info if there are more results
			if data.get("total", 0) > len(data.get("data", [])):
				formatted += f"\n\nShowing {len(data['data'])} of {data['total']} total results"
			return formatted
		
		# Generic dict formatting (key-value pairs)
		formatted = [f"Results from {tool_name}:"]
		for key, value in data.items():
			if isinstance(value, (dict, list)):
				formatted.append(f"- {key}: {json.dumps(value, indent=2)}")  # JSON for complex values
			else:
				formatted.append(f"- {key}: {value}")  # Simple values inline
		
		return "\n".join(formatted)
	
	def _format_table(self, items: List[Dict]) -> str:
		"""
		Format list of dicts as a text table.
		
		Creates ASCII table with:
		- Header row (sorted keys)
		- Separator line (dashes)
		- Data rows (10 max)
		- Footer if more than 10 rows
		
		Limits:
		- Max 10 rows (prevent context overflow)
		- Max 50 chars per cell (truncate long values)
		"""
		if not items:
			return "No data"
		
		# Get all unique keys from all items (some items may have different keys)
		all_keys = set()
		for item in items:
			all_keys.update(item.keys())
		
		# Limit to first 10 items (prevent large tables)
		display_items = items[:10]
		
		# Create simple text table
		formatted = []
		
		# Header row (sorted for consistency)
		headers = sorted(all_keys)
		formatted.append(" | ".join(headers))
		formatted.append("-" * (len(" | ".join(headers))))  # Separator line
		
		# Data rows
		for item in display_items:
			row = []
			for header in headers:
				value = item.get(header, "")  # Use empty string if key missing
				# Truncate long values (50 chars max to keep table readable)
				str_value = str(value)[:50]
				row.append(str_value)
			formatted.append(" | ".join(row))
		
		# Footer if more items (show count of hidden rows)
		if len(items) > 10:
			formatted.append(f"\n... and {len(items) - 10} more rows")
		
		return "\n".join(formatted)
	
	def _format_document(self, doc: Dict) -> str:
		"""
		Format Frappe document with important fields first.
		
		Frappe documents have standard structure:
		- doctype: Type of document (e.g., "User", "Task", "Customer")
		- name: Primary key / unique identifier
		- Standard meta fields: owner, modified, creation, status
		
		Strategy:
		- Show important fields first (name, title, status, etc.)
		- Then show other fields (limit to 10 to prevent overflow)
		- Skip complex nested structures (dicts, lists)
		"""
		formatted = [
			f"Document: {doc['doctype']} - {doc['name']}",
			"-" * 40  # Separator line
		]
		
		# Important fields first (common across all doctypes)
		important_fields = [
			"name", "title", "subject", "description",
			"status", "owner", "modified", "creation"
		]
		
		# Add important fields if present
		for field in important_fields:
			if field in doc and doc[field]:
				formatted.append(f"{field.title()}: {doc[field]}")
		
		# Add other fields (limit to 10 to prevent context overflow)
		other_fields = [k for k in doc.keys() if k not in important_fields]
		for field in other_fields[:10]:
			value = doc[field]
			# Only show simple values (skip nested dicts/lists)
			if value and not isinstance(value, (dict, list)):
				formatted.append(f"{field.title()}: {value}")
		
		return "\n".join(formatted)
	
	def format_tool_calls(self, tool_calls: List[Dict]) -> str:
		"""
		Format multiple tool calls for display in UI or logs.
		
		Shows numbered list of tool calls with arguments (JSON formatted).
		Used for debugging and transparency (show user what tools LLM called).
		
		Args:
			tool_calls: List of tool calls (each has "name" and "arguments")
		
		Returns:
			Formatted string with numbered list of tool calls
		"""
		if not tool_calls:
			return "No tools called"
		
		formatted = ["Tools Called:"]
		
		for i, call in enumerate(tool_calls, 1):
			name = call.get("name", "Unknown")
			args = call.get("arguments", {})
			formatted.append(f"\n{i}. {name}")  # Tool name
			
			if args:
				# Show arguments as indented JSON
				formatted.append(f"   Arguments: {json.dumps(args, indent=2)}")
		
		return "\n".join(formatted)
	
	def summarize_result(self, result: Dict[str, Any], max_length: int = 200) -> str:
		"""
		Create a short summary of result for quick display.
		
		Used for:
		- UI previews (show summary before full result)
		- Logs (quick overview of what tool returned)
		- Token saving (avoid sending full result to LLM if not needed)
		
		Args:
			result: Tool result (any type)
			max_length: Maximum summary length (default 200 chars)
		
		Returns:
			Brief summary (e.g., "Returned 5 items", "Found 100 results")
		"""
		content = result.get("content", result)
		
		# List: Show count
		if isinstance(content, list):
			return f"Returned {len(content)} items"
		
		# Dict: Show total if available, else field count
		elif isinstance(content, dict):
			if "total" in content:
				return f"Found {content['total']} results"
			return f"Returned {len(content)} fields"
		
		# String: Truncate if too long
		elif isinstance(content, str):
			if len(content) <= max_length:
				return content
			return content[:max_length] + "..."  # Add ellipsis for truncated strings
		
		# Fallback: Convert to string and truncate
		return str(content)[:max_length]
