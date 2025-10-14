/**
 * AI Assistant Page
 * 
 * Full-page chat interface for interacting with AI assistants.
 * Supports Claude, OpenAI, and Local LLMs with MCP tool integration.
 * 
 * Architecture: Single-file module following community best practices
 * Structure:
 *   1. Page Initialization (lines 1-20)
 *   2. Main Class Definition (lines 21-50)
 *   3. Styles (lines 51-450)
 *   4. UI Setup & Rendering (lines 451-700)
 *   5. Message Handling (lines 701-900)
 *   6. Streaming & Tool Calls (lines 901-1050)
 *   7. Session Management (lines 1051-1121)
 */

/*******************************
 * PAGE INITIALIZATION
 *******************************/

frappe.pages['ai-assistant'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'AI Assistant',
		single_column: false
	});

	// Initialize the AI Assistant
	const assistant = new AIAssistant(page);
	assistant.init();
};

/*******************************
 * MAIN CLASS DEFINITION
 *******************************/

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

	async init() {
		// Add custom CSS
		this.add_styles();
		
		// Setup UI
		this.setup_toolbar();
		this.render_layout();
		
		// Check for OAuth callback success
		const urlParams = new URLSearchParams(window.location.search);
		if (urlParams.get('oauth_success') === '1') {
			frappe.show_alert({
				message: __('OAuth authorization successful! You can now use the AI Assistant.'),
				indicator: 'green'
			}, 5);
			// Clean URL
			window.history.replaceState({}, document.title, window.location.pathname);
		}
		
		// Check if user has valid OAuth token
		await this.check_oauth_status();
		
		// Load sessions
		await this.load_sessions();
		
		// Load or create default session
		await this.get_or_create_session();
	}
	
	async check_oauth_status() {
		/**
		 * Check if current user has valid OAuth tokens.
		 * If not, show authorization prompt.
		 */
		try {
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.oauth.get_user_token_status',
				freeze: false
			});
			
			const status = response.message;
			
			if (!status.has_token || !status.is_valid) {
				// User needs to authorize
				this.show_oauth_prompt();
			}
		} catch (error) {
			console.error('Failed to check OAuth status:', error);
		}
	}
	
	show_oauth_prompt() {
		/**
		 * Show dialog prompting user to authorize the chatbot.
		 */
		const dialog = new frappe.ui.Dialog({
			title: __('Authorization Required'),
			indicator: 'blue',
			fields: [
				{
					fieldtype: 'HTML',
					options: `
						<div style="padding: 20px; text-align: center;">
							<p style="font-size: 16px; margin-bottom: 20px;">
								${__('The AI Assistant needs your permission to access Frappe Assistant Core.')}
							</p>
							<p style="color: var(--text-muted); margin-bottom: 20px;">
								${__('You will be redirected to authorize this application. This is a one-time setup.')}
							</p>
							<button class="btn btn-primary btn-lg" id="oauth-authorize-btn">
								<i class="fa fa-shield-alt"></i> ${__('Authorize Now')}
							</button>
						</div>
					`
				}
			],
			primary_action_label: null // No primary action, handled by button click
		});
		
		dialog.show();
		
		// Handle authorize button click
		dialog.$wrapper.find('#oauth-authorize-btn').on('click', async () => {
			try {
				// Get authorization URL from backend
				const response = await frappe.call({
					method: 'frappe_ai_chatbot.api.oauth.get_authorization_url',
					freeze: true,
					freeze_message: __('Preparing authorization...')
				});
				
				const { authorization_url } = response.message;
				
				// Redirect to authorization URL
				window.location.href = authorization_url;
			} catch (error) {
				frappe.msgprint({
					title: __('Error'),
					indicator: 'red',
					message: __('Failed to get authorization URL: {0}', [error.message || error])
				});
			}
		});
	}

	/*******************************
	 * STYLES
	 * 
	 * All CSS embedded here for simplicity and following community standards.
	 * Organized by component:
	 *   - Container & Layout
	 *   - Sidebar
	 *   - Chat Area
	 *   - Messages
	 *   - Input Area
	 *   - Animations & Effects
	 *   - Responsive Design
	 *******************************/

	add_styles() {
		if (!$('#ai-assistant-styles').length) {
			$('head').append(`
				<style id="ai-assistant-styles">
					/* === CONTAINER & LAYOUT === */
					.ai-assistant-container {
						display: flex;
						height: calc(100vh - 120px);
						background: var(--bg-color);
						gap: 0;
						overflow: hidden;
					}
					
					/* === SIDEBAR === */
					.ai-sidebar {
						width: 280px;
						background: var(--card-bg);
						border-right: 1px solid var(--border-color);
						display: flex;
						flex-direction: column;
						overflow: hidden;
					}
					
					.ai-sidebar-header {
						padding: 16px;
						border-bottom: 1px solid var(--border-color);
					}
					
					.ai-new-chat-btn {
						width: 100%;
						display: flex;
						align-items: center;
						justify-content: center;
						gap: 8px;
						padding: 10px 16px;
						background: var(--primary);
						color: white;
						border: none;
						border-radius: var(--border-radius-md);
						cursor: pointer;
						font-weight: 500;
						transition: all 0.2s;
					}
					
					.ai-new-chat-btn:hover {
						background: var(--primary-dark);
						transform: translateY(-1px);
					}
					
					.ai-sessions-list {
						flex: 1;
						overflow-y: auto;
						padding: 8px;
					}
					
					.ai-session-item {
						padding: 12px;
						margin-bottom: 4px;
						border-radius: var(--border-radius);
						cursor: pointer;
						transition: all 0.2s;
						border: 1px solid transparent;
					}
					
					.ai-session-item:hover {
						background: var(--subtle-bg);
						border-color: var(--border-color);
					}
					
					.ai-session-item.active {
						background: var(--primary-bg);
						border-color: var(--primary);
					}
					
					.ai-session-title {
						font-weight: 500;
						margin-bottom: 4px;
						color: var(--text-color);
						display: flex;
						justify-content: space-between;
						align-items: center;
					}
					
					.ai-session-meta {
						font-size: 12px;
						color: var(--text-muted);
					}
					
					.ai-session-actions {
						opacity: 0;
						transition: opacity 0.2s;
					}
					
					.ai-session-item:hover .ai-session-actions {
						opacity: 1;
					}
					
					/* === CHAT AREA === */
					.ai-chat-area {
						flex: 1;
						display: flex;
						flex-direction: column;
						background: var(--bg-color);
					}
					
					.ai-chat-header {
						padding: 16px 24px;
						border-bottom: 1px solid var(--border-color);
						background: var(--card-bg);
						display: flex;
						justify-content: space-between;
						align-items: center;
					}
					
					.ai-chat-header-title {
						font-size: 16px;
						font-weight: 600;
						color: var(--text-color);
					}
					
					.ai-chat-header-actions {
						display: flex;
						gap: 8px;
					}
					
					.ai-messages-container {
						flex: 1;
						overflow-y: auto;
						padding: 24px;
						scroll-behavior: smooth;
					}
					
					.ai-message {
						margin-bottom: 24px;
						display: flex;
						gap: 12px;
						animation: messageSlideIn 0.3s ease-out;
					}
					
					@keyframes messageSlideIn {
						from {
							opacity: 0;
							transform: translateY(10px);
						}
						to {
							opacity: 1;
							transform: translateY(0);
						}
					}
					
					.ai-message-avatar {
						width: 36px;
						height: 36px;
						border-radius: 50%;
						display: flex;
						align-items: center;
						justify-content: center;
						font-weight: 600;
						flex-shrink: 0;
					}
					
					.ai-message.user .ai-message-avatar {
						background: var(--primary);
						color: white;
					}
					
					.ai-message.assistant .ai-message-avatar {
						background: var(--purple-500);
						color: white;
					}
					
					.ai-message-content {
						flex: 1;
						max-width: 800px;
					}
					
					.ai-message-text {
						background: var(--card-bg);
						padding: 12px 16px;
						border-radius: var(--border-radius-md);
						line-height: 1.6;
						color: var(--text-color);
						word-wrap: break-word;
					}
					
					.ai-message.user .ai-message-text {
						background: var(--primary-bg);
					}
					
					.ai-message-time {
						font-size: 11px;
						color: var(--text-muted);
						margin-top: 4px;
						padding-left: 16px;
					}
					
					.ai-tool-call {
						margin-top: 8px;
						padding: 12px;
						background: var(--subtle-bg);
						border-left: 3px solid var(--orange-500);
						border-radius: var(--border-radius);
					}
					
					.ai-tool-call-header {
						display: flex;
						align-items: center;
						gap: 8px;
						font-weight: 500;
						margin-bottom: 8px;
						color: var(--text-color);
					}
					
					.ai-tool-call-status {
						width: 8px;
						height: 8px;
						border-radius: 50%;
						background: var(--orange-500);
					}
					
					.ai-tool-call-status.running {
						background: var(--blue-500);
						animation: pulse 1.5s ease-in-out infinite;
					}
					
					.ai-tool-call-status.complete {
						background: var(--green-500);
					}
					
					.ai-tool-call-status.error {
						background: var(--red-500);
					}
					
					@keyframes pulse {
						0%, 100% { opacity: 1; }
						50% { opacity: 0.5; }
					}
					
					.ai-tool-call-details {
						font-size: 12px;
						color: var(--text-muted);
						font-family: monospace;
						white-space: pre-wrap;
						max-height: 200px;
						overflow-y: auto;
					}
					
					/* === INPUT AREA === */
					.ai-input-area {
						padding: 16px 24px;
						border-top: 1px solid var(--border-color);
						background: var(--card-bg);
					}
					
					.ai-input-wrapper {
						display: flex;
						gap: 12px;
						align-items: flex-end;
					}
					
					.ai-input-field {
						flex: 1;
						min-height: 44px;
						max-height: 200px;
						padding: 12px 16px;
						border: 1px solid var(--border-color);
						border-radius: var(--border-radius-md);
						resize: vertical;
						font-family: inherit;
						font-size: 14px;
						line-height: 1.5;
						background: var(--control-bg);
						color: var(--text-color);
						transition: border-color 0.2s;
					}
					
					.ai-input-field:focus {
						outline: none;
						border-color: var(--primary);
						box-shadow: 0 0 0 2px var(--primary-bg);
					}
					
					.ai-input-field:disabled {
						opacity: 0.6;
						cursor: not-allowed;
					}
					
					.ai-send-btn {
						padding: 12px 24px;
						background: var(--primary);
						color: white;
						border: none;
						border-radius: var(--border-radius-md);
						cursor: pointer;
						font-weight: 500;
						transition: all 0.2s;
						display: flex;
						align-items: center;
						gap: 6px;
					}
					
					.ai-send-btn:hover:not(:disabled) {
						background: var(--primary-dark);
						transform: translateY(-1px);
					}
					
					.ai-send-btn:disabled {
						opacity: 0.6;
						cursor: not-allowed;
					}
					
					.ai-typing-indicator {
						display: flex;
						gap: 4px;
						padding: 12px 16px;
					}
					
					.ai-typing-dot {
						width: 8px;
						height: 8px;
						background: var(--text-muted);
						border-radius: 50%;
						animation: typingDot 1.4s ease-in-out infinite;
					}
					
					.ai-typing-dot:nth-child(2) {
						animation-delay: 0.2s;
					}
					
					.ai-typing-dot:nth-child(3) {
						animation-delay: 0.4s;
					}
					
					@keyframes typingDot {
						0%, 60%, 100% { transform: translateY(0); }
						30% { transform: translateY(-10px); }
					}
					
					/* === ANIMATIONS & EFFECTS === */
					.ai-empty-state {
						display: flex;
						flex-direction: column;
						align-items: center;
						justify-content: center;
						height: 100%;
						color: var(--text-muted);
						text-align: center;
						padding: 40px;
					}
					
					.ai-empty-state-icon {
						font-size: 64px;
						margin-bottom: 16px;
						opacity: 0.5;
					}
					
					.ai-empty-state-title {
						font-size: 18px;
						font-weight: 600;
						margin-bottom: 8px;
						color: var(--text-color);
					}
					
					.ai-empty-state-text {
						font-size: 14px;
					}
					
					/* Loading Spinner */
					.ai-loading {
						display: inline-block;
						width: 16px;
						height: 16px;
						border: 2px solid currentColor;
						border-right-color: transparent;
						border-radius: 50%;
						animation: spin 0.6s linear infinite;
					}
					
					@keyframes spin {
						to { transform: rotate(360deg); }
					}
					
					/* Scrollbar */
					.ai-sessions-list::-webkit-scrollbar,
					.ai-messages-container::-webkit-scrollbar,
					.ai-tool-call-details::-webkit-scrollbar {
						width: 6px;
					}
					
					.ai-sessions-list::-webkit-scrollbar-track,
					.ai-messages-container::-webkit-scrollbar-track,
					.ai-tool-call-details::-webkit-scrollbar-track {
						background: transparent;
					}
					
					.ai-sessions-list::-webkit-scrollbar-thumb,
					.ai-messages-container::-webkit-scrollbar-thumb,
					.ai-tool-call-details::-webkit-scrollbar-thumb {
						background: var(--border-color);
						border-radius: 3px;
					}
					
					.ai-sessions-list::-webkit-scrollbar-thumb:hover,
					.ai-messages-container::-webkit-scrollbar-thumb:hover,
					.ai-tool-call-details::-webkit-scrollbar-thumb:hover {
						background: var(--text-muted);
					}
					
					/* === RESPONSIVE DESIGN === */
					@media (max-width: 768px) {
						.ai-sidebar {
							position: absolute;
							left: -280px;
							height: 100%;
							z-index: 100;
							transition: left 0.3s;
						}
						
						.ai-sidebar.mobile-open {
							left: 0;
							box-shadow: 2px 0 8px rgba(0,0,0,0.1);
						}
						
						.ai-assistant-container {
							height: calc(100vh - 100px);
						}
					}
					
					/* Code blocks */
					.ai-message-text pre {
						background: var(--subtle-bg);
						padding: 12px;
						border-radius: var(--border-radius);
						overflow-x: auto;
						margin: 8px 0;
					}
					
					.ai-message-text code {
						background: var(--subtle-bg);
						padding: 2px 6px;
						border-radius: 3px;
						font-family: monospace;
						font-size: 13px;
					}
					
					.ai-message-text pre code {
						background: none;
						padding: 0;
					}
				</style>
			`);
		}
	}

	/*******************************
	 * UI SETUP & RENDERING
	 * 
	 * Methods for building the interface:
	 *   - setup_toolbar(): Add toolbar buttons (Settings, Clear History)
	 *   - render_layout(): Create main layout structure (sidebar + chat area)
	 *   - bind_events(): Attach event handlers for user interactions
	 * 
	 * Layout Structure:
	 *   - Sidebar: Session list + New Chat button
	 *   - Chat Area: Header + Messages + Input
	 *******************************/

	setup_toolbar() {
		// Add settings button (opens AI Chatbot Settings dialog)
		this.page.add_button('Settings', () => {
			this.show_settings_dialog();
		}, 'octicon octicon-gear');
		
		// Add clear history button (deletes all messages in current session)
		this.page.add_button('Clear History', () => {
			this.clear_session_history();
		}, 'octicon octicon-trash');
	}

	render_layout() {
		const container = $(`
			<div class="ai-assistant-container">
				<div class="ai-sidebar">
					<div class="ai-sidebar-header">
						<button class="ai-new-chat-btn">
							<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
								<path d="M8 0a1 1 0 0 1 1 1v6h6a1 1 0 1 1 0 2H9v6a1 1 0 1 1-2 0V9H1a1 1 0 0 1 0-2h6V1a1 1 0 0 1 1-1z"/>
							</svg>
							New Chat
						</button>
					</div>
					<div class="ai-sessions-list"></div>
				</div>
				<div class="ai-chat-area">
					<div class="ai-chat-header">
						<div class="ai-chat-header-title">AI Assistant</div>
						<div class="ai-chat-header-actions">
							<button class="btn btn-sm btn-default ai-toggle-sidebar" style="display: none;">
								<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
									<path d="M0 3h16v2H0zm0 4h16v2H0zm0 4h16v2H0z"/>
								</svg>
							</button>
						</div>
					</div>
					<div class="ai-messages-container"></div>
					<div class="ai-input-area">
						<div class="ai-input-wrapper">
							<textarea 
								class="ai-input-field" 
								placeholder="Type your message here... (Shift+Enter for new line)"
								rows="1"
							></textarea>
							<button class="ai-send-btn">
								<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
									<path d="M15.854.146a.5.5 0 0 1 .11.54l-5.819 14.547a.75.75 0 0 1-1.329.124l-3.178-4.995L.643 7.184a.75.75 0 0 1 .124-1.33L15.314.037a.5.5 0 0 1 .54.11ZM6.636 10.07l2.761 4.338L14.13 2.576 6.636 10.07Zm6.787-8.201L1.591 6.602l4.339 2.76 7.494-7.493Z"/>
								</svg>
								Send
							</button>
						</div>
					</div>
				</div>
			</div>
		`);
		
		this.wrapper.find('.page-content').append(container);
		
		// Bind events
		this.bind_events();
	}

	bind_events() {
		// New chat button - Creates fresh session
		this.wrapper.find('.ai-new-chat-btn').on('click', () => {
			this.create_new_session();
		});
		
		// Send button - Submits message
		this.wrapper.find('.ai-send-btn').on('click', () => {
			this.send_message();
		});
		
		// Input field keyboard handling
		// Enter: Send message
		// Shift+Enter: New line
		this.wrapper.find('.ai-input-field').on('keydown', (e) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this.send_message();
			}
		});
		
		// Auto-resize textarea as user types (grows with content)
		this.wrapper.find('.ai-input-field').on('input', function() {
			this.style.height = 'auto';  // Reset height
			this.style.height = (this.scrollHeight) + 'px';  // Set to content height
		});
		
		// Mobile sidebar toggle (hamburger menu)
		this.wrapper.find('.ai-toggle-sidebar').on('click', () => {
			this.wrapper.find('.ai-sidebar').toggleClass('mobile-open');
		});
		
		// Show mobile toggle button on small screens
		if (window.innerWidth <= 768) {
			this.wrapper.find('.ai-toggle-sidebar').show();
		}
	}

	/*******************************
	 * SESSION MANAGEMENT
	 * 
	 * Methods for managing chat sessions (conversations):
	 *   - load_sessions(): Fetch all user sessions from database
	 *   - render_sessions(): Display sessions in sidebar list
	 *   - create_new_session(): Start new chat session
	 *   - load_session(): Switch to existing session (loads messages)
	 *   - delete_session(): Remove a session and its messages
	 *   - get_or_create_session(): Get current or create default session
	 * 
	 * Session Lifecycle:
	 *   1. User clicks "New Chat" → create_new_session()
	 *   2. Session persisted to AI Chat Session DocType
	 *   3. Messages linked to session via session_id
	 *   4. Sessions displayed in sidebar, sorted by modified date
	 *******************************/

	async load_sessions() {
		try {
			const response = await frappe.call({
				method: 'frappe.client.get_list',
				args: {
					doctype: 'AI Chat Session',
					filters: {
						user: frappe.session.user,
						status: ['!=', 'Archived']
					},
					fields: ['name', 'title', 'modified', 'status', 'total_messages'],
					order_by: 'modified desc',
					limit_page_length: 50
				}
			});
			
			this.sessions = response.message || [];
			this.render_sessions();
		} catch (error) {
			console.error('Failed to load sessions:', error);
			frappe.show_alert({
				message: 'Failed to load chat sessions',
				indicator: 'red'
			});
		}
	}

	render_sessions() {
		const container = this.wrapper.find('.ai-sessions-list');
		container.empty();
		
		if (this.sessions.length === 0) {
			container.append(`
				<div style="padding: 20px; text-align: center; color: var(--text-muted);">
					<p>No chat sessions yet.</p>
					<p style="font-size: 12px;">Click "New Chat" to start.</p>
				</div>
			`);
			return;
		}
		
		this.sessions.forEach(session => {
			const item = $(`
				<div class="ai-session-item ${session.name === this.current_session ? 'active' : ''}" data-session="${session.name}">
					<div class="ai-session-title">
						<span>${session.title || 'Untitled Chat'}</span>
						<div class="ai-session-actions">
							<button class="btn btn-xs btn-default ai-delete-session" title="Delete">
								<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
									<path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
									<path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
								</svg>
							</button>
						</div>
					</div>
					<div class="ai-session-meta">
						${session.total_messages || 0} messages • ${frappe.datetime.comment_when(session.modified)}
					</div>
				</div>
			`);
			
			// Click to load session
			item.on('click', (e) => {
				if (!$(e.target).closest('.ai-session-actions').length) {
					this.load_session(session.name);
				}
			});
			
			// Delete session
			item.find('.ai-delete-session').on('click', (e) => {
				e.stopPropagation();
				this.delete_session(session.name);
			});
			
			container.append(item);
		});
	}

	async get_or_create_session() {
		try {
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.chat.get_or_create_session'
			});
			
			if (!response || !response.message) {
				console.error('Invalid session response:', response);
				frappe.msgprint(__('Failed to initialize AI chat session - no session returned'));
				return;
			}

			this.current_session = response.message.name;
			console.log('Session created:', this.current_session);
			
			await this.load_messages();
			await this.load_sessions(); // Refresh sidebar
		} catch (error) {
			console.error('Failed to create session:', error);
			
			// Show specific error message to user
			if (error.exc) {
				// Server-side error with message
				const errorMsg = error._server_messages 
					? JSON.parse(error._server_messages)[0] 
					: error.message || 'Unknown error';
				frappe.msgprint(__(errorMsg));
			} else {
				frappe.msgprint(__('Failed to initialize AI chat session. Please contact your administrator.'));
			}
		}
	}

	async create_new_session() {
		if (this.is_streaming) {
			frappe.show_alert({
				message: 'Please wait for the current message to complete',
				indicator: 'orange'
			});
			return;
		}
		
		console.log('[NEW CHAT] Starting new session creation...');
		console.log('[NEW CHAT] Old session:', this.current_session);
		
		try {
			// Call new API endpoint that closes old session and creates fresh one
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.chat.create_new_session'
			});
			
			if (!response || !response.message) {
				console.error('[NEW CHAT] Invalid response:', response);
				frappe.show_alert({
					message: 'Failed to create new chat',
					indicator: 'red'
				});
				return;
			}
			
			// Clear all local state
			this.current_session = response.message.name;
			this.messages = [];
			this.is_streaming = false;
			this.current_stream_message = null;
			
			console.log('[NEW CHAT] New session created:', this.current_session);
			
			// Clear UI
			const input = this.wrapper.find('.ai-input-field');
			input.val('').css('height', 'auto');
			this.wrapper.find('.ai-messages-container').empty();
			
			// Show empty state
			this.render_messages();
			
			// Refresh sidebar to show new session as active
			await this.load_sessions();
			
			console.log('[NEW CHAT] Complete!');
			
			frappe.show_alert({
				message: 'New chat created',
				indicator: 'green'
			});
		} catch (error) {
			console.error('[NEW CHAT] Error:', error);
			frappe.show_alert({
				message: 'Failed to create new chat: ' + (error.message || 'Unknown error'),
				indicator: 'red'
			});
		}
	}

	async load_session(session_id) {
		if (this.is_streaming) {
			frappe.show_alert({
				message: 'Please wait for the current message to complete',
				indicator: 'orange'
			});
			return;
		}
		
		this.current_session = session_id;
		await this.load_messages();
		
		// Update active state in sidebar
		this.wrapper.find('.ai-session-item').removeClass('active');
		this.wrapper.find(`.ai-session-item[data-session="${session_id}"]`).addClass('active');
		
		// Close mobile sidebar
		if (window.innerWidth <= 768) {
			this.wrapper.find('.ai-sidebar').removeClass('mobile-open');
		}
	}

	/*******************************
	 * MESSAGE HANDLING
	 * 
	 * Methods for displaying and formatting messages:
	 *   - load_messages(): Fetch messages from database for current session
	 *   - render_messages(): Display all messages in chat area
	 *   - create_message_element(): Build HTML for single message (user/assistant)
	 *   - format_message_content(): Apply markdown formatting (code blocks, links, etc.)
	 *   - create_tool_call_element(): Display tool execution cards (expandable details)
	 * 
	 * Message Types:
	 *   - User messages: Right-aligned, blue background
	 *   - Assistant messages: Left-aligned, markdown formatted
	 *   - Tool calls: Special cards showing tool name, args, and results
	 * 
	 * Rendering Flow:
	 *   1. load_messages() fetches from AI Chat Message DocType
	 *   2. render_messages() clears container and builds HTML for each message
	 *   3. Scroll to bottom to show latest messages
	 *******************************/

	async load_messages() {
		if (!this.current_session) return;
		
		try {
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.chat.get_messages',
				args: {
					session_id: this.current_session,
					limit: 100
				}
			});
			
			this.messages = response.message || [];
			this.render_messages();
		} catch (error) {
			console.error('Failed to load messages:', error);
			frappe.show_alert({
				message: 'Failed to load messages',
				indicator: 'red'
			});
		}
	}

	render_messages() {
		const container = this.wrapper.find('.ai-messages-container');
		container.empty();
		
		if (this.messages.length === 0) {
			container.append(`
				<div class="ai-empty-state">
					<div class="ai-empty-state-icon">💬</div>
					<div class="ai-empty-state-title">Start a conversation</div>
					<div class="ai-empty-state-text">
						Ask me anything! I can help you with ERPNext data,<br>
						run reports, analyze documents, and much more.
					</div>
				</div>
			`);
			return;
		}
		
		this.messages.forEach(msg => {
			container.append(this.create_message_element(msg));
		});
		
		// Scroll to bottom
		this.scroll_to_bottom();
	}

	create_message_element(msg) {
		// Skip tool messages - they're not meant to be displayed directly
		// Tool results are shown inline with the assistant message that called them
		if (msg.role === 'tool') {
			return $('<!-- tool message hidden -->');
		}
		
		const message_div = $(`
			<div class="ai-message ${msg.role}">
				<div class="ai-message-avatar">
					${msg.role === 'user' ? frappe.user_info(frappe.session.user).abbr : 'AI'}
				</div>
				<div class="ai-message-content">
					<div class="ai-message-text">${this.format_message_content(msg.content)}</div>
					<div class="ai-message-time">${frappe.datetime.comment_when(msg.timestamp)}</div>
				</div>
			</div>
		`);
		
		// Don't show tool execution cards for old messages loaded from database
		// The tool results are already incorporated into the assistant's response text
		// Showing raw tool outputs clutters the UI and provides no value to the user
		
		return message_div;
	}

	create_tool_call_element(tool) {
		const status = tool.status || 'complete';
		return $(`
			<div class="ai-tool-call">
				<div class="ai-tool-call-header">
					<div class="ai-tool-call-status ${status}"></div>
					<span>🔧 ${tool.name || 'Tool Execution'}</span>
				</div>
				<div class="ai-tool-call-details">${this.format_tool_details(tool)}</div>
			</div>
		`);
	}

	format_tool_details(tool) {
		let details = '';
		if (tool.parameters) {
			details += `Parameters: ${JSON.stringify(tool.parameters, null, 2)}\n`;
		}
		if (tool.result) {
			details += `\nResult: ${typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2)}`;
		}
		return details || 'Executing...';
	}

	format_message_content(content) {
		// Simple markdown-like formatting
		content = frappe.utils.escape_html(content);
		
		// Code blocks
		content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
		
		// Inline code
		content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
		
		// Bold
		content = content.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
		
		// Italic
		content = content.replace(/\*([^*]+)\*/g, '<em>$1</em>');
		
		// Line breaks
		content = content.replace(/\n/g, '<br>');
		
		return content;
	}

	/*******************************
	 * STREAMING & REAL-TIME COMMUNICATION
	 * 
	 * Methods for handling real-time AI responses:
	 *   - send_message(): Send user message and start streaming
	 *   - Handle SSE events: content, tool_call, tool_result, done, error
	 *   - set_input_state(): Enable/disable input during streaming
	 *   - scroll_to_bottom(): Auto-scroll to latest message
	 *******************************/

	async send_message() {
		const input = this.wrapper.find('.ai-input-field');
		const message = input.val().trim();
		
		if (!message || this.is_streaming) return;

		// Ensure session exists before sending
		if (!this.current_session) {
			await this.get_or_create_session();
			if (!this.current_session) {
				frappe.msgprint(__('Failed to create chat session'));
				return;
			}
		}
		
		// Clear input
		input.val('').css('height', 'auto');
		
		// Disable input
		this.is_streaming = true;  // Block new messages during streaming
		this.set_input_state(false);  // Disable input field
		
		// Add user message to UI immediately (optimistic rendering)
		const user_msg = {
			role: 'user',
			content: message,
			timestamp: frappe.datetime.now_datetime()
		};
		this.messages.push(user_msg);
		
		const container = this.wrapper.find('.ai-messages-container');
		
		// Remove empty state placeholder if present
		container.find('.ai-empty-state').remove();
		
		// Render user message in chat
		container.append(this.create_message_element(user_msg));
		this.scroll_to_bottom();
		
		// Create empty assistant message container (will be filled as stream arrives)
		const assistant_msg_div = $(`
			<div class="ai-message assistant" id="ai-streaming-response">
				<div class="ai-message-avatar">AI</div>
				<div class="ai-message-content">
					<div class="ai-message-text"></div>
					<div class="ai-tool-calls-container"></div>
					<div class="ai-message-time"></div>
				</div>
			</div>
		`);
		container.append(assistant_msg_div);
		
		let streaming_content = '';  // Accumulate content chunks
		let tool_calls = [];  // Track tool executions
		
		// Create Server-Sent Events connection
		// SSE provides real-time streaming from server
		const eventSource = new EventSource(
			`/api/method/frappe_ai_chatbot.api.stream.stream_chat?` +
			`session_id=${encodeURIComponent(this.current_session)}&` +
			`message=${encodeURIComponent(message)}`
		);
		
		// Handle 'content' events (LLM text chunks)
		eventSource.addEventListener('content', (e) => {
			try {
				const data = JSON.parse(e.data);
				streaming_content += data.content || '';  // Append chunk
				// Render accumulated content with markdown formatting
				assistant_msg_div.find('.ai-message-text').html(this.format_message_content(streaming_content));
				this.scroll_to_bottom();  // Keep latest content visible
			} catch (error) {
				console.error('Error parsing content event:', error);
			}
		});
		
		// Handle 'tool_call' events (LLM requests to execute a tool)
		eventSource.addEventListener('tool_call', (e) => {
			try {
				const data = JSON.parse(e.data);
				console.log('[TOOL_CALL] Received:', data);
				
				const tool = {
					id: data.id,  // Tool call ID for matching with results
					name: data.name,  // e.g., "get_document"
					parameters: data.parameters,  // Tool arguments
					status: 'running'  // Execution in progress
				};
				tool_calls.push(tool);
				
				// Add expandable tool execution card to UI
				const tool_container = assistant_msg_div.find('.ai-tool-calls-container');
				tool_container.append(this.create_tool_call_element(tool));
				this.scroll_to_bottom();
			} catch (error) {
				console.error('Error parsing tool_call event:', error);
			}
		});
		
		// Handle 'tool_result' events (tool execution completed)
		eventSource.addEventListener('tool_result', (e) => {
			try {
				const data = JSON.parse(e.data);
				console.log('[TOOL_RESULT] Received:', data);
				
				// Find tool by tool_call_id (more reliable than index)
				const tool_call_id = data.tool_call_id;
				const tool_name = data.tool_name;
				const result = data.result;
				
				// Find the tool in our tracked list
				const tool_index = tool_calls.findIndex(tc => 
					tc.id === tool_call_id || (tc.name === tool_name && !tc.result)
				);
				
				if (tool_index >= 0) {
					console.log('[TOOL_RESULT] Updating tool at index:', tool_index);
					
					// Update tool with result
					tool_calls[tool_index].result = result;
					tool_calls[tool_index].status = 'complete';
					
					// Update tool card UI (change status indicator, show result)
					const tool_cards = assistant_msg_div.find('.ai-tool-call');
					if (tool_cards[tool_index]) {
						console.log('[TOOL_RESULT] Updating UI for:', tool_name);
						$(tool_cards[tool_index]).find('.ai-tool-call-status')
							.removeClass('running')
							.addClass('complete');
						$(tool_cards[tool_index]).find('.ai-tool-call-details')
							.text(this.format_tool_details(tool_calls[tool_index]));
					}
					this.scroll_to_bottom();
				} else {
					console.warn('[TOOL_RESULT] Could not find tool to update:', tool_name, tool_call_id);
				}
			} catch (error) {
				console.error('Error parsing tool_result event:', error);
			}
		});
		
		// Handle 'error' events (streaming errors)
		eventSource.addEventListener('error', (e) => {
			try {
				const data = JSON.parse(e.data);
				console.error('Streaming error:', data);
				
				// Check if this is an authorization error
				if (data.action === 'authorize') {
					// Show authorization dialog
					this.show_oauth_prompt();
					frappe.show_alert({
						message: data.message || 'Authorization required',
						indicator: 'orange'
					});
				} else if (data.action === 'reload') {
					// Suggest reloading
					frappe.show_alert({
						message: data.message || 'Authentication error. Please reload and try again.',
						indicator: 'red'
					});
				} else {
					// Generic error
					frappe.show_alert({
						message: 'Error: ' + (data.message || data.error || 'An unexpected error occurred'),
						indicator: 'red'
					});
				}
			} catch (error) {
				console.error('Error parsing error event:', error);
			}
			// Clean up SSE connection and re-enable input
			eventSource.close();
			this.is_streaming = false;
			this.set_input_state(true);
		});
		
		// Handle 'done' event (stream complete)
		eventSource.addEventListener('done', (e) => {
			try {
				const data = JSON.parse(e.data);
				
				// Update final message with server-confirmed content
				if (data.message) {
					streaming_content = data.message.content || streaming_content;
					assistant_msg_div.find('.ai-message-text').html(this.format_message_content(streaming_content));
					
					// Update timestamp to server time
					const timestamp = data.message.timestamp || frappe.datetime.now_datetime();
					assistant_msg_div.find('.ai-message-time').text(frappe.datetime.comment_when(timestamp));
					
					// Store complete message in local state
					this.messages.push({
						role: 'assistant',
						content: streaming_content,
						timestamp: timestamp,
						tool_calls: tool_calls
					});
				}
				
				// Remove ALL tool execution cards once streaming is complete
				// The AI has already incorporated the tool results into its response,
				// so showing the raw tool outputs is redundant and clutters the UI
				const tool_container = assistant_msg_div.find('.ai-tool-calls-container');
				tool_container.remove();
				
				console.log('[DONE] Removed tool execution cards from UI');
				
				// Remove streaming ID (convert to normal message)
				assistant_msg_div.attr('id', '');
				
				this.scroll_to_bottom();
			} catch (error) {
				console.error('Error parsing done event:', error);
			}
			
			// Clean up SSE connection and re-enable input
			eventSource.close();
			this.is_streaming = false;
			this.set_input_state(true);
		});
		
		// Handle SSE connection errors (network failures, server errors)
		eventSource.onerror = (error) => {
			console.error('EventSource error:', error);
			eventSource.close();
			
			// Remove streaming message if no content received (connection failed before any data)
			if (!streaming_content) {
				assistant_msg_div.remove();
				frappe.show_alert({
					message: 'Connection lost. Please try again.',
					indicator: 'red'
				});
			}
			
			// Re-enable input
			this.is_streaming = false;
			this.set_input_state(true);
		};
	}

	set_input_state(enabled) {
		// Enable/disable input field and send button
		const input = this.wrapper.find('.ai-input-field');
		const button = this.wrapper.find('.ai-send-btn');
		
		input.prop('disabled', !enabled);
		button.prop('disabled', !enabled);
		
		// Focus input when enabled (UX improvement)
		if (enabled) {
			input.focus();
		}
	}

	scroll_to_bottom() {
		// Debounce scroll to prevent animation queue buildup during streaming
		if (this._scroll_timeout) {
			clearTimeout(this._scroll_timeout);
		}
		
		this._scroll_timeout = setTimeout(() => {
			const container = this.wrapper.find('.ai-messages-container');
			if (container.length) {
				// Use instant scroll instead of animate to prevent stutter
				container[0].scrollTop = container[0].scrollHeight;
			}
		}, 50); // 50ms debounce - smooth but responsive
	}

	/*******************************
	 * UTILITY & HELPER METHODS
	 * 
	 * Additional functionality:
	 *   - delete_session(): Remove session with confirmation dialog
	 *   - clear_session_history(): Clear all messages in current session
	 *   - show_settings_dialog(): Display AI Chatbot Settings dialog
	 *   - format_message_content(): Convert markdown to HTML
	 * 
	 * These methods provide UI utilities and supporting functionality
	 * for the main chat interface.
	 *******************************/

	async delete_session(session_id) {
		const confirm_delete = await frappe.confirm(
			'Are you sure you want to delete this chat session?',
			() => {
				frappe.call({
					method: 'frappe.client.delete',
					args: {
						doctype: 'AI Chat Session',
						name: session_id
					},
					callback: () => {
						frappe.show_alert({
							message: 'Chat session deleted',
							indicator: 'green'
						});
						
						// If deleted current session, create new one
						if (session_id === this.current_session) {
							this.create_new_session();
						} else {
							this.load_sessions();
						}
					}
				});
			}
		);
	}

	async clear_session_history() {
		if (!this.current_session) return;
		
		const confirm_clear = await frappe.confirm(
			'Are you sure you want to clear the message history for this session?',
			() => {
				frappe.call({
					method: 'frappe_ai_chatbot.api.chat.clear_history',
					args: {
						session_id: this.current_session
					},
					callback: () => {
						frappe.show_alert({
							message: 'Chat history cleared',
							indicator: 'green'
						});
						this.load_messages();
					}
				});
			}
		);
	}

	show_settings_dialog() {
		const d = new frappe.ui.Dialog({
			title: 'AI Assistant Settings',
			fields: [
				{
					fieldname: 'info',
					fieldtype: 'HTML',
					options: '<p style="color: var(--text-muted);">Settings are managed by your system administrator. Contact them to change LLM provider, model, or rate limits.</p>'
				},
				{
					fieldname: 'current_session',
					fieldtype: 'Data',
					label: 'Current Session ID',
					read_only: 1,
					default: this.current_session || 'No active session'
				},
				{
					fieldname: 'total_messages',
					fieldtype: 'Int',
					label: 'Messages in Session',
					read_only: 1,
					default: this.messages.length
				}
			],
			primary_action_label: 'Close',
			primary_action: function() {
				d.hide();
			}
		});
		
		d.show();
	}
}
