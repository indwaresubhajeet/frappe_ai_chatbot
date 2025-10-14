"""
Context Manager - Manages conversation context for LLM requests

Key Features:
- Load recent messages from database (AI Chat Message doctype)
- Token-based pruning to fit context window (max_tokens limit)
- Message summarization (old messages → summary, keep recent as-is)
- Relevance-based filtering (keyword matching, can use embeddings)
- Always preserve system messages (instructions, prompts)

Use Cases:
- Called by llm/router.py before sending to LLM
- Prevent context overflow (Claude 200K, OpenAI 128K, Gemini 2M)
- Maintain conversation coherence with limited context
- Prioritize recent and relevant messages

Context Window Strategies:
1. get_context(): Load last N messages (simple, chronological)
2. prune_context(): Token-based truncation (keep system + recent messages)
3. summarize_old_context(): Replace old messages with summary (token savings)
4. get_relevant_context(): Keyword-based relevance (semantic matching)

Example Flow:
  context_manager = ContextManager(context_window_size=10)
  messages = context_manager.get_context(session_id)
  pruned = context_manager.prune_context(messages, max_tokens=100000, token_counter=adapter.count_tokens)
  # Returns messages that fit within 100K tokens
"""

import frappe
from typing import List
from frappe_ai_chatbot.llm.base_adapter import LLMMessage
import json


