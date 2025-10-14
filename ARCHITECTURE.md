# Frappe AI Chatbot - Complete Architecture Documentation

**Technical Reference**

This document provides complete technical documentation of the actual codebase.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Complete File Structure](#2-complete-file-structure)
3. [Core API Endpoints](#3-core-api-endpoints)
4. [LLM Integration Layer](#4-llm-integration-layer)
5. [MCP Client Implementation](#5-mcp-client-implementation)
6. [Frontend Application](#6-frontend-application)
   - [Full-Page Interface](#file-ai_chatbotpageai_assistantai_assistantjs)
   - [Floating Chat Widget](#file-publicjsai_chat_widgetjs)
7. [Database Schema (DocTypes)](#7-database-schema-doctypes)
8. [Configuration & Setup](#8-configuration--setup)
9. [Data Flow Diagrams](#9-data-flow-diagrams)
10. [Complete API Reference](#10-complete-api-reference)

---

## 1. Project Overview

### What This Project Does

Frappe AI Chatbot is a custom Frappe app that embeds AI assistant interfaces into ERPNext. It provides:

- **Floating chat widget** (primary UI) - Available on all pages
- **Full-page chat UI** at `/app/ai-assistant` *(temporarily disabled)*
- **Multi-LLM support**: Claude (Anthropic), OpenAI GPT, Gemini (Google), Local (Ollama)
- **MCP Protocol integration** with Frappe_Assistant_Core (22+ tools)
- **Real-time streaming** via Server-Sent Events (SSE)
- **Session management** with database persistence
- **Rate limiting** and permission controls

### Technology Stack

- **Backend**: Python 3.11+, Frappe Framework v15+
- **Frontend**: JavaScript (ES6+), jQuery, Frappe UI
- **Database**: MariaDB (via Frappe ORM)
- **Streaming**: Server-Sent Events (SSE)
- **Protocol**: Model Context Protocol (MCP) for tool calling
- **LLM SDKs**: anthropic, openai, google-generativeai

### Key Design Decisions

1. **Single-file frontend** (`ai_assistant.js`): Follows Frappe community standard
2. **Adapter pattern** for LLMs: Easy to add new providers
3. **SSE over WebSockets**: Simpler protocol, better proxy compatibility
4. **JSON-RPC 2.0** for MCP: Standard protocol for tool communication
5. **Minimal dependencies**: Only 3 external packages in pyproject.toml

---

## 2. Complete File Structure

```
frappe_ai_chatbot/                              # Project root
├── pyproject.toml                              # Package configuration
├── README.md                                   # User documentation
├── ARCHITECTURE.md                             # This file (technical reference)
└── frappe_ai_chatbot/                         # Main app directory
    ├── __init__.py                            # App version and metadata
    ├── hooks.py                               # Frappe framework integration
    ├── setup.py                               # Post-installation setup tasks
    ├── modules.txt                            # Module list
    ├── patches.txt                            # Database migration patches
    │
    ├── ai_chatbot/                            # Main module
    │   ├── __init__.py
    │   ├── doctype/                           # Database models (DocTypes)
    │   │   ├── ai_chatbot_settings/
    │   │   │   ├── ai_chatbot_settings.py     # Settings controller
    │   │   │   └── ai_chatbot_settings.json   # DocType schema
    │   │   ├── ai_chat_session/
    │   │   │   ├── ai_chat_session.py         # Session controller
    │   │   │   └── ai_chat_session.json       # DocType schema
    │   │   ├── ai_chat_message/
    │   │   │   ├── ai_chat_message.py         # Message controller
    │   │   │   └── ai_chat_message.json       # DocType schema
    │   │   └── ai_chat_feedback/
    │   │       ├── ai_chat_feedback.py        # Feedback controller
    │   │       └── ai_chat_feedback.json      # DocType schema
    │   │
    │   └── page/                              # Custom Frappe pages
    │       └── ai_assistant/
    │           ├── ai_assistant.py            # Page backend
    │           ├── ai_assistant.js            # Complete single-page UI
    │           └── ai_assistant.json          # Page metadata
    │
    ├── api/                                   # REST API endpoints
    │   ├── __init__.py
    │   ├── chat.py                            # Non-streaming chat API
    │   └── stream.py                          # SSE streaming endpoint
    │
    ├── llm/                                   # LLM integration layer
    │   ├── __init__.py
    │   ├── base_adapter.py                    # Abstract adapter interface
    │   ├── router.py                          # Request routing & orchestration
    │   ├── claude_adapter.py                  # Anthropic Claude integration
    │   ├── openai_adapter.py                  # OpenAI GPT integration
    │   ├── gemini_adapter.py                  # Google Gemini integration
    │   └── local_adapter.py                   # Local LLM (Ollama) integration
    │
    ├── mcp/                                   # MCP protocol client
    │   ├── __init__.py
    │   ├── client.py                          # JSON-RPC 2.0 MCP client
    │   ├── executor.py                        # Tool execution with retry logic
    │   └── formatter.py                       # Response formatting utilities
    │
    ├── utils/                                 # Utility modules
    │   ├── __init__.py
    │   ├── rate_limiter.py                    # Rate limiting & quota management
    │   └── context_manager.py                 # Conversation windowing strategies
    │
    ├── public/                                # Static assets
    │   └── js/
    │       ├── ai_assistant_launcher.js       # Navbar button (temporarily disabled)
    │       └── ai_chat_widget.js              # Floating chat widget (active)
    │
    └── tests/                                 # Unit tests
        ├── test_chat_api.py
        ├── test_stream.py
        ├── test_llm_router.py
        └── test_mcp_client.py
```

---

## 3. Core API Endpoints

### File: `api/chat.py`

**Purpose**: Main REST API endpoints for non-streaming chat operations.

#### Function: `get_or_create_session()`

```python
@frappe.whitelist()
def get_or_create_session() -> Dict:
```

**What it does**: Gets active session for current user or creates a new one.

**Returns**:
```python
{
    "name": "CHAT-SESSION-00001",  # Session ID
    "user": "user@example.com",
    "title": "Chat on 2025-10-14 10:30",
    "status": "Active",
    "started_at": "2025-10-14 10:30:00",
    "last_activity": "2025-10-14 10:35:00",
    "llm_provider": "claude",
    "model_name": "claude-3-5-sonnet-20241022",
    "total_messages": 5,
    "total_tokens": 1234,
    "estimated_cost": 0.05
}
```

**Logic flow**:
1. Check if user has `enable_ai_chatbot` field enabled
2. Check if AI Chatbot Settings is globally enabled
3. Look for active session (status="Active") for current user
4. If found: update `last_activity` and return
5. If not found: create new session with current timestamp

---

#### Function: `send_message(session_id, message, stream=False)`

```python
@frappe.whitelist()
def send_message(session_id: str, message: str, stream: bool = False) -> Dict:
```

**Parameters**:
- `session_id` (str): Chat session ID (e.g., "CHAT-SESSION-00001")
- `message` (str): User's message text
- `stream` (bool): Not used here (use `stream_chat` for streaming)

**What it does**: Sends message and gets complete response (non-streaming).

**Returns**:
```python
{
    "success": True,
    "message": {
        "name": "MSG-00042",
        "role": "assistant",
        "content": "Here's the information...",
        "tool_calls": [...],  # If tools were used
        "token_count": 156,
        "model_used": "claude-3-5-sonnet-20241022"
    },
    "session": {
        # Updated session data
    }
}
```

**Logic flow**:
1. Validate session ownership (must be current user's session)
2. Check rate limiting (via `_check_rate_limit()`)
3. Save user message to database (`AI Chat Message` DocType)
4. Initialize `LLMRouter` and call `router.chat(session_id, message)`
5. Save assistant response to database
6. Update session statistics (tokens, cost)
7. Return complete response

---

#### Function: `get_messages(session_id, limit=50, offset=0)`

```python
@frappe.whitelist()
def get_messages(session_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
```

**What it does**: Retrieves message history for a session with pagination.

**Returns**:
```python
[
    {
        "name": "MSG-00001",
        "role": "user",
        "content": "What are my pending sales orders?",
        "timestamp": "2025-10-14 10:30:15",
        "token_count": 0
    },
    {
        "name": "MSG-00002",
        "role": "assistant",
        "content": "You have 5 pending sales orders...",
        "timestamp": "2025-10-14 10:30:18",
        "token_count": 78,
        "tool_calls": "[{\"name\": \"list_documents\", ...}]"
    }
    # ... more messages
]
```

---

#### Function: `clear_history(session_id)`

```python
@frappe.whitelist()
def clear_history(session_id: str) -> Dict:
```

**What it does**: Deletes all messages in a session and resets statistics.

**Logic flow**:
1. Validate session ownership
2. Delete all `AI Chat Message` records for this session
3. Reset session counters:
   - `total_messages = 0`
   - `total_tokens = 0`
   - `estimated_cost = 0`
4. Return success

---

#### Function: `close_session(session_id)`

```python
@frappe.whitelist()
def close_session(session_id: str) -> Dict:
```

**What it does**: Marks session as closed (status="Closed").

---

#### Function: `get_settings()`

```python
@frappe.whitelist()
def get_settings() -> Dict:
```

**What it does**: Returns public settings (API keys are excluded).

**Returns**:
```python
{
    "enabled": True,
    "llm_provider": "claude",
    "claude_model": "claude-3-5-sonnet-20241022",
    "temperature": 0.7,
    "max_tokens": 4096,
    "enable_tool_calling": True,
    "system_prompt": "You are a helpful assistant...",
    # API keys are NOT included (security)
}
```

---

#### Helper Functions

```python
def _save_message(session_id, role, content, tool_calls=None, token_count=0, model_used=None)
```
- Creates and saves `AI Chat Message` document
- Returns saved document object

```python
def _check_rate_limit(user: str) -> bool
```
- Checks if user has exceeded rate limits
- Returns `True` if allowed, `False` if exceeded

```python
def _get_model_name(settings) -> str
```
- Extracts model name from settings based on provider
- Returns model string (e.g., "claude-3-5-sonnet-20241022")

---

### File: `api/stream.py`

**Purpose**: Server-Sent Events (SSE) endpoint for real-time streaming.

#### Function: `stream_chat(session_id, message)`

```python
@frappe.whitelist(allow_guest=False)
def stream_chat(session_id: str, message: str):
```

**What it does**: Streams AI response in real-time using SSE protocol.

**HTTP Response**:
```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

**SSE Event Types**:

1. **`user_message`** - Confirms user message saved
```
event: user_message
data: {"name": "MSG-00042", "content": "...", "timestamp": "..."}

```

2. **`content`** - Text chunk from AI
```
event: content
data: {"content": "Here's "}

event: content
data: {"content": "the "}

event: content
data: {"content": "answer..."}

```

3. **`tool_call`** - Tool execution started
```
event: tool_call
data: {"name": "list_documents", "arguments": {"doctype": "Sales Order"}}

```

4. **`tool_result`** - Tool execution completed
```
event: tool_result
data: {"result": {"documents": [...]}}

```

5. **`done`** - Stream complete
```
event: done
data: {"name": "MSG-00043", "content": "...", "tool_calls": [...]}

```

6. **`error`** - Error occurred
```
event: error
data: {"message": "Rate limit exceeded", "traceback": "..."}

```

**Logic flow**:
1. Set SSE headers (text/event-stream, no-cache)
2. Validate session exists and user has permission
3. Check rate limits
4. Save user message → yield `user_message` event
5. Initialize `LLMRouter` and call `stream_chat()`
6. For each chunk from LLM:
   - If content chunk → yield `content` event
   - If tool call → execute tool → yield `tool_call` + `tool_result`
   - If error → yield `error` event and stop
7. Save complete assistant message to database
8. Update rate limiter
9. Yield `done` event

---

#### Function: `format_sse_message(event_type, data)`

```python
def format_sse_message(event_type: str, data: dict) -> str:
```

**What it does**: Formats data into SSE protocol format.

**Example**:
```python
format_sse_message("content", {"content": "Hello"})
# Returns:
# "event: content\ndata: {\"content\": \"Hello\"}\n\n"
```

**SSE Format Requirements**:
- `event: <type>` line
- `data: <json>` line
- Double newline separator (`\n\n`)

---

#### Function: `test_streaming()`

```python
@frappe.whitelist()
def test_streaming():
```

**What it does**: Test endpoint that streams numbers 0-9 (useful for debugging).

---

## 4. LLM Integration Layer

### File: `llm/router.py`

**Purpose**: Routes requests to appropriate LLM provider and orchestrates conversation flow.

#### Class: `LLMRouter`

```python
class LLMRouter:
    def __init__(self):
        self.settings = frappe.get_single("AI Chatbot Settings")
        self.adapter: Optional[BaseLLMAdapter] = None
        self._initialize_adapter()
```

**Responsibilities**:
- Initialize correct LLM adapter based on settings
- Manage conversation context
- Handle tool calling flow
- Provide streaming and non-streaming interfaces

---

#### Method: `_initialize_adapter()`

```python
def _initialize_adapter(self):
```

**What it does**: Creates appropriate adapter instance based on `llm_provider` setting.

**Provider mapping**:
```python
"claude"  → ClaudeAdapter(api_key, model, temperature, max_tokens, top_p)
"openai"  → OpenAIAdapter(api_key, model, temperature, max_tokens, top_p)
"gemini"  → GeminiAdapter(api_key, model, temperature, max_tokens, top_p)
"local"   → LocalAdapter(endpoint, model, temperature, max_tokens)
```

**Validation**: Calls `adapter.validate_config()` to ensure required credentials exist.

---

#### Method: `chat(session_id, user_message)`

```python
def chat(self, session_id: str, user_message: str) -> Dict:
```

**What it does**: Non-streaming chat with automatic tool calling.

**Returns**:
```python
{
    "content": "The assistant's response text",
    "model": "claude-3-5-sonnet-20241022",
    "token_count": 234,
    "tool_calls": [
        {
            "name": "list_documents",
            "arguments": {"doctype": "Sales Order"},
            "result": {"documents": [...]}
        }
    ],
    "cost": 0.012,
    "finish_reason": "stop"
}
```

**Logic flow**:
1. Load conversation history (`_get_conversation_context()`)
2. Append current user message
3. Get available tools if `enable_tool_calling` is true
4. Get system prompt from settings
5. Call `adapter.chat(messages, tools, system_prompt)`
6. If response contains tool calls:
   - Execute each tool via `_handle_tool_calls()`
   - Get final response with tool results
7. Return complete response

---

#### Method: `stream_chat(session_id, user_message)`

```python
def stream_chat(self, session_id: str, user_message: str) -> Generator[Dict, None, None]:
```

**What it does**: Streaming chat that yields events as they occur.

**Yields**:
```python
{"type": "content", "content": "text chunk"}
{"type": "tool_call", "tool": {...}}
{"type": "tool_result", "tool": "name", "result": {...}}
{"type": "error", "error": "message"}
```

**Logic flow**:
1. Load conversation history
2. Append user message
3. Get tools and system prompt
4. Call `adapter.stream_chat(messages, tools, system_prompt)`
5. For each event from adapter:
   - If `content` → yield immediately
   - If `tool_call` → execute tool → yield `tool_result`
   - If `error` → log and yield error
6. Generator ends naturally

---

#### Method: `_get_conversation_context(session_id)`

```python
def _get_conversation_context(self, session_id: str) -> List[LLMMessage]:
```

**What it does**: Retrieves message history limited by `context_window_size`.

**Example** (context_window_size=10):
```python
[
    LLMMessage(role="user", content="What's my revenue?"),
    LLMMessage(role="assistant", content="Your revenue is..."),
    # ... up to 10 messages
]
```

**Uses**: `ContextManager` utility class to handle windowing logic.

---

#### Method: `_get_available_tools()`

```python
def _get_available_tools(self) -> List[Dict]:
```

**What it does**: Fetches tools from MCP server and formats for LLM.

**Flow**:
1. Initialize `MCPClient`
2. Call `mcp_client.list_tools()`
3. For each tool, call `adapter.format_tool_for_llm(tool)`
4. Return formatted tool list

**Tool format example** (after formatting):
```python
{
    "type": "function",
    "function": {
        "name": "list_documents",
        "description": "List documents in ERPNext",
        "parameters": {
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "DocType name"},
                "filters": {"type": "object"}
            },
            "required": ["doctype"]
        }
    }
}
```

---

#### Method: `_execute_tool(tool_call)`

```python
def _execute_tool(self, tool_call: Dict) -> Dict:
```

**What it does**: Executes a single tool via MCP.

**Parameters**:
```python
tool_call = {
    "name": "list_documents",
    "arguments": {"doctype": "Sales Order", "filters": {}}
}
```

**Returns**: Tool execution result from MCP.

---

#### Method: `_handle_tool_calls(messages, response, tools, system_prompt)`

```python
def _handle_tool_calls(
    self,
    messages: List[LLMMessage],
    response: LLMResponse,
    tools: List[Dict],
    system_prompt: str
) -> LLMResponse:
```

**What it does**: Recursively handles tool calls until final response.

**Logic** (multi-turn tool calling):
1. Add assistant message with tool calls to conversation
2. Execute each tool call
3. Add tool result messages to conversation
4. Call LLM again with all tool results
5. If new response has more tool calls → recurse
6. Else → return final response

**Example flow**:
```
User: "What are my pending orders and their total value?"
  ↓
LLM: tool_call(list_documents, doctype="Sales Order", status="Pending")
  ↓
Execute tool → returns [SO-001, SO-002, SO-003]
  ↓
LLM: tool_call(aggregate_data, field="grand_total", documents=[...])
  ↓
Execute tool → returns {"total": 125000}
  ↓
LLM: "You have 3 pending orders with total value of ₹125,000"
```

---

#### Method: `count_tokens(text)`

```python
def count_tokens(self, text: str) -> int:
```

**What it does**: Estimates token count for text using adapter's tokenizer.

---

### File: `llm/base_adapter.py`

**Purpose**: Abstract base class defining LLM adapter interface.

#### Classes

```python
@dataclass
class LLMMessage:
    role: str                    # "user", "assistant", "tool", "system"
    content: str
    tool_calls: Optional[List] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

@dataclass
class LLMResponse:
    content: str
    model: str
    token_count: int
    tool_calls: Optional[List] = None
    cost: float = 0.0
    finish_reason: str = "stop"

class LLMError(Exception):
    """Base exception for LLM errors"""
    pass
```

#### Abstract Methods (must be implemented by adapters):

```python
class BaseLLMAdapter(ABC):
    @abstractmethod
    def chat(self, messages: List[LLMMessage], tools=None, system_prompt=None) -> LLMResponse:
        pass
    
    @abstractmethod
    def stream_chat(self, messages: List[LLMMessage], tools=None, system_prompt=None) -> Generator:
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        pass
    
    @abstractmethod
    def format_tool_for_llm(self, tool: Dict) -> Dict:
        pass
    
    @abstractmethod
    def count_tokens(self, messages: List[LLMMessage]) -> int:
        pass
```

---

### Provider Adapters

Each adapter implements the base interface for specific LLM:

- **`claude_adapter.py`**: Uses `anthropic` SDK
- **`openai_adapter.py`**: Uses `openai` SDK
- **`gemini_adapter.py`**: Uses `google-generativeai` SDK
- **`local_adapter.py`**: Uses HTTP requests to Ollama endpoint

---

## 5. MCP Client Implementation

### File: `mcp/client.py`

**Purpose**: Client for communicating with Frappe_Assistant_Core's MCP endpoint using JSON-RPC 2.0.

#### Class: `MCPClient`

```python
class MCPClient:
    def __init__(self):
        self.settings = frappe.get_single("AI Chatbot Settings")
        self.endpoint = self.settings.mcp_endpoint
        self.initialized = False
        self.server_info = None
```

**Responsibilities**:
- Initialize MCP connection
- List available tools
- Execute tool calls
- Cache tool definitions
- Handle JSON-RPC 2.0 protocol

---

#### Method: `initialize()`

```python
def initialize(self) -> Dict:
```

**What it does**: Initializes MCP connection following protocol handshake.

**JSON-RPC Request**:
```json
{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "roots": {"listChanged": false}
        },
        "clientInfo": {
            "name": "frappe_ai_chatbot",
            "version": "1.0.0"
        }
    },
    "id": "uuid-generated"
}
```

**Response**:
```json
{
    "jsonrpc": "2.0",
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {...},
        "serverInfo": {
            "name": "Frappe_Assistant_Core",
            "version": "2.1.1"
        }
    },
    "id": "uuid-generated"
}
```

---

#### Method: `list_tools(use_cache=True)`

```python
def list_tools(self, use_cache: bool = True) -> List[Dict]:
```

**What it does**: Gets available tools from MCP server with optional caching.

**Caching**:
- Cache key: `mcp_tools_{user}`
- TTL: `tool_cache_ttl` seconds (default 300)
- Stored in Redis via `frappe.cache()`

**JSON-RPC Request**:
```json
{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "params": {},
    "id": "uuid"
}
```

**Response format**:
```json
{
    "result": {
        "tools": [
            {
                "name": "list_documents",
                "description": "List documents in ERPNext",
                "inputSchema": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            },
            // ... 21 more tools
        ]
    }
}
```

---

#### Method: `call_tool(name, arguments)`

```python
def call_tool(self, name: str, arguments: Dict) -> Any:
```

**What it does**: Executes a tool via MCP.

**JSON-RPC Request**:
```json
{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "list_documents",
        "arguments": {
            "doctype": "Sales Order",
            "filters": {"status": "Pending"}
        }
    },
    "id": "uuid"
}
```

**Response handling**:
- Success: Returns `result` object
- Error: Returns `{"error": true, "message": "...", "tool": "name"}`
- Logs errors to Error Log

---

#### Method: `get_tool_info(tool_name)`

```python
def get_tool_info(self, tool_name: str) -> Optional[Dict]:
```

**What it does**: Gets metadata for specific tool.

---

#### Method: `clear_cache()`

```python
def clear_cache(self):
```

**What it does**: Clears cached tool list from Redis.

---

#### Method: `_call_endpoint(request)`

```python
def _call_endpoint(self, request: Dict) -> Dict:
```

**What it does**: Makes HTTP request to MCP endpoint using `frappe.call()`.

**Endpoint**: `/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp`

---

#### Method: `test_connection()`

```python
def test_connection(self) -> Dict:
```

**What it does**: Tests MCP connectivity.

**Returns**:
```python
{
    "success": True,
    "message": "Connected to MCP server successfully",
    "server_info": {...}
}
```

---

#### Whitelisted Functions

```python
@frappe.whitelist()
def test_mcp_connection():
    """Callable from frontend"""

@frappe.whitelist()
def get_available_tools():
    """Callable from frontend"""

@frappe.whitelist()
def clear_tool_cache():
    """Callable from frontend"""
```

---

## 6. Frontend Application

### File: `ai_chatbot/page/ai_assistant/ai_assistant.js`

**Purpose**: Complete single-page application for chat interface.

**Status**: ⚠️ **Temporarily Disabled** - Launcher commented out in `hooks.py`. Widget provides better UX for most use cases.

#### Architecture

**Single-file structure** containing:
- Page initialization
- Class definition
- Embedded CSS
- UI setup methods
- Message handling logic
- Streaming event processing
- Session management

---

#### Class: `AIAssistant`

```javascript
class AIAssistant {
    constructor(page) {
        this.page = page;
        this.wrapper = $(this.page.wrapper);
        this.current_session = null;
        this.sessions = [];
        this.messages = [];
        this.is_streaming = false;
        this.current_stream_message = null;
    }
}
```

**Properties**:
- `page`: Frappe page object
- `wrapper`: jQuery wrapper for page content
- `current_session`: Active session object
- `sessions`: Array of all user sessions
- `messages`: Current session's message history
- `is_streaming`: Boolean flag for streaming state
- `current_stream_message`: DOM element for streaming message

---

#### Method: `async init()`

**What it does**: Initializes the application.

**Flow**:
1. Call `add_styles()` to inject CSS
2. Call `setup_toolbar()` to add buttons
3. Call `render_layout()` to create DOM structure
4. Call `load_sessions()` to fetch session list
5. Call `get_or_create_session()` to start

---

#### Method: `add_styles()`

**What it does**: Injects embedded CSS into `<head>`.

**CSS organization**:
```css
/* Container & Layout */
.ai-assistant-container { display: flex; height: calc(100vh - 120px); }

/* Sidebar */
.ai-sidebar { width: 280px; background: var(--card-bg); }
.session-item { padding: 12px; cursor: pointer; }

/* Chat Area */
.ai-chat-area { flex: 1; display: flex; flex-direction: column; }
.ai-messages { flex: 1; overflow-y: auto; padding: 20px; }

/* Messages */
.message-bubble { padding: 12px; margin: 8px 0; border-radius: 8px; }
.message-bubble.user { background: #2563eb; color: white; }
.message-bubble.assistant { background: #f3f4f6; color: #1f2937; }

/* Tool Cards */
.tool-call-card { border: 1px solid #e5e7eb; padding: 12px; margin: 8px 0; }

/* Input Area */
.ai-input-container { padding: 16px; border-top: 1px solid #e5e7eb; }
.ai-input-textarea { width: 100%; min-height: 60px; resize: vertical; }

/* Animations */
.typing-indicator { animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

/* Responsive */
@media (max-width: 768px) {
    .ai-sidebar { width: 60px; }
    .session-title { display: none; }
}
```

---

#### Method: `setup_toolbar()`

**What it does**: Adds buttons to page toolbar.

**Buttons added**:
- **"New Chat"**: Calls `create_new_session()`
- **"Settings"**: Opens settings dialog
- **"Clear History"**: Clears current session messages

---

#### Method: `render_layout()`

**What it does**: Creates DOM structure.

**HTML structure**:
```html
<div class="ai-assistant-container">
    <!-- Sidebar -->
    <div class="ai-sidebar">
        <div class="sessions-header">
            <h3>Sessions</h3>
        </div>
        <div class="sessions-list">
            <!-- Session items dynamically added -->
        </div>
    </div>
    
    <!-- Chat Area -->
    <div class="ai-chat-area">
        <!-- Messages Container -->
        <div class="ai-messages">
            <!-- Messages dynamically added -->
        </div>
        
        <!-- Input Area -->
        <div class="ai-input-container">
            <textarea class="ai-input-textarea" placeholder="Type a message..."></textarea>
            <button class="ai-send-button">
                <svg>...</svg> Send
            </button>
        </div>
    </div>
</div>
```

---

#### Method: `async load_sessions()`

**What it does**: Loads all sessions for current user.

**API call**:
```javascript
const response = await frappe.call({
    method: 'frappe_ai_chatbot.api.chat.get_all_sessions',
    args: { user: frappe.session.user }
});
this.sessions = response.message || [];
```

**Renders**: Session list in sidebar.

---

#### Method: `async get_or_create_session()`

**What it does**: Gets or creates active session.

**API call**:
```javascript
const response = await frappe.call({
    method: 'frappe_ai_chatbot.api.chat.get_or_create_session'
});
this.current_session = response.message;
await this.load_messages();
```

---

#### Method: `async load_messages()`

**What it does**: Loads messages for current session.

**API call**:
```javascript
const response = await frappe.call({
    method: 'frappe_ai_chatbot.api.chat.get_messages',
    args: {
        session_id: this.current_session.name,
        limit: 50
    }
});
this.messages = response.message || [];
this.render_messages();
```

---

#### Method: `render_messages()`

**What it does**: Renders all messages in chat area.

**For each message**:
```javascript
const bubble = $(`
    <div class="message-bubble ${message.role}">
        <div class="message-content">${this.format_content(message.content)}</div>
        <div class="message-time">${message.timestamp}</div>
    </div>
`);
$('.ai-messages').append(bubble);
```

**Auto-scrolls** to bottom after rendering.

---

#### Method: `format_content(text)`

**What it does**: Formats message content with Markdown.

**Features**:
- **Bold**: `**text**` → `<strong>text</strong>`
- **Italic**: `*text*` → `<em>text</em>`
- **Code blocks**: ` ```language\ncode\n``` ` → Syntax highlighted
- **Inline code**: `` `code` `` → `<code>code</code>`
- **Links**: Auto-detect URLs and make clickable

**Uses**: `marked.js` library (included in Frappe)

---

#### Method: `async send_message()`

**What it does**: Sends message with SSE streaming.

**Flow**:
1. Get message text from textarea
2. Validate not empty
3. Clear textarea and disable input
4. Append user message bubble immediately (optimistic update)
5. Create placeholder assistant bubble with typing indicator
6. Establish SSE connection:
   ```javascript
   const eventSource = new EventSource(
       `/api/method/frappe_ai_chatbot.api.stream.stream_chat?` +
       `session_id=${this.current_session.name}&message=${encodeURIComponent(text)}`
   );
   ```
7. Handle events:
   - **`content`**: Append text chunk to assistant bubble
   - **`tool_call`**: Show tool execution card
   - **`tool_result`**: Update tool card with result
   - **`done`**: Close connection, save message
   - **`error`**: Show error, close connection
8. Re-enable input

---

#### Event Handlers

```javascript
// Content streaming
eventSource.addEventListener('content', (e) => {
    const data = JSON.parse(e.data);
    this.current_stream_message.find('.content').append(data.content);
    this.scroll_to_bottom();
});

// Tool execution
eventSource.addEventListener('tool_call', (e) => {
    const data = JSON.parse(e.data);
    const tool_card = this.create_tool_card(data);
    this.current_stream_message.append(tool_card);
});

// Stream complete
eventSource.addEventListener('done', (e) => {
    eventSource.close();
    this.is_streaming = false;
    this.current_stream_message.find('.typing-indicator').remove();
});

// Error handling
eventSource.addEventListener('error', (e) => {
    eventSource.close();
    this.show_error('Connection lost or error occurred');
    this.is_streaming = false;
});
```

---

#### Method: `create_tool_card(tool_data)`

**What it does**: Creates visual card for tool execution.

**HTML**:
```html
<div class="tool-call-card">
    <div class="tool-header">
        <span class="tool-icon">🔧</span>
        <span class="tool-name">${tool_data.name}</span>
        <span class="tool-status loading">Running...</span>
    </div>
    <div class="tool-args">
        <pre>${JSON.stringify(tool_data.arguments, null, 2)}</pre>
    </div>
    <div class="tool-result" style="display:none;">
        <!-- Result populated when tool_result event received -->
    </div>
</div>
```

---

#### Method: `async create_new_session()`

**What it does**: Creates new chat session.

**API call**:
```javascript
const response = await frappe.call({
    method: 'frappe_ai_chatbot.api.chat.create_new_session'
});
this.current_session = response.message;
this.messages = [];
this.render_messages();
this.sessions.unshift(response.message);
this.render_sessions();
```

---

#### Keyboard Shortcuts

```javascript
// Ctrl/Cmd + Enter to send
$('.ai-input-textarea').on('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        this.send_message();
    }
});

// Escape to cancel streaming
$(document).on('keydown', (e) => {
    if (e.key === 'Escape' && this.is_streaming) {
        this.cancel_stream();
    }
});
```

---

### File: `public/js/ai_assistant_launcher.js`

**Purpose**: Adds "AI Assistant" button to navbar.

**Status**: ⚠️ **Temporarily Disabled** - Commented out in `hooks.py`.

**To re-enable**:
1. Edit `frappe_ai_chatbot/hooks.py`
2. Uncomment the `ai_assistant_launcher.js` line in `app_include_js` array
3. Run `bench build --app frappe_ai_chatbot`
4. Restart: `bench restart`

```javascript
frappe.ready(() => {
    // Add button to navbar
    $(document).on('startup', () => {
        // Check if user has enable_ai_chatbot field
        if (frappe.boot.user.enable_ai_chatbot) {
            // Add button to navbar
            $('.navbar-right').prepend(`
                <li>
                    <a href="/app/ai-assistant" class="ai-assistant-launcher">
                        <svg>...</svg> AI Assistant
                    </a>
                </li>
            `);
        }
    });
    
    // Keyboard shortcut: Ctrl+Shift+A
    $(document).on('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'A') {
            e.preventDefault();
            frappe.set_route('ai-assistant');
        }
    });
});
```

---

### File: `public/js/ai_chat_widget.js`

**Purpose**: Floating chat widget (bubble + slide-in panel) available on all pages.

**What it is**: Modern chat widget similar to Intercom/Drift that provides:
- Floating chat bubble in bottom-right corner (🤖 icon)
- Slide-in chat panel from right side
- Unread message badge on bubble
- Same backend as full-page interface
- Non-intrusive, works on any page

#### Architecture

**Single-file structure** containing:
- `AIChatWidget` class
- Embedded CSS (300+ lines)
- Complete UI logic
- SSE streaming integration
- Session management

**Key difference from full-page**: Widget is more compact (400px panel width) and designed to be used while working on other pages.

---

#### Class: `AIChatWidget`

```javascript
class AIChatWidget {
    constructor() {
        this.is_open = false;           // Panel visibility state
        this.is_streaming = false;      // Streaming state
        this.current_session = null;    // Active session
        this.messages = [];             // Message history
        this.unread_count = 0;          // Unread message count
        this.bubble = null;             // Chat bubble element
        this.panel = null;              // Chat panel element
        this.current_stream_message = null; // Streaming message element
    }
}
```

**Properties**:
- `is_open`: Boolean flag for panel visibility
- `is_streaming`: Prevents duplicate sends during streaming
- `current_session`: Session object from API
- `messages`: Array of message objects
- `unread_count`: Number shown in badge
- `bubble`: jQuery object for chat bubble
- `panel`: jQuery object for chat panel
- `current_stream_message`: DOM element being updated during streaming

---

#### Method: `async init()`

**What it does**: Initializes the widget.

**Flow**:
1. Call `check_user_permission()` to verify chatbot is enabled
2. If enabled, call `add_styles()` to inject CSS
3. Call `create_chat_bubble()` to add bubble to page
4. Call `create_chat_panel()` to add panel (hidden initially)
5. Call `get_or_create_session()` to initialize session
6. Attach event handlers (click, keyboard shortcuts)

**Initialization check**:
```javascript
if (window.location.pathname === '/app/ai-assistant') {
    return; // Don't load widget on full-page interface
}
```

---

#### Method: `async check_user_permission()`

**What it does**: Checks if chatbot is enabled for current user.

**API call**:
```javascript
const response = await frappe.call({
    method: 'frappe_ai_chatbot.api.chat.check_permission'
});
return response.message.enabled;
```

**Returns**: Boolean - if false, widget won't initialize.

---

#### Method: `add_styles()`

**What it does**: Injects embedded CSS into `<head>`.

**CSS highlights**:
```css
/* Chat Bubble (fixed bottom-right) */
.ai-chat-bubble {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 60px;
    height: 60px;
    border-radius: 30px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    cursor: pointer;
    z-index: 9998;
}

/* Unread Badge */
.ai-chat-bubble-badge {
    position: absolute;
    top: -5px;
    right: -5px;
    background: #ef4444;
    color: white;
    border-radius: 10px;
    padding: 2px 6px;
}

/* Chat Panel (slide-in from right) */
.ai-chat-panel {
    position: fixed;
    right: -400px; /* Hidden by default */
    top: 0;
    width: 400px;
    height: 100vh;
    background: white;
    box-shadow: -2px 0 10px rgba(0,0,0,0.1);
    transition: right 0.3s ease;
    z-index: 9999;
}

.ai-chat-panel.open {
    right: 0; /* Slide in */
}

/* Messages Container */
.ai-chat-messages {
    height: calc(100vh - 160px);
    overflow-y: auto;
    padding: 20px;
}

/* Message Bubbles */
.ai-message-bubble.user {
    background: #2563eb;
    color: white;
    margin-left: auto;
    max-width: 80%;
}

.ai-message-bubble.assistant {
    background: #f3f4f6;
    color: #1f2937;
    margin-right: auto;
    max-width: 80%;
}

/* Typing Indicator (animated dots) */
.ai-typing-indicator {
    display: flex;
    gap: 4px;
}

.ai-typing-dot {
    width: 8px;
    height: 8px;
    background: #9ca3af;
    border-radius: 50%;
    animation: typing 1.4s infinite;
}

@keyframes typing {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-10px); }
}

/* Input Area */
.ai-chat-input-area {
    padding: 16px;
    border-top: 1px solid #e5e7eb;
}

.ai-chat-textarea {
    width: 100%;
    min-height: 40px;
    max-height: 120px;
    resize: none;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 8px;
}

/* Mobile Responsive */
@media (max-width: 768px) {
    .ai-chat-panel {
        width: 100%;
        right: -100%;
    }
}
```

---

#### Method: `create_chat_bubble()`

**What it does**: Creates and appends chat bubble to page.

**HTML structure**:
```html
<div class="ai-chat-bubble">
    <div class="ai-chat-bubble-icon">🤖</div>
    <div class="ai-chat-bubble-badge" style="display: none;">0</div>
</div>
```

**Click handler**: Calls `toggle_panel()` to show/hide chat.

**Appends to**: `<body>` element (so it's always visible).

---

#### Method: `create_chat_panel()`

**What it does**: Creates and appends chat panel to page.

**HTML structure**:
```html
<div class="ai-chat-panel">
    <!-- Header -->
    <div class="ai-chat-header">
        <h3>AI Assistant</h3>
        <div class="ai-chat-header-actions">
            <button class="ai-chat-new-btn">➕</button>
            <button class="ai-chat-clear-btn">🗑️</button>
            <button class="ai-chat-close-btn">✕</button>
        </div>
    </div>
    
    <!-- Messages -->
    <div class="ai-chat-messages">
        <!-- Messages dynamically added here -->
    </div>
    
    <!-- Input Area -->
    <div class="ai-chat-input-area">
        <textarea class="ai-chat-textarea" placeholder="Type a message..."></textarea>
        <button class="ai-chat-send-btn">📤 Send</button>
    </div>
</div>
```

**Event handlers attached**:
- **Close button**: Calls `toggle_panel()` to hide
- **New button**: Calls `create_new_session()`
- **Clear button**: Calls `clear_history()`
- **Send button**: Calls `send_message()`
- **Textarea Ctrl+Enter**: Calls `send_message()`
- **Textarea input**: Auto-resize up to 3 lines

---

#### Method: `toggle_panel()`

**What it does**: Opens/closes chat panel with smooth animation.

**Logic**:
```javascript
if (this.is_open) {
    this.panel.removeClass('open');  // Slides out to right
    this.is_open = false;
} else {
    this.panel.addClass('open');     // Slides in from right
    this.is_open = true;
    this.unread_count = 0;           // Clear unread badge
    this.bubble.find('.ai-chat-bubble-badge').removeClass('show');
}
```

---

#### Method: `async send_message()`

**What it does**: Sends user message and streams AI response via SSE.

**Flow**:
1. Get message text from textarea, validate not empty
2. Clear textarea and reset height
3. Disable input controls (`set_input_state(false)`)
4. Set `is_streaming = true`
5. Add user message bubble immediately (optimistic UI)
6. Create assistant placeholder with typing indicator (••• animation)
7. Establish SSE connection to `/api/method/frappe_ai_chatbot.api.stream.stream_chat`
8. Listen for SSE events:
   - `content`: Append text chunks to message
   - `tool_call`: Add tool execution card
   - `tool_result`: Update tool card with result
   - `done`: Close connection, add timestamp, re-enable input
   - `error`: Show error message, re-enable input
9. If panel is closed, increment `unread_count` and show badge

**SSE event handling**:
```javascript
const url = `/api/method/frappe_ai_chatbot.api.stream.stream_chat?session_id=${session_id}&message=${message}`;
const eventSource = new EventSource(url);

let accumulated_content = '';

eventSource.addEventListener('content', (e) => {
    const data = JSON.parse(e.data);
    accumulated_content += data.content;
    this.current_stream_message.find('.ai-message-content').html(
        this.format_content(accumulated_content)
    );
    this.scroll_to_bottom();
});

eventSource.addEventListener('tool_call', (e) => {
    const data = JSON.parse(e.data);
    const tool_card = this.create_tool_card(data);
    this.current_stream_message.find('.ai-message-content').append(tool_card);
});

eventSource.addEventListener('done', (e) => {
    eventSource.close();
    this.is_streaming = false;
    this.set_input_state(true);
    
    // Show notification if panel closed
    if (!this.is_open) {
        this.unread_count++;
        this.bubble.find('.ai-chat-bubble-badge')
            .text(this.unread_count)
            .addClass('show');
    }
});
```

---

#### Method: `create_message_bubble(message)`

**What it does**: Creates DOM element for a message.

**Parameters**:
- `message`: Object with `{role, content, timestamp, tool_calls?}`

**Returns**: jQuery element
```html
<div class="ai-message-bubble user/assistant">
    <div class="ai-message-content">[formatted content]</div>
    <div class="ai-message-time">14:30</div>
</div>
```

**Role styling**:
- `user`: Blue background, white text, right-aligned
- `assistant`: Gray background, dark text, left-aligned

---

#### Method: `create_tool_card(tool)`

**What it does**: Creates visual card for tool execution.

**Returns**: jQuery element
```html
<div class="ai-tool-card">
    <div class="ai-tool-card-header">
        <span>🔧</span>
        <span class="ai-tool-card-name">[tool.name]</span>
    </div>
</div>
```

**Styling**: Blue background, rounded corners, compact display.

---

#### Method: `format_content(text)`

**What it does**: Applies basic Markdown formatting to text.

**Transformations**:
- `**bold**` → `<strong>bold</strong>`
- `*italic*` → `<em>italic</em>`
- `` `code` `` → `<code>code</code>`
- `\n` → `<br>`

**Note**: Simpler than full-page interface (no code block syntax highlighting in widget).

---

#### Method: `set_input_state(enabled)`

**What it does**: Enables/disables textarea and send button.

**Used**: During streaming to prevent duplicate sends.

---

#### Method: `scroll_to_bottom()`

**What it does**: Auto-scrolls messages container to show latest message.

**Called**: After adding messages or updating streaming content.

---

#### Method: `async create_new_session()`

**What it does**: Creates new chat session.

**Flow**:
1. Close current session via API
2. Call `get_or_create_session()` to create new one
3. Clear messages and render empty state
4. Show success alert

---

#### Method: `async clear_history()`

**What it does**: Deletes all messages in current session.

**Flow**:
1. Show confirmation dialog
2. Call API to delete messages
3. Clear local `messages` array
4. Re-render (empty state)

---

#### Initialization

**Widget loads automatically** on all pages except `/app/ai-assistant`:

```javascript
frappe.ready(() => {
    if (window.location.pathname !== '/app/ai-assistant') {
        window.ai_chat_widget = new AIChatWidget();
    }
});
```

**Global access**: Widget instance available at `window.ai_chat_widget`.

---

#### Widget vs Full-Page Comparison

| Feature | Widget | Full-Page |
|---------|--------|-----------|
| **Location** | All pages | `/app/ai-assistant` only |
| **UI** | Bubble + slide-in panel | Full screen |
| **Width** | 400px (100% on mobile) | Full width |
| **Sidebar** | ❌ No | ✅ Session list |
| **Unread Badge** | ✅ Yes | ❌ No |
| **Keyboard Shortcut** | ❌ No | ✅ Ctrl+Shift+A |
| **Markdown** | Basic | Full (code highlighting) |
| **Backend** | Same API | Same API |
| **Session** | Shared | Shared |

---

## 7. Database Schema (DocTypes)

### DocType: `AI Chatbot Settings` (Single)

**Purpose**: Global configuration for AI chatbot.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | Check | Enable/disable chatbot globally |
| `llm_provider` | Select | "claude", "openai", "gemini", "local" |
| `claude_api_key` | Password | Anthropic API key |
| `claude_model` | Data | Model name (e.g., "claude-3-5-sonnet-20241022") |
| `openai_api_key` | Password | OpenAI API key |
| `openai_model` | Data | Model name (e.g., "gpt-4o") |
| `gemini_api_key` | Password | Google Gemini API key |
| `gemini_model` | Data | Model name (e.g., "gemini-1.5-flash") |
| `local_endpoint` | Data | Local model endpoint (e.g., "http://localhost:11434/v1") |
| `local_model` | Data | Model name (e.g., "llama3:8b") |
| `temperature` | Float | 0.0 - 2.0 (default: 0.7) |
| `max_tokens` | Int | Maximum response tokens (default: 4096) |
| `top_p` | Float | 0.0 - 1.0 (default: 0.9) |
| `context_window_size` | Int | Number of messages to keep in context (default: 10) |
| `enable_tool_calling` | Check | Enable MCP tool execution |
| `mcp_endpoint` | Data | MCP server endpoint |
| `enable_tool_caching` | Check | Cache tool definitions |
| `tool_cache_ttl` | Int | Cache TTL in seconds (default: 300) |
| `system_prompt` | Text | System prompt template |
| `enable_rate_limiting` | Check | Enable rate limits |
| `rate_limit_per_hour` | Int | Messages per hour per user |
| `rate_limit_tokens_per_day` | Int | Total tokens per day per user |

**Controller**: `ai_chatbot_settings.py`
- `validate()`: Validates API keys and numeric ranges
- `get_settings()`: Returns public settings (excludes API keys)
- `test_llm_connection()`: Tests provider connectivity

---

### DocType: `AI Chat Session`

**Purpose**: Represents a conversation session.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `user` | Link (User) | Session owner |
| `title` | Data | Session title |
| `status` | Select | "Active", "Closed", "Archived" |
| `started_at` | Datetime | When session started |
| `last_activity` | Datetime | Last message timestamp |
| `llm_provider` | Data | Provider used in this session |
| `model_name` | Data | Model used |
| `total_messages` | Int | Message count |
| `total_tokens` | Int | Total tokens used |
| `estimated_cost` | Currency | Estimated API cost |

**Controller**: `ai_chat_session.py`
- `validate()`: Sets default values
- `update_activity()`: Updates timestamp (without triggering modified)
- `increment_message_count()`: Increments counter
- `add_tokens(count, cost)`: Adds tokens and cost
- `close_session()`: Marks as closed
- `archive_old_sessions(days)`: Archives old sessions

**Indexes**:
- `user, status, last_activity` (for fetching active sessions)

---

### DocType: `AI Chat Message`

**Purpose**: Individual message in a session.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `session` | Link (AI Chat Session) | Parent session |
| `role` | Select | "user", "assistant", "tool" |
| `content` | Long Text | Message content |
| `timestamp` | Datetime | When message was created |
| `token_count` | Int | Tokens in this message |
| `model_used` | Data | Model that generated response |
| `tool_calls` | JSON | Tool calls made (if any) |

**Controller**: `ai_chat_message.py`
- `get_session_messages(session_id, limit, offset)`: Retrieves messages
- `delete_session_messages(session_id)`: Deletes all messages in session

**Indexes**:
- `session, timestamp` (for chronological ordering)

---

### DocType: `AI Chat Feedback`

**Purpose**: User feedback on AI responses.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `message` | Link (AI Chat Message) | Message being rated |
| `user` | Link (User) | User providing feedback |
| `rating` | Select | "Positive", "Negative" |
| `feedback_text` | Text | Optional comment |
| `timestamp` | Datetime | When feedback given |

**Controller**: `ai_chat_feedback.py`

---

### Custom Field on User DocType

**Field**: `enable_ai_chatbot`
- **Type**: Check
- **Default**: 1
- **Description**: Controls whether user can access AI chatbot
- **Created by**: `setup.py` during installation

---

## 8. Configuration & Setup

### File: `pyproject.toml`

```toml
[project]
name = "frappe_ai_chatbot"
version = "1.0.0"
description = "Embedded AI chatbot for ERPNext with LLM integration"
authors = []
dependencies = [
    "frappe~=15.0",
    "httpx>=0.24.0",
    "sse-starlette>=1.6.5"
]
requires-python = ">=3.11"
readme = "README.md"
license = {text = "MIT"}

[build-system]
requires = ["flit_core >=3.4,<4"]
build-backend = "flit_core.buildapi"

[tool.bench]
frappe_version = 15

[tool.isort]
profile = "black"

[tool.black]
line-length = 120
```

**Dependencies explained**:
- `frappe~=15.0`: Framework (required)
- `httpx>=0.24.0`: Async HTTP client for MCP calls
- `sse-starlette>=1.6.5`: SSE utilities (not actually used in current code)

**Note**: LLM SDKs (`anthropic`, `openai`, etc.) are NOT listed as dependencies. They should be installed separately based on which provider is used.

---

### File: `hooks.py`

**Key hooks**:

```python
# App metadata (required)
app_name = "frappe_ai_chatbot"
app_title = "Frappe AI Chatbot"
app_description = "Embedded AI chatbot for ERPNext with LLM integration"
app_icon = "octicon octicon-comment-discussion"
app_color = "blue"
app_version = "1.0.0"

# Global JS inclusion (navbar button)
app_include_js = "/assets/frappe_ai_chatbot/js/ai_assistant_launcher.js"

# Post-installation hook
after_install = "frappe_ai_chatbot.setup.after_install"

# Scheduled tasks
scheduler_events = {
    "hourly": [
        "frappe_ai_chatbot.tasks.cleanup_old_sessions"
    ],
    "daily": [
        "frappe_ai_chatbot.tasks.generate_usage_reports"
    ]
}

# Fixtures (auto-exported custom fields)
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "in", ["User"]],
            ["fieldname", "in", ["enable_ai_chatbot"]]
        ]
    }
]
```

---

### File: `setup.py`

**Function**: `after_install()`

**What it does**: Runs after app installation.

**Tasks**:
1. Create custom field on User DocType (`enable_ai_chatbot`)
2. Create default AI Chatbot Settings document
3. Commit to database
4. Print success message

**Default settings created**:
```python
{
    "enable_chatbot": 1,
    "default_provider": "Claude",
    "claude_model": "claude-3-5-sonnet-20241022",
    "openai_model": "gpt-4o",
    "gemini_model": "gemini-1.5-flash",
    "max_tokens": 4096,
    "temperature": 0.7,
    "context_window_size": 10,
    "enable_tool_calling": 1,
    "enable_rate_limiting": 1,
    "rate_limit_per_hour": 50,
    "mcp_endpoint": "/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp",
    "system_prompt": "You are a helpful AI assistant..."
}
```

---

## 9. Data Flow Diagrams

### Non-Streaming Chat Flow

```
User clicks "Send" in UI
         ↓
ai_assistant.js: send_message()
         ↓
POST /api/method/frappe_ai_chatbot.api.chat.send_message
    args: {session_id, message}
         ↓
chat.py: send_message()
    1. Validate session ownership
    2. Check rate limits
    3. Save user message to DB
         ↓
llm/router.py: chat()
    1. Load conversation history (last N messages)
    2. Get available tools from MCP
    3. Call adapter.chat(messages, tools)
         ↓
llm/claude_adapter.py: chat()
    1. Format messages for Claude API
    2. Call anthropic.messages.create()
    3. Parse response
         ↓
    If tool calls in response:
        ↓
    llm/router.py: _handle_tool_calls()
        1. For each tool call:
            ↓
        mcp/executor.py: execute()
            ↓
        mcp/client.py: call_tool()
            ↓
        POST /api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp
            JSON-RPC: {"method": "tools/call", "params": {...}}
            ↓
        [Frappe_Assistant_Core executes tool]
            ↓
        Returns: tool result
        2. Add tool results to conversation
        3. Call LLM again with results
        4. Repeat if more tool calls
         ↓
llm/router.py: returns final response
         ↓
chat.py: send_message()
    1. Save assistant message to DB
    2. Update session statistics
    3. Return response
         ↓
ai_assistant.js: Renders assistant message
```

---

### Streaming Chat Flow (SSE)

```
User clicks "Send" in UI
         ↓
ai_assistant.js: send_message()
         ↓
new EventSource('/api/method/...stream_chat?session_id=...&message=...')
         ↓
stream.py: stream_chat()
    1. Set SSE headers
    2. Validate session + permissions
    3. Check rate limits
    4. Save user message → yield 'user_message' event
         ↓
llm/router.py: stream_chat()
    1. Load conversation history
    2. Get available tools
    3. Call adapter.stream_chat(messages, tools)
         ↓
llm/claude_adapter.py: stream_chat()
    1. Call anthropic.messages.stream()
    2. For each chunk:
         ↓
         yield {"type": "content", "content": "text chunk"}
         ↓
stream.py: forwards to client
    yield 'event: content\ndata: {"content": "..."}\n\n'
         ↓
ai_assistant.js: EventSource listener
    eventSource.addEventListener('content', (e) => {
        // Append chunk to message bubble
        this.current_stream_message.append(e.data.content);
    });
         ↓
[User sees text appearing in real-time]
         ↓
    If tool call in stream:
         ↓
llm/claude_adapter.py: yields {"type": "tool_call", "tool": {...}}
         ↓
stream.py: stream_chat()
    1. Execute tool via mcp/executor.py
    2. yield 'tool_call' event
    3. yield 'tool_result' event
         ↓
ai_assistant.js: 
    - Shows tool execution card
    - Updates with result
         ↓
stream.py: stream_chat()
    1. Save complete assistant message to DB
    2. Update rate limiter
    3. yield 'done' event
         ↓
ai_assistant.js:
    eventSource.close();
    // Remove typing indicator
```

---

### MCP Tool Execution Flow

```
LLM decides to call tool
         ↓
Tool call: {
    name: "list_documents",
    arguments: {"doctype": "Sales Order", "filters": {...}}
}
         ↓
llm/router.py: _execute_tool()
         ↓
mcp/executor.py: execute()
         ↓
mcp/client.py: call_tool()
    1. Check initialization
    2. Build JSON-RPC request:
       {
           "jsonrpc": "2.0",
           "method": "tools/call",
           "params": {
               "name": "list_documents",
               "arguments": {...}
           },
           "id": "uuid"
       }
    3. POST to MCP endpoint
         ↓
Frappe_Assistant_Core: handle_mcp()
    1. Parse JSON-RPC request
    2. Route to appropriate tool
    3. Execute tool with Frappe permissions
    4. Return JSON-RPC response
         ↓
mcp/client.py: call_tool()
    1. Parse response
    2. Handle errors if any
    3. Return result
         ↓
llm/router.py: _execute_tool()
    Returns: {"documents": [...], "count": 15}
         ↓
llm/router.py: _handle_tool_calls()
    1. Add tool result to conversation:
       {
           role: "tool",
           content: JSON.stringify(result),
           name: "list_documents"
       }
    2. Call LLM again with tool results
         ↓
LLM generates final response using tool data
```

---

### Session Lifecycle

```
User opens /app/ai-assistant
         ↓
ai_assistant.js: init()
         ↓
frappe.call('get_or_create_session')
         ↓
chat.py: get_or_create_session()
    1. Check if User.enable_ai_chatbot = 1
    2. Check if AI Chatbot Settings.enabled = 1
    3. Query: SELECT * FROM `tabAI Chat Session`
              WHERE user = ? AND status = 'Active'
              ORDER BY last_activity DESC LIMIT 1
         ↓
    If exists:
        - Load session
        - Update last_activity
        - Return session
         ↓
    If not exists:
        - Create new AI Chat Session:
          {
              user: current user,
              title: "Chat on 2025-10-14 10:30",
              status: "Active",
              started_at: NOW(),
              last_activity: NOW(),
              llm_provider: from settings,
              model_name: from settings
          }
        - INSERT into database
        - Return new session
         ↓
ai_assistant.js: Stores session object
         ↓
frappe.call('get_messages', {session_id: ...})
         ↓
chat.py: get_messages()
    SELECT * FROM `tabAI Chat Message`
    WHERE session = ?
    ORDER BY timestamp ASC
    LIMIT 50
         ↓
ai_assistant.js: Renders message history
         ↓
[User interacts with chat...]
         ↓
After 30 days of inactivity:
         ↓
Scheduled task: tasks.cleanup_old_sessions()
    UPDATE `tabAI Chat Session`
    SET status = 'Archived'
    WHERE last_activity < DATE_SUB(NOW(), INTERVAL 30 DAY)
```

---

## 10. Complete API Reference

### REST API Endpoints

#### `@frappe.whitelist()`
Base URL: `/api/method/frappe_ai_chatbot.api.chat`

---

**`get_or_create_session()`**
- **Method**: GET/POST
- **Auth**: Required
- **Parameters**: None
- **Returns**: Session object

---

**`send_message(session_id, message, stream=False)`**
- **Method**: POST
- **Auth**: Required
- **Parameters**:
  - `session_id` (str): Session ID
  - `message` (str): User message
  - `stream` (bool): Unused (use stream_chat for streaming)
- **Returns**: 
  ```json
  {
      "success": true,
      "message": {...},
      "session": {...}
  }
  ```

---

**`get_messages(session_id, limit=50, offset=0)`**
- **Method**: GET/POST
- **Auth**: Required
- **Parameters**:
  - `session_id` (str)
  - `limit` (int): Default 50
  - `offset` (int): Default 0
- **Returns**: Array of message objects

---

**`clear_history(session_id)`**
- **Method**: POST
- **Auth**: Required
- **Parameters**: `session_id` (str)
- **Returns**: `{"success": true}`

---

**`close_session(session_id)`**
- **Method**: POST
- **Auth**: Required
- **Parameters**: `session_id` (str)
- **Returns**: `{"success": true}`

---

**`get_settings()`**
- **Method**: GET/POST
- **Auth**: Required
- **Parameters**: None
- **Returns**: Settings object (API keys excluded)

---

### SSE Endpoint

**`stream_chat(session_id, message)`**
- **URL**: `/api/method/frappe_ai_chatbot.api.stream.stream_chat`
- **Method**: GET (SSE requires GET)
- **Auth**: Required
- **Parameters** (query string):
  - `session_id` (str)
  - `message` (str)
- **Response**: text/event-stream

**Event Types**:
- `user_message`: User message confirmation
- `content`: Text chunk
- `tool_call`: Tool execution started
- `tool_result`: Tool execution completed
- `done`: Stream complete
- `error`: Error occurred

---

### MCP Endpoints

**`test_mcp_connection()`**
- **Method**: GET/POST
- **Auth**: Required
- **Returns**: Connection test result

---

**`get_available_tools()`**
- **Method**: GET/POST
- **Auth**: Required
- **Returns**: Array of tool definitions

---

**`clear_tool_cache()`**
- **Method**: POST
- **Auth**: Required
- **Returns**: `{"success": true}`

---

### DocType Endpoints

**`test_llm_connection(provider=None)`**
- **Method**: POST
- **Auth**: Required (System Manager)
- **Parameters**: `provider` (str, optional)
- **Returns**: Connection test result

---

**`close_session(session_id)`** (AI Chat Session)
- **Method**: POST
- **Auth**: Required
- **Parameters**: `session_id` (str)
- **Returns**: `{"success": true}`

---

**`archive_old_sessions(days=30)`** (AI Chat Session)
- **Method**: POST
- **Auth**: Required (System Manager)
- **Parameters**: `days` (int, default 30)
- **Returns**: `{"archived_count": N}`

---

**Codebase Version**: 1.0.0  
**Frappe Version**: v15+
