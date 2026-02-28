/*!
 * chat.js
 * Handles the AI Research Assistant chat interface and API calls.
 */

class ChatController {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.historyElement = document.getElementById('chat-history');
        this.inputElement = this.container.querySelector('textarea');

        this._attachEventListeners();
    }

    _attachEventListeners() {
        this.inputElement.addEventListener('keydown', (e) => {
            // Send message on Enter (without Shift)
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._sendMessage();
            }
        });
    }

    async _sendMessage() {
        const messageText = this.inputElement.value.trim();
        if (!messageText) return;

        // 1. Add user message to UI
        this._appendMessage('user', messageText);
        this.inputElement.value = '';

        // 2. Add loading state
        const loadingId = this._appendMessage('ai', 'Thinking...', true);

        try {
            // 3. Call local backend API
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageText })
            });

            if (!response.ok) throw new Error('API Request Failed');

            const data = await response.json();

            // 4. Update UI with response
            this._updateMessage(loadingId, data.response);

        } catch (error) {
            console.error("Chat Error:", error);
            this._updateMessage(loadingId, 'Sorry, I encountered an error checking your secure records.');
        }
    }

    _appendMessage(role, text, isLoading = false) {
        const msgDiv = document.createElement('div');
        const msgId = 'msg-' + Date.now();
        msgDiv.id = msgId;
        msgDiv.className = `chat-msg msg-${role}`;
        if (isLoading) msgDiv.style.opacity = '0.5';

        msgDiv.textContent = text;
        this.historyElement.appendChild(msgDiv);
        this.historyElement.scrollTop = this.historyElement.scrollHeight;

        return msgId;
    }

    _updateMessage(msgId, text) {
        const msgDiv = document.getElementById(msgId);
        if (msgDiv) {
            msgDiv.textContent = text;
            msgDiv.style.opacity = '1';
            this.historyElement.scrollTop = this.historyElement.scrollHeight;
        }
    }
}