class ContextManager:
	"""
	Manages conversation context window for LLM requests.
	
	Responsibilities:
	- Load messages from database (AI Chat Message)
	- Prune messages to fit token limits (prevent overflow)
	- Summarize old messages (save tokens)
	- Filter by relevance (keyword matching)
	- Always preserve system messages
	"""
	
	def __init__(self, context_window_size: int = 10):
		"""
		Initialize context manager.
		
		Args:
			context_window_size: Number of recent messages to include (default 10)
		"""
		self.context_window_size = context_window_size
	
	def get_context(self, session_id: str) -> List[LLMMessage]:
		"""
		Get conversation context for a session (recent messages).
		
		Loads last N messages from database, converts to LLMMessage objects.
		Handles tool_calls JSON parsing (tool calling messages).
		
		Args:
			session_id: Chat session ID (primary key of AI Chat Session)
		
		Returns:
			List of LLMMessage objects in chronological order
		"""
		# Get recent messages from database (ordered newest first)
		messages = frappe.get_all(
			"AI Chat Message",
			filters={"session": session_id},
			fields=["role", "content", "tool_calls", "tool_call_id", "tool_name"],
			order_by="timestamp desc",  # Newest first
			limit=self.context_window_size  # Last N messages
		)
		
		# Reverse to get chronological order (oldest → newest)
		messages.reverse()
		
		# Convert to LLMMessage objects
		llm_messages = []
		
		for msg in messages:
			# Parse tool_calls JSON (if present, for assistant tool calling messages)
			tool_calls = None
			if msg.get("tool_calls"):
				try:
					parsed_tool_calls = json.loads(msg["tool_calls"])  # Parse JSON string
					# Only set tool_calls if the array is not empty
					# OpenAI rejects messages with empty tool_calls array
					if parsed_tool_calls and len(parsed_tool_calls) > 0:
						tool_calls = parsed_tool_calls
				except json.JSONDecodeError:
					pass  # Ignore malformed JSON
			
			# Create LLMMessage object
			llm_msg = LLMMessage(
				role=msg["role"],  # "user", "assistant", "system", "tool"
				content=msg["content"],
				tool_calls=tool_calls,  # List of tool calls (assistant role) - None if empty
				tool_call_id=msg.get("tool_call_id"),  # Tool result ID (tool role)
				name=msg.get("tool_name")  # Tool name (tool role)
			)
			
			llm_messages.append(llm_msg)
		
		return llm_messages
	
	def prune_context(
		self,
		messages: List[LLMMessage],
		max_tokens: int,
		token_counter
	) -> List[LLMMessage]:
		"""
		Prune context to fit within token limit (prevent overflow).
		
		Strategy:
		- Always keep system messages (instructions, prompts)
		- Add recent messages until reaching max_tokens
		- Drop oldest messages first (FIFO)
		
		Args:
			messages: List of messages (chronological order)
			max_tokens: Maximum token count (e.g., 100000 for Claude)
			token_counter: Function to count tokens (adapter.count_tokens)
		
		Returns:
			Pruned list of messages (fits within max_tokens)
		"""
		# Always keep system message if present (critical instructions)
		system_messages = [m for m in messages if m.role == "system"]
		other_messages = [m for m in messages if m.role != "system"]
		
		# Start with most recent messages (reverse to process newest first)
		other_messages.reverse()
		
		pruned = []
		current_tokens = token_counter(system_messages)  # Count system message tokens
		
		# Add messages from newest to oldest until hitting limit
		for msg in other_messages:
			msg_tokens = token_counter([msg])  # Count tokens for this message
			
			if current_tokens + msg_tokens <= max_tokens:
				pruned.insert(0, msg)  # Insert at beginning to maintain chronological order
				current_tokens += msg_tokens
			else:
				break  # Stop when we would exceed limit
		
		# Combine system messages (at start) and pruned messages (chronological)
		return system_messages + pruned
	
	def summarize_old_context(
		self,
		messages: List[LLMMessage],
		keep_recent: int = 5
	) -> List[LLMMessage]:
		"""
		Summarize old messages to save tokens (alternative to pruning).
		
		Strategy:
		- Keep recent N messages as-is (full context)
		- Summarize older messages into single system message (truncated)
		- Saves tokens while maintaining conversation history
		
		Use when:
		- Context window almost full but want to keep history
		- Long conversations (100+ messages)
		- Alternative to dropping old messages completely
		
		Args:
			messages: List of messages (chronological)
			keep_recent: Number of recent messages to keep as-is (default 5)
		
		Returns:
			List with summarized old context + recent messages
		"""
		if len(messages) <= keep_recent:
			return messages  # No need to summarize
		
		# Split messages into old (to summarize) and recent (keep as-is)
		old_messages = messages[:-keep_recent]
		recent_messages = messages[-keep_recent:]
		
		# Create summary of old messages (truncated to first 100 chars each)
		summary_text = "Previous conversation summary:\n"
		
		for msg in old_messages:
			if msg.role == "user":
				summary_text += f"User asked about: {msg.content[:100]}...\n"
			elif msg.role == "assistant":
				summary_text += f"Assistant responded: {msg.content[:100]}...\n"
			# Skip system and tool messages in summary
		
		# Create summary message (system role = instructions/context)
		summary_message = LLMMessage(
			role="system",
			content=summary_text
		)
		
		# Return: [summary] + [recent messages]
		return [summary_message] + recent_messages
	
	def get_relevant_context(
		self,
		session_id: str,
		query: str,
		max_messages: int = 5
	) -> List[LLMMessage]:
		"""
		Get most relevant messages for current query (semantic filtering).
		
		Uses simple keyword matching (can be enhanced with embeddings/vector search).
		Useful for long conversations where not all messages are relevant.
		
		Relevance Scoring:
		- Count keyword overlap between query and message
		- Sort by overlap (descending)
		- Return top N most relevant messages
		
		Future Enhancement:
		- Replace with semantic embeddings (OpenAI embeddings, sentence-transformers)
		- Vector similarity search (cosine similarity)
		- Contextual relevance (not just keyword matching)
		
		Args:
			session_id: Chat session ID
			query: Current user query (to find relevant messages)
			max_messages: Maximum messages to return (default 5)
		
		Returns:
			List of relevant messages (sorted by relevance, descending)
		"""
		# Get all messages from session
		all_messages = self.get_context(session_id)
		
		if not all_messages:
			return []
		
		# Simple keyword-based relevance (split query into words)
		query_keywords = set(query.lower().split())
		
		# Score messages by keyword overlap
		scored_messages = []
		
		for msg in all_messages:
			if not msg.content:
				continue  # Skip empty messages
			
			# Count keyword overlap
			msg_keywords = set(msg.content.lower().split())
			overlap = len(query_keywords & msg_keywords)  # Set intersection
			
			scored_messages.append((overlap, msg))
		
		# Sort by score (descending = most relevant first)
		scored_messages.sort(key=lambda x: x[0], reverse=True)
		
		# Return top N messages
		return [msg for score, msg in scored_messages[:max_messages]]
