/**
 * AI Chat Widget - Floating chat bubble with slide-in panel
 * 
 * Features:
 * - Floating chat bubble (bottom-right corner)
 * - Slide-in chat panel from right side
 * - Reuses AI Assistant backend logic
 * - Available globally on all ERPNext pages
 * - Minimizable and expandable
 * - Unread message indicator
 */

class AIChatWidget {
	constructor() {
		// Panel state: whether chat panel is open or closed
		this.is_open = false;
		
		// Streaming state: whether AI is currently responding
		this.is_streaming = false;
		
		// Current chat session object (from AI Chat Session DocType)
		this.current_session = null;
		
		// Array of message objects for current session
		this.messages = [];
		
		// DOM element of currently streaming assistant message
		this.current_stream_message = null;
		
		// Count of unread messages (shown in badge)
		this.unread_count = 0;
		
		// Initialize widget on construction
		this.init();
	}

	async init() {
		// Check if chatbot is enabled globally and for this user
		// Calls get_settings() API to verify permission
		const user_enabled = await this.check_user_permission();
		if (!user_enabled) return;

		// Inject CSS styles into page head (embedded CSS for single-file solution)
		this.add_styles();
		
		// Create DOM elements: bubble and panel
		this.create_chat_bubble();
		this.create_chat_panel();
		
		// Get existing active session or create new one via API
		await this.get_or_create_session();
	}

	async check_user_permission() {
		// Calls get_settings() to check if chatbot is enabled
		// Returns true if enabled, false otherwise
		try {
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.chat.get_settings'
			});
			
