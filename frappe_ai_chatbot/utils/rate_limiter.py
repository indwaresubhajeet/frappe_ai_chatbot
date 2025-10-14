"""
Rate Limiter - Rate limiting for API requests to prevent abuse

Key Features:
- Messages per hour limit (hourly quota, Frappe cache)
- Tokens per day limit (daily quota, database sum)
- Concurrent requests limit (parallel request throttling, cache)
- Per-user isolation (each user has separate quotas)
- Configurable via AI Chatbot Settings (enable/disable, adjust limits)

Use Cases:
- Called by api/chat.py before processing request
- Prevent abuse (spam, excessive API costs)
- Fair resource allocation (prevent single user monopolizing)
- Cost control (limit tokens/day to control LLM API bills)

Rate Limit Types:
1. Messages per hour: Redis-like counter, 1-hour TTL (fast, cache-based)
2. Tokens per day: Database sum of total_tokens (accurate, persistent)
3. Concurrent requests: Active request counter (prevent parallel flooding)

Storage:
- Messages count: Frappe cache (expires_in_sec=3600)
- Tokens count: Database query (AI Chat Session.total_tokens)
- Concurrent count: Frappe cache (expires_in_sec=300)

Example Flow:
  if not check_rate_limit(user, settings):
      frappe.throw("Rate limit exceeded. Try again later.")
  # Process request...
"""

import frappe
from datetime import datetime, timedelta
from typing import Optional


def check_rate_limit(user: str, settings) -> bool:
	"""
	Check if user has exceeded any rate limit.
	
	Checks all enabled limits (messages/hour, tokens/day, concurrent requests).
	Returns False if ANY limit is exceeded.
	
	Args:
		user: User email (e.g., "john@example.com")
		settings: AI Chatbot Settings (doctype singleton)
	
	Returns:
		True if within all limits, False if any limit exceeded
	"""
	# Skip if rate limiting disabled globally
	if not settings.enable_rate_limiting:
		return True
	
	# Check messages per hour (e.g., 100 messages/hour max)
	if settings.messages_per_hour:
		if not _check_messages_per_hour(user, settings.messages_per_hour):
			return False  # Exceeded hourly message limit
	
	# Check tokens per day (e.g., 1M tokens/day max)
	if settings.tokens_per_day:
		if not _check_tokens_per_day(user, settings.tokens_per_day):
			return False  # Exceeded daily token limit
	
	# Check concurrent requests (e.g., 5 parallel requests max)
	if settings.max_concurrent_requests:
		if not _check_concurrent_requests(user, settings.max_concurrent_requests):
			return False  # Too many concurrent requests
	
	return True  # All checks passed


def _check_messages_per_hour(user: str, limit: int) -> bool:
	"""
	Check messages per hour limit (cache-based counter).
	
	Uses Frappe cache with 1-hour TTL (automatic reset).
	Increments counter on each check (atomic operation).
	
	Returns False if limit exceeded, True if within limit (and increments).
	"""
	cache_key = f"rate_limit_messages_{user}"
	
	# Get current count from cache
	count = frappe.cache().get_value(cache_key)
	
	if count is None:
		count = 0  # First message this hour
	else:
		count = int(count)
	
	# Check if limit exceeded
	if count >= limit:
		return False  # Over limit, reject request
	
	# Increment counter (this request counts toward limit)
	frappe.cache().set_value(
		cache_key,
		count + 1,
		expires_in_sec=3600  # 1 hour TTL (automatic reset)
	)
	
	return True  # Within limit, allow request


def _check_tokens_per_day(user: str, limit: int) -> bool:
	"""
	Check tokens per day limit (database-based sum).
	
	Sums total_tokens from all sessions created today.
	More accurate than cache, but slower (database query).
	"""
	from frappe.utils import today
	
	# Get today's token usage from database (sum of total_tokens)
	today_date = today()  # e.g., "2024-01-15"
	
	total_tokens = frappe.db.get_value(
		"AI Chat Session",
		{
			"user": user,
			"creation": [">=", today_date]  # Sessions created today
		},
		"sum(total_tokens)"  # Aggregate function
	) or 0  # Default to 0 if no sessions
	
	return total_tokens < limit  # True if under limit


def _check_concurrent_requests(user: str, limit: int) -> bool:
	"""
	Check concurrent requests limit (active request counter).
	
	Counts how many requests are currently in-flight.
	Used with increment_concurrent_requests() / decrement_concurrent_requests().
	"""
	cache_key = f"concurrent_requests_{user}"
	
	# Get current count from cache
	count = frappe.cache().get_value(cache_key)
	
	if count is None:
		count = 0
	else:
		count = int(count)
	
	# Check if limit exceeded
	if count >= limit:
		return False  # Too many concurrent requests
	
	return True  # Within limit


def increment_concurrent_requests(user: str):
	"""
	Increment concurrent request counter (call at request start).
	
	Used with decrement_concurrent_requests() to track active requests.
	5-minute TTL prevents stale counters (if decrement not called).
	"""
	cache_key = f"concurrent_requests_{user}"
	
	count = frappe.cache().get_value(cache_key)
	if count is None:
		count = 0
	else:
		count = int(count)
	
	frappe.cache().set_value(
		cache_key,
		count + 1,  # Add one active request
		expires_in_sec=300  # 5 minutes TTL (safety)
	)


def decrement_concurrent_requests(user: str):
	"""
	Decrement concurrent request counter (call at request end).
	
	Must be called in finally block to ensure cleanup even on errors.
	"""
	cache_key = f"concurrent_requests_{user}"
	
	count = frappe.cache().get_value(cache_key)
	if count is None or count == 0:
		return  # Already at 0, nothing to decrement
	
	count = int(count)
	
	if count > 0:
		frappe.cache().set_value(
			cache_key,
			count - 1,  # Remove one active request
			expires_in_sec=300  # 5 minutes TTL (safety)
		)


def get_rate_limit_status(user: str) -> dict:
	"""
	Get current rate limit status for user (for UI display).
	
	Returns current usage and remaining quota for all limits.
	Useful for showing user their usage (e.g., "50/100 messages this hour").
	
	Args:
		user: User email
	
	Returns:
		Dict with current, limit, remaining for each rate limit type
	"""
	from frappe.utils import today
	
	settings = frappe.get_single("AI Chatbot Settings")
	
	# Messages this hour (cache-based)
	cache_key = f"rate_limit_messages_{user}"
	messages_count = frappe.cache().get_value(cache_key) or 0
	
	# Tokens today (database-based sum)
	today_date = today()
	tokens_count = frappe.db.get_value(
		"AI Chat Session",
		{
			"user": user,
			"creation": [">=", today_date]
		},
		"sum(total_tokens)"
	) or 0
	
	# Concurrent requests (cache-based)
	concurrent_key = f"concurrent_requests_{user}"
	concurrent_count = frappe.cache().get_value(concurrent_key) or 0
	
	return {
		"messages_per_hour": {
			"current": int(messages_count),
			"limit": settings.messages_per_hour,
			"remaining": max(0, settings.messages_per_hour - int(messages_count))
		},
		"tokens_per_day": {
			"current": int(tokens_count),
			"limit": settings.tokens_per_day,
			"remaining": max(0, settings.tokens_per_day - int(tokens_count))
		},
		"concurrent_requests": {
			"current": int(concurrent_count),
			"limit": settings.max_concurrent_requests
		}
	}


@frappe.whitelist()
def get_my_rate_limit_status():
	"""
	Get rate limit status for current user (API endpoint).
	
	Whitelisted for frontend calls (no authentication required beyond session).
	"""
	return get_rate_limit_status(frappe.session.user)
