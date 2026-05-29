"""
Flask web server for CNEC Chatbot with Claude API + function calling.

Runs on localhost:5000 by default. Accessible from other machines on the same network
at http://<your-ip>:5000.
"""

from dotenv import load_dotenv
from pathlib import Path

# Load .env variables before other imports
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

import json
import os
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from datetime import datetime
from audit_log import AuditLogger

app = Flask(__name__)
audit = AuditLogger()

# Use mock chatbot for testing (doesn't hit any LLM API)
if os.getenv("TEST_MODE", "").lower() == "true":
    print("🧪 TEST MODE ENABLED - Using mock chatbot (no LLM API calls)")
    from mock_chatbot import MockChatbotEngine
    chatbot = MockChatbotEngine()
else:
    from chatbot import ChatbotEngine
    from llm_provider import get_provider

    try:
        provider = get_provider()
        chatbot = ChatbotEngine(provider=provider)
    except RuntimeError as e:
        print(f"❌ Failed to initialize LLM provider: {e}")
        print("   Check your .env file and LLM_PROVIDER setting.")
        raise

# Serve logo from asset folder
@app.route("/asset/<path:filename>")
def serve_asset(filename):
    """Serve logo and other assets."""
    asset_path = Path(__file__).parent / "asset" / filename
    if asset_path.exists():
        return send_file(asset_path)
    return jsonify({"error": "Asset not found"}), 404


@app.route("/", methods=["GET"])
def index():
    """Serve the chat interface."""
    return """<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CNEC Chatbot</title>
        <style>
            :root {
                --cn-blue: #0052CC;
                --cn-orange: #FF6D00;
                --neutral-light: #F5F5F5;
                --neutral-bg: #FFFFFF;
                --text-primary: #1A1A1A;
                --text-secondary: #666666;
                --border-color: #E0E0E0;
            }

            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }

            .container {
                width: 100%;
                max-width: 900px;
                height: 90vh;
                max-height: 700px;
                background: var(--neutral-bg);
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .header {
                background: linear-gradient(135deg, var(--cn-blue) 0%, #003d99 100%);
                color: white;
                padding: 20px;
                display: flex;
                align-items: center;
                gap: 16px;
                flex-shrink: 0;
            }

            .header img {
                height: 50px;
                width: auto;
                object-fit: contain;
            }

            .header-text h1 {
                font-size: 24px;
                font-weight: 600;
                margin: 0;
            }

            .header-text p {
                font-size: 12px;
                opacity: 0.9;
                margin: 4px 0 0 0;
            }

            #chat {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .message {
                display: flex;
                animation: slideIn 0.3s ease-out;
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

            .message.user {
                justify-content: flex-end;
            }

            .message.user .bubble {
                background: var(--cn-blue);
                color: white;
                border-radius: 18px 18px 4px 18px;
            }

            .message.assistant .bubble {
                background: var(--neutral-light);
                color: var(--text-primary);
                border-radius: 18px 18px 18px 4px;
            }

            .message.error .bubble {
                background: #FFE0E0;
                color: #C41C3B;
                border-radius: 18px;
            }

            .bubble {
                padding: 12px 16px;
                max-width: 75%;
                word-wrap: break-word;
                line-height: 1.5;
                font-size: 14px;
                white-space: pre-wrap;
                word-break: break-word;
            }

            .bubble a {
                color: var(--cn-blue);
                text-decoration: underline;
                cursor: pointer;
            }

            .bubble table {
                margin: 8px 0;
                border-collapse: collapse;
                width: 100%;
            }

            .bubble table th {
                background: rgba(0, 0, 0, 0.05);
                padding: 8px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid rgba(0, 0, 0, 0.1);
            }

            .bubble table td {
                padding: 8px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            }

            .bubble table tr:last-child td {
                border-bottom: none;
            }

            .thinking {
                display: flex;
                align-items: center;
                gap: 8px;
                color: var(--text-secondary);
                font-size: 13px;
                padding: 12px 16px;
                background: var(--neutral-light);
                border-radius: 18px;
            }

            .dots {
                display: inline-flex;
                gap: 4px;
            }

            .dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: var(--text-secondary);
                animation: bounce 1.4s infinite;
            }

            .dot:nth-child(2) {
                animation-delay: 0.2s;
            }

            .dot:nth-child(3) {
                animation-delay: 0.4s;
            }

            @keyframes bounce {
                0%, 60%, 100% {
                    opacity: 0.6;
                    transform: translateY(0);
                }
                30% {
                    opacity: 1;
                    transform: translateY(-8px);
                }
            }

            .input-area {
                padding: 16px 20px;
                background: var(--neutral-bg);
                border-top: 1px solid var(--border-color);
                display: flex;
                gap: 12px;
                flex-shrink: 0;
            }

            #message {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid var(--border-color);
                border-radius: 24px;
                font-size: 14px;
                font-family: inherit;
                outline: none;
                transition: all 0.2s;
            }

            #message:focus {
                border-color: var(--cn-blue);
                box-shadow: 0 0 0 3px rgba(0, 82, 204, 0.1);
            }

            #message:disabled {
                background: var(--neutral-light);
                cursor: not-allowed;
                opacity: 0.6;
            }

            button {
                padding: 12px 28px;
                background: var(--cn-blue);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            button:hover:not(:disabled) {
                background: var(--cn-orange);
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(255, 109, 0, 0.3);
            }

            button:active:not(:disabled) {
                transform: translateY(0);
            }

            button:disabled {
                background: #CCCCCC;
                cursor: not-allowed;
                opacity: 0.6;
            }

            @media (max-width: 768px) {
                .container {
                    max-height: 100%;
                    border-radius: 0;
                }
                .bubble {
                    max-width: 90%;
                }
                .header h1 {
                    font-size: 20px;
                }
                .header img {
                    height: 40px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="/asset/cnec-logo.jpeg" alt="Code Ninjas Eastvale Chino Logo">
                <div class="header-text">
                    <h1>GBS Tour Assistant</h1>
                    <p>Code Ninjas Eastvale Chino</p>
                </div>
            </div>

            <div id="chat"></div>

            <div class="input-area">
                <input type="text" id="message" placeholder="Ask about GBS tours..." autocomplete="off">
                <button id="sendBtn" onclick="console.log('Button clicked'); sendMessage();">Send</button>
            </div>
        </div>

        <script>
        let isProcessing = false;

        function parseMarkdownLinks(text) {
            return text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        }

        function sendMessage() {
            const input = document.getElementById('message');
            const button = document.getElementById('sendBtn');
            const message = input.value.trim();
            if (!message || isProcessing) return;
            isProcessing = true;
            input.disabled = true;
            button.disabled = true;
            const chat = document.getElementById('chat');

            const userMsg = document.createElement('div');
            userMsg.className = 'message user';
            const userBubble = document.createElement('div');
            userBubble.className = 'bubble';
            userBubble.textContent = message;
            userMsg.appendChild(userBubble);
            chat.appendChild(userMsg);
            input.value = '';

            const thinkingMsg = document.createElement('div');
            thinkingMsg.className = 'message assistant';
            thinkingMsg.innerHTML = '<div class="thinking"><span>Claude is thinking</span><div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>';
            chat.appendChild(thinkingMsg);
            chat.scrollTop = chat.scrollHeight;

            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            }).then(r => r.json()).then(data => {
                thinkingMsg.remove();
                const assistantMsg = document.createElement('div');
                assistantMsg.className = 'message assistant';
                const assistantBubble = document.createElement('div');
                assistantBubble.className = 'bubble';
                assistantBubble.innerHTML = parseMarkdownLinks(data.response);
                assistantMsg.appendChild(assistantBubble);
                chat.appendChild(assistantMsg);
                chat.scrollTop = chat.scrollHeight;
                isProcessing = false;
                input.disabled = false;
                button.disabled = false;
                input.focus();
            }).catch(err => {
                thinkingMsg.remove();
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message error';
                const errorBubble = document.createElement('div');
                errorBubble.className = 'bubble';
                errorBubble.textContent = 'Error: ' + err.message;
                errorMsg.appendChild(errorBubble);
                chat.appendChild(errorMsg);
                isProcessing = false;
                input.disabled = false;
                button.disabled = false;
            });
        }
        document.getElementById('message').addEventListener('keypress', e => {
            if (e.key === 'Enter' && !isProcessing) sendMessage();
        });
        document.getElementById('message').focus();
        </script>
    </body>
    </html>
    """