			const settings = response.message || {};
			// enabled === 1 means globally enabled
			return settings.enabled === 1;
		} catch (error) {
			console.error('Failed to check chatbot permission:', error);
			return false;
		}
	}

	add_styles() {
		const style = document.createElement('style');
		style.textContent = `
			/* Chat Bubble - Floating button */
			.ai-chat-bubble {
				position: fixed;
				bottom: 24px;
				right: 24px;
				width: 56px;
				height: 56px;
				border-radius: 50%;
				background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
				box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: center;
				z-index: 9998;
				transition: all 0.3s ease;
			}

			.ai-chat-bubble:hover {
				transform: scale(1.1);
				box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
			}

			.ai-chat-bubble.open {
				transform: scale(0.9);
			}

			.ai-chat-bubble-icon {
				font-size: 28px;
				color: white;
			}

			.ai-chat-bubble-badge {
				position: absolute;
				top: -4px;
				right: -4px;
				background: #ef4444;
				color: white;
				border-radius: 10px;
				padding: 2px 6px;
				font-size: 11px;
				font-weight: 600;
				min-width: 20px;
				text-align: center;
				display: none;
			}

			.ai-chat-bubble-badge.show {
				display: block;
			}

			/* Chat Panel - Slide-in container */
			.ai-chat-panel {
				position: fixed;
				right: -400px;
				bottom: 0;
				width: 400px;
				height: calc(100vh - 100px);
				max-height: 700px;
				background: var(--card-bg, white);
				box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
				z-index: 9999;
				transition: right 0.3s ease;
				display: flex;
				flex-direction: column;
				border-radius: 12px 0 0 12px;
				overflow: hidden;
			}

			.ai-chat-panel.open {
				right: 24px;
			}

			/* Chat Header */
			.ai-chat-header {
				padding: 16px 20px;
				background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
				color: white;
				display: flex;
				justify-content: space-between;
				align-items: center;
				flex-shrink: 0;
			}

			.ai-chat-header-title {
				font-size: 18px;
				font-weight: 600;
				display: flex;
				align-items: center;
				gap: 8px;
			}

			.ai-chat-header-actions {
				display: flex;
				gap: 8px;
			}

			.ai-chat-header-btn {
				background: rgba(255, 255, 255, 0.2);
				border: none;
				color: white;
				width: 32px;
				height: 32px;
				border-radius: 6px;
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: center;
				transition: background 0.2s;
			}

			.ai-chat-header-btn:hover {
				background: rgba(255, 255, 255, 0.3);
			}

			/* Messages Area */
			.ai-chat-messages {
				flex: 1;
				overflow-y: auto;
				padding: 16px;
				background: var(--bg-color, #f9fafb);
			}

			.ai-message-bubble {
				margin-bottom: 12px;
				animation: slideIn 0.2s ease;
			}

			@keyframes slideIn {
				from {
					opacity: 0;
					transform: translateY(10px);
				}
				to {
					opacity: 1;
					transform: translateY(0);
				}
			}

			.ai-message-content {
				padding: 10px 14px;
				border-radius: 12px;
				max-width: 85%;
				word-wrap: break-word;
				font-size: 14px;
				line-height: 1.5;
			}

			.ai-message-bubble.user .ai-message-content {
				background: #2563eb;
				color: white;
				margin-left: auto;
				border-bottom-right-radius: 4px;
			}

			.ai-message-bubble.assistant .ai-message-content {
				background: white;
				color: #1f2937;
				border: 1px solid #e5e7eb;
				border-bottom-left-radius: 4px;
			}

			.ai-message-time {
				font-size: 11px;
				color: var(--text-muted);
				margin-top: 4px;
				padding: 0 4px;
			}

			.ai-message-bubble.user .ai-message-time {
				text-align: right;
			}

			/* Typing Indicator */
			.ai-typing-indicator {
				display: flex;
				gap: 4px;
				padding: 10px 14px;
			}

			.ai-typing-dot {
				width: 8px;
				height: 8px;
				border-radius: 50%;
				background: #9ca3af;
				animation: typingBounce 1.4s infinite;
			}

			.ai-typing-dot:nth-child(2) {
				animation-delay: 0.2s;
			}

			.ai-typing-dot:nth-child(3) {
				animation-delay: 0.4s;
			}

			@keyframes typingBounce {
				0%, 60%, 100% {
					transform: translateY(0);
				}
				30% {
					transform: translateY(-10px);
				}
			}

			/* Tool Call Card */
			.ai-tool-card {
				background: #f0f9ff;
				border: 1px solid #bae6fd;
				border-radius: 8px;
				padding: 10px;
				margin-top: 8px;
				font-size: 13px;
			}

			.ai-tool-card-header {
				display: flex;
				align-items: center;
				gap: 6px;
				font-weight: 500;
				color: #0369a1;
				margin-bottom: 4px;
			}

			.ai-tool-card-name {
				font-family: monospace;
				font-size: 12px;
				color: #0c4a6e;
			}

			/* Input Area */
			.ai-chat-input-container {
				padding: 16px;
				background: var(--card-bg, white);
				border-top: 1px solid var(--border-color, #e5e7eb);
				flex-shrink: 0;
			}

			.ai-chat-input-wrapper {
				display: flex;
				gap: 8px;
				align-items: flex-end;
			}

			.ai-chat-textarea {
				flex: 1;
				min-height: 40px;
				max-height: 120px;
				padding: 10px 12px;
				border: 1px solid var(--border-color, #e5e7eb);
				border-radius: 8px;
				resize: none;
				font-size: 14px;
				font-family: inherit;
				background: var(--control-bg);
			}

			.ai-chat-textarea:focus {
				outline: none;
				border-color: #667eea;
				box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
			}

			.ai-chat-send-btn {
				background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
				border: none;
				color: white;
				width: 40px;
				height: 40px;
				border-radius: 8px;
				cursor: pointer;
				display: flex;
				align-items: center;
				justify-content: center;
				flex-shrink: 0;
				transition: transform 0.2s;
			}

			.ai-chat-send-btn:hover:not(:disabled) {
				transform: scale(1.05);
			}

			.ai-chat-send-btn:disabled {
				opacity: 0.5;
				cursor: not-allowed;
			}

			/* Responsive */
			@media (max-width: 768px) {
				.ai-chat-panel {
					width: 100%;
					right: -100%;
					border-radius: 0;
					max-height: 100vh;
					height: 100vh;
				}

				.ai-chat-panel.open {
					right: 0;
				}

				.ai-chat-bubble {
					bottom: 16px;
					right: 16px;
				}
			}

			/* Scrollbar */
			.ai-chat-messages::-webkit-scrollbar {
				width: 6px;
			}

			.ai-chat-messages::-webkit-scrollbar-track {
				background: transparent;
			}

			.ai-chat-messages::-webkit-scrollbar-thumb {
				background: #d1d5db;
				border-radius: 3px;
			}

			.ai-chat-messages::-webkit-scrollbar-thumb:hover {
				background: #9ca3af;
			}
		`;
		// Append style element to page head
		document.head.appendChild(style);
	}

	create_chat_bubble() {
		// Create floating chat bubble (bottom-right corner)
		// Shows robot emoji, has gradient background, displays unread badge
		this.bubble = $(`
			<div class="ai-chat-bubble" title="Open AI Assistant">
				<span class="ai-chat-bubble-icon">🤖</span>
				<span class="ai-chat-bubble-badge"></span>
			</div>
		`);

		// Click handler: toggle panel open/closed
		this.bubble.on('click', () => {
			this.toggle_panel();
		});

		// Append bubble to page body (fixed position, always visible)
		$('body').append(this.bubble);
	}

	create_chat_panel() {
		// Create slide-in chat panel (slides from right side)
		// Contains header, messages area, and input box
		this.panel = $(`
			<div class="ai-chat-panel">
				<div class="ai-chat-header">
					<div class="ai-chat-header-title">
						<span>🤖</span>
						<span>AI Assistant</span>
					</div>
					<div class="ai-chat-header-actions">
						<button class="ai-chat-header-btn" title="New Chat" data-action="new">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<line x1="12" y1="5" x2="12" y2="19"></line>
								<line x1="5" y1="12" x2="19" y2="12"></line>
							</svg>
						</button>
						<button class="ai-chat-header-btn" title="Clear History" data-action="clear">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<polyline points="3 6 5 6 21 6"></polyline>
								<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
							</svg>
						</button>
						<button class="ai-chat-header-btn" title="Close" data-action="close">
							<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<line x1="18" y1="6" x2="6" y2="18"></line>
								<line x1="6" y1="6" x2="18" y2="18"></line>
							</svg>
						</button>
					</div>
				</div>
				<div class="ai-chat-messages"></div>
				<div class="ai-chat-input-container">
					<div class="ai-chat-input-wrapper">
						<textarea 
							class="ai-chat-textarea" 
							placeholder="Ask me anything about your ERP..."
							rows="1"
						></textarea>
						<button class="ai-chat-send-btn" title="Send (Ctrl+Enter)">
							<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<line x1="22" y1="2" x2="11" y2="13"></line>
								<polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
							</svg>
						</button>
					</div>
				</div>
			</div>
		`);

		// Event handlers for header buttons
		this.panel.find('[data-action="close"]').on('click', () => this.toggle_panel());
		this.panel.find('[data-action="new"]').on('click', () => this.create_new_session());
		this.panel.find('[data-action="clear"]').on('click', () => this.clear_history());
		
		// Send button click handler
		this.panel.find('.ai-chat-send-btn').on('click', () => this.send_message());
		
		// Keyboard shortcut: Ctrl+Enter to send message
		this.panel.find('.ai-chat-textarea').on('keydown', (e) => {
			if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
				e.preventDefault();
				this.send_message();
			}
		});

		// Auto-resize textarea as user types (up to 120px max height)
		this.panel.find('.ai-chat-textarea').on('input', (e) => {
			e.target.style.height = 'auto';
			e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
		});

		// Append panel to page body (initially hidden, slides in when opened)
		$('body').append(this.panel);
	}

	toggle_panel() {
		// Toggle panel open/closed state
		this.is_open = !this.is_open;
		this.panel.toggleClass('open', this.is_open);
		this.bubble.toggleClass('open', this.is_open);

		if (this.is_open) {
			// Clear unread badge when opening
			this.unread_count = 0;
			this.bubble.find('.ai-chat-bubble-badge').removeClass('show');
			
			// Focus textarea after animation completes (300ms)
			setTimeout(() => {
				this.panel.find('.ai-chat-textarea').focus();
			}, 300);
		}
	}

	async get_or_create_session() {
		// Get existing active session or create new one
		// Reuses same API as full-page interface
		try {
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.chat.get_or_create_session'
			});

			if (!response || !response.message) {
				console.error('Invalid session response:', response);
				frappe.msgprint(__('Failed to initialize AI chat session - no session returned'));
				return;
			}

			this.current_session = response.message;
			console.log('Session created:', this.current_session.name);
			
			// Load message history after session is ready
			await this.load_messages();
		} catch (error) {
			console.error('Failed to get/create session:', error);
			
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

	async load_messages() {
		// Load message history for current session (limit 50 messages)
		if (!this.current_session) return;

		try {
			const response = await frappe.call({
				method: 'frappe_ai_chatbot.api.chat.get_messages',
				args: {
					session_id: this.current_session.name,
					limit: 50
				}
			});

			this.messages = response.message || [];
			// Render all messages in chat panel
			this.render_messages();
		} catch (error) {
			console.error('Failed to load messages:', error);
		}
	}

	render_messages() {
		// Clear existing messages and render all from this.messages array
		const container = this.panel.find('.ai-chat-messages');
		container.empty();

		// Create bubble for each message
		this.messages.forEach(msg => {
			const bubble = this.create_message_bubble(msg);
			container.append(bubble);
		});

		// Scroll to show latest messages
		this.scroll_to_bottom();
	}

	create_message_bubble(message) {
		// Format timestamp (HH:mm format, e.g., "14:30")
		const time = moment(message.timestamp).format('HH:mm');
		
		// Create message bubble div with role-based styling (user/assistant)
		const bubble = $(`
			<div class="ai-message-bubble ${message.role}">
				<div class="ai-message-content">${this.format_content(message.content)}</div>
				<div class="ai-message-time">${time}</div>
			</div>
		`);

		// If message has tool calls, add tool cards to show what tools were used
		if (message.tool_calls && message.tool_calls.length > 0) {
			message.tool_calls.forEach(tool => {
				const tool_card = this.create_tool_card(tool);
				bubble.find('.ai-message-content').append(tool_card);
			});
		}

		return bubble;
	}

	create_tool_card(tool) {
		// Create visual card showing tool execution (blue background, tool icon)
		return $(`
			<div class="ai-tool-card">
				<div class="ai-tool-card-header">
					<span>🔧</span>
					<span class="ai-tool-card-name">${tool.name}</span>
				</div>
			</div>
		`);
	}

	format_content(text) {
		// Apply basic markdown formatting to message text
		// **bold**, *italic*, `code`, newlines → HTML
		text = text
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')  // Bold
			.replace(/\*(.+?)\*/g, '<em>$1</em>')              // Italic
			.replace(/`(.+?)`/g, '<code>$1</code>')            // Inline code
			.replace(/\n/g, '<br>');                           // Newlines
		
		return text;
	}

	async send_message() {
		// Get message text from textarea, trim whitespace
		const textarea = this.panel.find('.ai-chat-textarea');
		const message = textarea.val().trim();

		// Validate: Don't send empty messages or while already streaming
		if (!message || this.is_streaming) return;

		// Ensure session exists before sending
		if (!this.current_session) {
			await this.get_or_create_session();
			if (!this.current_session) {
				frappe.msgprint(__('Failed to create chat session'));
				return;
			}
		}

		// Clear textarea and reset height (after auto-resize)
		textarea.val('').css('height', 'auto');

		// Disable input controls to prevent duplicate sends during streaming
		this.set_input_state(false);
		this.is_streaming = true;

		// Add user message bubble immediately (optimistic UI pattern)
		const user_bubble = this.create_message_bubble({
			role: 'user',
			content: message,
			timestamp: new Date().toISOString()
		});
		this.panel.find('.ai-chat-messages').append(user_bubble);
		this.scroll_to_bottom();

		// Create assistant message placeholder with animated typing indicator
		// (3 dots that bounce while waiting for response)
		this.current_stream_message = $(`
			<div class="ai-message-bubble assistant">
				<div class="ai-message-content">
					<div class="ai-typing-indicator">
						<div class="ai-typing-dot"></div>
						<div class="ai-typing-dot"></div>
						<div class="ai-typing-dot"></div>
					</div>
				</div>
			</div>
		`);
		this.panel.find('.ai-chat-messages').append(this.current_stream_message);
		this.scroll_to_bottom();

		// Establish SSE (Server-Sent Events) connection for streaming response
		// stream_chat endpoint will send events as AI generates response
		const url = `/api/method/frappe_ai_chatbot.api.stream.stream_chat?session_id=${encodeURIComponent(this.current_session.name)}&message=${encodeURIComponent(message)}`;
		const eventSource = new EventSource(url);

		// Accumulate content chunks as they arrive
		let accumulated_content = '';

		// Handle 'content' events: AI response text chunks
		eventSource.addEventListener('content', (e) => {
			const data = JSON.parse(e.data);
			accumulated_content += data.content;
			
			// Replace typing indicator with actual content, apply markdown formatting
			this.current_stream_message.find('.ai-message-content').html(
				this.format_content(accumulated_content)
			);
			this.scroll_to_bottom();
		});

		// Handle 'tool_call' events: When AI uses a tool (search, create doc, etc.)
		eventSource.addEventListener('tool_call', (e) => {
			const data = JSON.parse(e.data);
			const tool_card = this.create_tool_card(data);
			this.current_stream_message.find('.ai-message-content').append(tool_card);
			this.scroll_to_bottom();
		});

		// Handle 'done' event: Stream complete, cleanup
		eventSource.addEventListener('done', (e) => {
			eventSource.close();
			
			// Add timestamp to final message
			const time = moment().format('HH:mm');
			this.current_stream_message.append(`<div class="ai-message-time">${time}</div>`);
			
			// Reset streaming state, re-enable input
			this.current_stream_message = null;
			this.is_streaming = false;
			this.set_input_state(true);
			
			// If panel is closed, show unread badge on bubble
			if (!this.is_open) {
				this.unread_count++;
				this.bubble.find('.ai-chat-bubble-badge')
					.text(this.unread_count)
					.addClass('show');
			}
		});

		// Handle 'error' events: Connection failures, server errors
		eventSource.addEventListener('error', (e) => {
			eventSource.close();
			console.error('Streaming error:', e);
			
			// Replace typing indicator with error message (red text)
			this.current_stream_message.find('.ai-message-content').html(
				'<span style="color: #ef4444;">Error: Failed to get response</span>'
			);
			
			// Reset streaming state, re-enable input
			this.is_streaming = false;
			this.set_input_state(true);
		});
	}

	set_input_state(enabled) {
		// Enable or disable textarea and send button (used during streaming)
		this.panel.find('.ai-chat-textarea').prop('disabled', !enabled);
		this.panel.find('.ai-chat-send-btn').prop('disabled', !enabled);
	}

	scroll_to_bottom() {
		// Auto-scroll messages container to show latest message
		// Called after adding new messages or content updates
		const messages_container = this.panel.find('.ai-chat-messages');
		messages_container.scrollTop(messages_container[0].scrollHeight);
	}

	async create_new_session() {
		// Don't allow creating new session while streaming
		if (this.is_streaming) return;

		try {
			// Close current session via API (marks as complete in database)
			if (this.current_session) {
				await frappe.call({
					method: 'frappe_ai_chatbot.api.chat.close_session',
					args: { session_id: this.current_session.name }
				});
			}

			// Create fresh session, clears messages, resets unread count
			await this.get_or_create_session();
			frappe.show_alert({ message: __('New chat session started'), indicator: 'green' });
		} catch (error) {
			console.error('Failed to create new session:', error);
			frappe.msgprint(__('Failed to create new session'));
		}
	}

	async clear_history() {
		// Don't allow clearing history while streaming
		if (this.is_streaming) return;

		// Show confirmation dialog before destructive action
		frappe.confirm(
			__('Are you sure you want to clear this conversation?'),
			async () => {
				try {
					// Call API to delete all messages in current session
					await frappe.call({
						method: 'frappe_ai_chatbot.api.chat.clear_history',
						args: { session_id: this.current_session.name }
					});

					// Clear local messages array and re-render (empty state)
					this.messages = [];
					this.render_messages();
					frappe.show_alert({ message: __('Chat history cleared'), indicator: 'green' });
				} catch (error) {
					console.error('Failed to clear history:', error);
					frappe.msgprint(__('Failed to clear history'));
				}
			}
		);
	}
}

// Initialize widget when Frappe framework is ready (DOM loaded, frappe.ready() fired)
// Wrap in check to ensure frappe is loaded (prevents "frappe.ready is not a function" error)
if (typeof frappe !== 'undefined' && frappe.ready) {
	frappe.ready(() => {
		// Only initialize if not already on full-page AI Assistant interface
		// Prevents duplicate widgets when full-page launcher is also active
		if (window.location.pathname !== '/app/ai-assistant') {
			window.ai_chat_widget = new AIChatWidget();
		}
	});
} else {
	// Fallback: Wait for frappe to load using window.onload
	window.addEventListener('load', () => {
		setTimeout(() => {
			if (typeof frappe !== 'undefined' && frappe.ready) {
				frappe.ready(() => {
					if (window.location.pathname !== '/app/ai-assistant') {
						window.ai_chat_widget = new AIChatWidget();
					}
				});
			}
		}, 500);
	});
}
