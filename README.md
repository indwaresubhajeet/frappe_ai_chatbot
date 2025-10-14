# Frappe AI Chatbot

🤖 **AI Assistant for ERPNext** - Chat with your ERP system using AI.

## Overview

A complete AI Assistant interface embedded in ERPNext with **two ways to chat**:

### 💬 Floating Chat Widget (Recommended!)
- **Always available** - Floating chat bubble on every page (bottom-right corner)
- **Click to chat** - Instant slide-in panel from the right
- **Stay on any page** - Chat while working on forms, lists, or reports
- **Unread notifications** - Badge shows new messages when minimized
- **Modern UI** - Inspired by Intercom, Drift, Zendesk Chat

### 📄 Full-Page Interface *(Temporarily Disabled)*
- **Dedicated page** at `/app/ai-assistant`
- **Distraction-free** - Full-screen chat experience
- **Session sidebar** - Browse and manage chat history
- **Note**: Currently disabled in favor of the floating widget. Can be re-enabled in `hooks.py`

### Features
- Chat with your ERP data using natural language
- Access 22+ powerful tools (search, reports, analysis, workflow automation)
- Use Claude, OpenAI, Gemini, or local LLMs
- Get real-time streaming responses
- Manage conversation history

**Works on remote servers!** Access from any browser - server does all the work!

---

## 🖥️ Remote Server? No Problem!

**Running Frappe on a remote server?** This chatbot works perfectly!

- ✅ Access from your local PC's browser
- ✅ No localhost required
- ✅ Server handles everything
- ✅ Just use your server URL in OAuth setup

📘 **See [SERVER_DEPLOYMENT_GUIDE.md](./SERVER_DEPLOYMENT_GUIDE.md)** for detailed remote server setup!

---

## Quick Start

### 1. Installation

```bash
# Get the app
cd ~/frappe-bench
bench get-app /path/to/frappe_ai_chatbot

# Install on your site
bench --site your-site install-app frappe_ai_chatbot

# Build assets
bench build --app frappe_ai_chatbot
```

### 2. Configuration

1. Open ERPNext → Search for **"AI Chatbot Settings"**
2. Check ✅ **"Enable Chatbot"** checkbox
3. Configure your LLM:

**For Gemini (FREE Trial - Best for Testing!):**
```
LLM Provider: Gemini
API Key: [Get FREE at https://makersuite.google.com/app/apikey]
Model: gemini-1.5-flash (Fast & has generous free tier!)
```

**For Claude (Best Quality):**
```
LLM Provider: Claude
API Key: sk-ant-api03-...
Model: claude-3-5-sonnet-20241022
```

**For OpenAI:**
```
LLM Provider: OpenAI
API Key: sk-proj-...
Model: gpt-4o
```

**For Local (Ollama - Free & Private):**
```
LLM Provider: Local
Endpoint: http://localhost:11434
Model: llama3:8b
```

4. Set **MCP Endpoint**: `http://localhost:8000/fac/mcp`
5. Click **Save**

**Important**: Use exact capitalization: `Claude`, `OpenAI`, `Gemini`, or `Local`

### 3. Enable for Users

**IMPORTANT**: The chatbot must be enabled at two levels:

**A. Global Settings** (one-time):
1. Search → **"AI Chatbot Settings"**
2. Check ✅ **"Enable Chatbot"**
3. Save

**B. Per-User** (for each user):
1. Go to **User List**
2. Open your user profile
3. Check ✅ **"Enable AI Chatbot"** (should be checked by default)
4. Save

### 4. Start Chatting!

**Using the Floating Widget (Recommended):**
1. Look for the **🤖 chat bubble** in the bottom-right corner
2. Click it to open the chat panel
3. Type your question and hit Enter or Ctrl+Enter
4. Chat stays with you on any page!

**Using the Full-Page Interface:** *(Temporarily Disabled)*
- Full-page interface is currently disabled in `hooks.py`
- To re-enable: Uncomment the launcher line in `frappe_ai_chatbot/hooks.py`
- Then rebuild: `bench build --app frappe_ai_chatbot` and restart
- Access via: Navbar button OR Ctrl+Shift+A OR `/app/ai-assistant`

---

## Features

### 🎈 Floating Chat Widget
- **Always accessible** - Chat bubble follows you on every page
- **Slide-in panel** - Smooth animation from right side
- **Unread badge** - Shows number of new messages
- **Works anywhere** - Use while editing forms, viewing lists, etc.
- **Auto-resize textarea** - Expands as you type
- **Keyboard shortcuts** - Ctrl+Enter to send

### 💬 Full-Page Interface *(Temporarily Disabled)*
- Beautiful, responsive UI inspired by Claude Desktop
- Sidebar with session management
- Message history with formatting
- Tool execution visualization
- Mobile responsive
- **Status**: Currently disabled - widget provides better UX for most use cases

