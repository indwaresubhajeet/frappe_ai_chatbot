/**
 * AI Assistant Launcher
 * 
 * Adds a "Launch AI Assistant" button to the ERPNext navbar.
 * When clicked, opens the AI Assistant page.
 */

// Wrap in check to ensure frappe is loaded (prevents "frappe.ready is not a function" error)
if (typeof frappe !== 'undefined' && frappe.ready) {
	frappe.ready(function() {
		// Add AI Assistant button to navbar
		add_ai_assistant_button();
	});
} else {
	// Fallback: Wait for frappe to load using window.onload
	window.addEventListener('load', () => {
		setTimeout(() => {
			if (typeof frappe !== 'undefined' && frappe.ready) {
				frappe.ready(function() {
					add_ai_assistant_button();
				});
			}
		}, 500);
	});
}

function add_ai_assistant_button() {
	// Wait for navbar to be ready
	setTimeout(() => {
		if (!$('.navbar-home').length) {
			// Retry if navbar not ready
			add_ai_assistant_button();
			return;
		}
		
		// Check if button already exists
		if ($('#ai-assistant-launcher').length) {
			return;
		}
		
		// Create launcher button
		const button = $(`
			<li id="ai-assistant-launcher">
				<a href="#" class="dropdown-toggle" onclick="launch_ai_assistant(); return false;">
					<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="margin-right: 4px; vertical-align: middle;">
						<path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"/>
						<path d="M5 6a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm4 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm4 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
					</svg>
					<span>AI Assistant</span>
				</a>
			</li>
		`);
		
		// Add button to navbar (after Home, before other items)
		$('.navbar-home').after(button);
		
		// Add some styling
		if (!$('#ai-assistant-launcher-styles').length) {
			$('head').append(`
				<style id="ai-assistant-launcher-styles">
					#ai-assistant-launcher a {
						color: var(--navbar-text-color) !important;
						font-weight: 500;
						padding: 8px 15px;
						display: flex;
						align-items: center;
						transition: all 0.2s;
					}
					
					#ai-assistant-launcher a:hover {
						background: var(--navbar-bg-hover);
						color: var(--primary) !important;
					}
					
					#ai-assistant-launcher svg {
						opacity: 0.8;
					}
					
					#ai-assistant-launcher a:hover svg {
						opacity: 1;
					}
					
					@media (max-width: 768px) {
						#ai-assistant-launcher span {
							display: none;
						}
					}
				</style>
			`);
		}
	}, 500);
}

// Global function to launch AI Assistant
window.launch_ai_assistant = function() {
	frappe.set_route('ai-assistant');
};

// Also add keyboard shortcut (Ctrl/Cmd + Shift + A)
$(document).on('keydown', function(e) {
	if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'A') {
		e.preventDefault();
		launch_ai_assistant();
	}
});

// Show welcome notification on first login
frappe.ui.toolbar.on_collapse = function() {
	// Check if user has enabled AI chatbot
	if (frappe.boot.user && frappe.boot.user.enable_ai_chatbot !== 0) {
		// Show notification once per session
		if (!sessionStorage.getItem('ai_assistant_welcome_shown')) {
			sessionStorage.setItem('ai_assistant_welcome_shown', '1');
			
			setTimeout(() => {
				frappe.show_alert({
					message: `
						<div style="display: flex; align-items: center; gap: 12px;">
							<svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
								<path d="M14 1a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4.414A2 2 0 0 0 3 11.586l-2 2V2a1 1 0 0 1 1-1h12zM2 0a2 2 0 0 0-2 2v12.793a.5.5 0 0 0 .854.353l2.853-2.853A1 1 0 0 1 4.414 12H14a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H2z"/>
								<path d="M5 6a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm4 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0zm4 0a1 1 0 1 1-2 0 1 1 0 0 1 2 0z"/>
							</svg>
							<div>
								<div style="font-weight: 600; margin-bottom: 4px;">AI Assistant is ready!</div>
								<div style="font-size: 12px; opacity: 0.9;">
									Click "AI Assistant" in the navbar or press Ctrl+Shift+A
								</div>
							</div>
						</div>
					`,
					indicator: 'blue'
				}, 8);
			}, 2000);
		}
	}
};