@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages via Claude API with function calling."""
    try:
        data = request.json
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"error": "Empty message"}), 400

        # Log the user message
        audit.log_event("user_message", {"message": user_message})

        # Process with chatbot (handles Claude API + tool execution)
        response_text = chatbot.chat(user_message)

        # Log the response
        audit.log_event("assistant_response", {"message": response_text})

        return jsonify({"response": response_text})

    except Exception as e:
        audit.log_event("error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500


@app.route("/api/audit-log", methods=["GET"])
def get_audit_log():
    """Retrieve audit log entries (staff/owner only in production)."""
    try:
        entries = audit.read_log()
        return jsonify({"entries": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/tours", methods=["GET"])
def export_tours():
    """Export today's tours to Excel file."""
    try:
        from export_tours import create_excel_file
        import asyncio

        # Get tours
        if os.getenv("TEST_MODE", "").lower() == "true":
            from format_tours import get_sample_sessions
            sessions = get_sample_sessions()
        else:
            from sites.lineleader.auth import get_bearer_token
            from sites.lineleader.schedules import get_todays_sessions, enrich_sessions_with_children

            bearer_token = asyncio.run(get_bearer_token())
            sessions = get_todays_sessions(bearer_token)
            enrich_sessions_with_children(bearer_token, sessions)

        if not sessions:
            return jsonify({"error": "No tours found"}), 400

        # Create Excel file
        filepath = asyncio.run(create_excel_file(sessions))

        # Return file for download
        return send_file(
            filepath,
            as_attachment=True,
            download_name=Path(filepath).name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        audit.log_event("error", {"error": f"Export failed: {str(e)}"})
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    # Bind to 0.0.0.0 to allow connections from other machines on the network
    app.run(host="0.0.0.0", port=5001, debug=True)