### 🔧 Tool Integration
- Full access to 22 Frappe_Assistant_Core MCP tools
- Search documents, run reports, analyze data
- Visual tool execution cards with status
- Automatic tool discovery

### 🎨 Smart Features
- Markdown formatting (code blocks, bold, italic)
- Typing indicators
- Auto-scroll to latest message
- Session history
- Dark mode support
- ERPNext theme integration

### 🔐 Security
- Frappe session-based authentication
- User permission inheritance
- Rate limiting (configurable)
- No API keys exposed to frontend

### 🔒 OAuth Configuration (Required)

The chatbot connects to Frappe_Assistant_Core (FAC) using **OAuth 2.0 Authorization Code Flow with PKCE**. This is the ONLY authentication method supported by FAC v2.2.0+.

#### Key Concepts

- **Per-User Authorization**: Each user authorizes the chatbot once to act on their behalf
- **Automatic Token Management**: Tokens are stored securely and refreshed automatically
- **One-Time Setup**: Admin configures OAuth Client once, users authorize on first use
- **Secure**: Uses industry-standard OAuth 2.0 with PKCE (RFC 7636)

#### Setup Steps

**Step 1: Enable OAuth in FAC**

1. Login to Frappe as **Administrator**
2. Go to: **Assistant Core Settings** (search for it)
3. Click **OAuth** tab
4. Check these boxes:
   - ✅ **Show Authorization Server Metadata**
   - ✅ **Enable Dynamic Client Registration**
   - ✅ **Show Protected Resource Metadata**
5. Click **Save**

**Step 2: Create OAuth Client**

Create an OAuth Client using Frappe's standard OAuth Client DocType:

```bash
# Option A: Via Frappe UI (Recommended)
1. Go to: OAuth Client (list view) → New
2. Fill fields:
   - App Name: AI Chatbot
   - Response Type: Code
   - Grant Type: Authorization Code
   - Redirect URIs: http://your-site.com/api/method/frappe_ai_chatbot.api.oauth.handle_callback
   - Scopes: all openid
   - Skip Authorization: Unchecked (users must authorize)
3. Save
4. Copy the Client ID (and Client Secret if generated)
```

```bash
# Option B: Via bench console
bench --site your-site console

# In console:
oauth_client = frappe.get_doc({
    "doctype": "OAuth Client",
    "app_name": "AI Chatbot",
    "redirect_uris": "http://your-site.com/api/method/frappe_ai_chatbot.api.oauth.handle_callback",
    "default_redirect_uri": "http://your-site.com/api/method/frappe_ai_chatbot.api.oauth.handle_callback",
    "response_type": "Code",
    "grant_type": "Authorization Code",
    "scopes": "all openid",
    "skip_authorization": 0
})
oauth_client.insert()
frappe.db.commit()

print(f"Client ID: {oauth_client.client_id}")
print(f"Client Secret: {oauth_client.get_password('client_secret')}")
```

**Important Notes**:
- Replace `http://your-site.com` with your **actual server URL**
- **Remote server**: Use `https://your-server.com` (your server's public URL)
- **Development**: Use `http://192.168.1.100:8000` (or your server's IP:port)
- **Frappe Cloud**: Use `https://your-site.frappe.cloud`
- The redirect URI must **exactly match** your server URL

💡 **Tip**: To get your server URL automatically:
```bash
bench --site your-site console
>>> import frappe
>>> print(frappe.utils.get_url())
```

**Step 3: Configure AI Chatbot Settings**

1. Go to: **AI Chatbot Settings**
2. Fill in the OAuth section:
   - **OAuth Client ID**: Your Client ID from Step 2
   - **OAuth Client Secret**: Your Client Secret (if created, leave blank for public clients)
   - **OAuth Token URL**: `/api/method/frappe.integrations.oauth2.get_token` (default)
   - **MCP Endpoint**: `/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp` (default)
3. Click **Save**

**Step 4: User Authorization (Per User)**

When a user first opens the chatbot:

1. User navigates to chatbot (floating widget or `/app/ai-assistant`)
2. Dialog appears: **"Authorization Required"**
3. User clicks **"Authorize Now"**
4. Redirected to Frappe's OAuth authorization page
5. User clicks **"Allow"** (since already logged into Frappe, just one click)
6. Redirected back to chatbot with success message
7. Chatbot now works! Tokens are stored and auto-refreshed

**Users only authorize ONCE** - tokens are stored securely in database.

#### How It Works

```
User Opens Chatbot
    ↓
Check if user has token
    ↓ (No token)
Show "Authorize" dialog
    ↓
User clicks "Authorize Now"
    ↓
Redirect to: /api/method/frappe.integrations.oauth2.authorize
    + PKCE code_challenge
    + client_id
    + redirect_uri
    + state (CSRF protection)
    ↓
User clicks "Allow"
    ↓
Redirect back with: authorization_code
    ↓
Backend exchanges code for tokens:
    - access_token (1 hour)
    - refresh_token (longer)
    ↓
Store tokens in AI Chatbot User Token
    ↓
All MCP requests use: Authorization: Bearer <access_token>
    ↓
Token expired? Auto-refresh using refresh_token
```

**Security Features**:
- ✅ PKCE (Proof Key for Code Exchange) prevents authorization code interception
- ✅ State parameter prevents CSRF attacks
- ✅ Tokens stored encrypted (Password fieldtype)
- ✅ Per-user tokens - chatbot acts with user's permissions
- ✅ Automatic token expiry and refresh

#### Troubleshooting

**"Authorization Required" dialog keeps appearing**
- OAuth Client doesn't exist or was deleted - recreate it
- Client ID in AI Chatbot Settings is incorrect
- Check Error Log for token exchange failures

**"Failed to get authorization URL"**
- Client ID not configured in AI Chatbot Settings
- FAC app not installed: `bench --site your-site list-apps`

**"Token Exchange Failed" after clicking Allow**
- Redirect URI mismatch - must exactly match OAuth Client settings
- Client Secret incorrect (if using confidential client)
- Check Error Log for detailed error

**401 Unauthorized on MCP requests**
- Token expired and refresh failed
- User needs to re-authorize: revoke token and authorize again
- Check token in `AI Chatbot User Token` DocType exists and not expired

**Manually Revoke Tokens** (if user wants to disconnect):
```bash
bench --site your-site console

frappe.delete_doc("AI Chatbot User Token", {"user": "user@example.com"})
frappe.db.commit()
```

Or users can disconnect via a "Revoke Access" button (you can add this to chatbot UI by calling `frappe_ai_chatbot.api.oauth.revoke_user_tokens`)

---

## Usage Examples

### Search Data
```
You: List all customers created this month
AI: 🔧 Using tool: list_documents
    Result: Found 15 customers...
```

### Run Reports
```
You: Show top 10 selling items
AI: 🔧 Using tool: execute_report
    Result: [displays item sales data]
```

### Analyze Trends
```
You: Analyze sales trend for Q3
AI: 🔧 Using tools: aggregate_data, trend_analysis
    Result: Sales increased 12% compared to Q2...
```

---

## Configuration Options

### Rate Limiting
Control usage to prevent excessive API costs:
```
Messages per hour: 100 (default)
Tokens per day: 1,000,000 (default)
```

### Model Parameters
Fine-tune AI behavior:
```
Max tokens: 4096 (response length)
Temperature: 0.7 (randomness: 0-1)
Context window: 10 messages (conversation memory)
```

### Scheduled Tasks
Automatic background maintenance (requires bench scheduler running):
```
Hourly: Cleanup old sessions (older than session_timeout days)
Daily: Generate usage reports (messages, tokens, costs)
```

---

## Troubleshooting

### Chat bubble/interface not appearing?

**Step 1: Enable AI Chatbot globally**
1. Go to: Search → **"AI Chatbot Settings"**
2. Check **"Enable Chatbot"** checkbox
3. Configure your LLM provider (see Configuration section above)
4. Save

**Step 2: Enable for your user**
1. Go to: **User List** → Open your user
2. Scroll to **"Enable AI Chatbot"** checkbox
3. Check it (should be enabled by default)
4. Save

**Step 3: Build and restart**
```bash
# Build assets to include the widget/launcher
bench build --app frappe_ai_chatbot

# Clear cache
bench --site your-site clear-cache

# Restart server
bench restart

# Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
```

**Step 4: Verify in browser**
- **Widget**: Look for 🤖 bubble in bottom-right corner
- **Full-page**: Look for "AI Assistant" button in navbar OR press Ctrl+Shift+A

### Want to enable the full-page interface?
```bash
# 1. Edit frappe_ai_chatbot/hooks.py
# 2. Uncomment the ai_assistant_launcher.js line in app_include_js
# 3. Build and restart:
bench build --app frappe_ai_chatbot
bench --site your-site clear-cache
bench restart
```

### Chat not working?
1. Check AI Chatbot Settings are configured
2. Verify MCP endpoint is reachable
3. Check browser console for errors
4. Verify user has permissions

### Rate limit errors?
- Increase limits in AI Chatbot Settings
- Or wait for reset (1 hour for messages)

---

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete technical documentation with implementation details

### Requirements
- Frappe Framework v15+
- Frappe_Assistant_Core v2.1.1+ (for MCP tools)
- Python 3.11+
- anthropic SDK (for Claude)
- openai SDK (for OpenAI)
- google-generativeai SDK (for Gemini)
- Ollama (for Local LLMs)

---

*Depends on [Frappe_Assistant_Core](https://github.com/buildswithpaul/Frappe_Assistant_Core) for MCP tools*
