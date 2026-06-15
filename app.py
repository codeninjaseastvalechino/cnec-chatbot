"""
Flask web server for CNEC Chatbot with Claude API + function calling.

Runs on localhost:5001. Accessible from other machines on the same network
at http://<your-ip>:5001.
"""

from dotenv import load_dotenv
from pathlib import Path

# Load .env variables before other imports
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

import json
import os
from core.logger import get_logger
logger = get_logger(__name__)
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from datetime import datetime
from audit_log import AuditLogger
from analytics import QueryAnalytics
from config.settings import settings

app = Flask(__name__)
audit = AuditLogger()
analytics = QueryAnalytics()

# Cache last fetched schedule for Excel export (avoid double API calls)
_schedule_cache = {"gbs_sessions": [], "appointments": []}

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
        <title>CNEC Studio Assistant</title>
        <style>
            :root {
                --cn-orange: #d96d32;
                --cn-orange-hover: #bf5a25;
                --cn-navy: #162044;
                --cn-navy-deep: #0f1a35;
                --cn-navy-card: #1a2a4a;
                --cn-navy-border: #243356;
                --cn-gold: #eabb5c;
                --text-primary: #e8edf8;
                --text-secondary: #8ea4c8;
                --text-muted: #5a7aaa;
            }

            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            html, body {
                height: 100%;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: #0a1020;
                height: 100vh;
                margin: 0;
                overflow: hidden;
            }

            .container {
                width: 100%;
                height: 100vh;
                background: var(--cn-navy-deep);
                display: flex;
                flex-direction: row;
                overflow: hidden;
            }

            .chat-panel {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
            }

            .sidebar {
                width: 220px;
                flex-shrink: 0;
                background: var(--cn-navy);
                border-left: 1px solid var(--cn-navy-border);
                padding: 16px 12px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                overflow-y: auto;
            }

            .sidebar h3 {
                font-size: 10px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: var(--cn-gold);
                margin: 0 0 4px 0;
            }

            .quick-btn {
                width: 100%;
                padding: 9px 12px;
                background: var(--cn-navy-card);
                color: var(--text-primary);
                border: 1px solid var(--cn-navy-border);
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                text-align: left;
                transition: all 0.15s;
                line-height: 1.3;
                box-shadow: none;
                transform: none;
            }

            .quick-btn:hover:not(:disabled) {
                background: var(--cn-orange);
                color: white;
                border-color: var(--cn-orange);
                transform: none;
                box-shadow: none;
            }

            .sidebar-divider {
                height: 1px;
                background: var(--cn-navy-border);
                margin: 4px 0;
            }

            .download-btn {
                width: 100%;
                padding: 9px 12px;
                background: var(--cn-navy-card);
                color: #6b7a8d;
                border: 1px solid var(--cn-navy-border);
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
                line-height: 1.3;
                text-decoration: none;
                display: block;
                box-sizing: border-box;
                transition: all 0.15s;
                cursor: not-allowed;
                pointer-events: none;
                opacity: 0.5;
            }

            .download-btn.ready {
                background: #1a4731;
                color: #4caf7d;
                border-color: #2d6a4f;
                cursor: pointer;
                pointer-events: auto;
                opacity: 1;
            }

            .download-btn.ready:hover {
                background: #1D6F42;
                color: white;
                border-color: #1D6F42;
            }

            @media (max-width: 768px) {
                .sidebar { display: none; }
            }

            .header {
                background: var(--cn-navy);
                border-bottom: 1px solid var(--cn-navy-border);
                color: white;
                padding: 22px 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 20px;
                flex-shrink: 0;
            }

.header-text {
                text-align: left;
            }

            .header-text h1 {
                font-size: 30px;
                font-weight: 800;
                margin: 0;
                color: #ffffff;
                letter-spacing: -0.5px;
                line-height: 1;
            }

            .header-text p {
                font-size: 13px;
                color: var(--cn-gold);
                margin: 5px 0 0 0;
                letter-spacing: 0.03em;
            }

            #chat {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                background: var(--cn-navy-deep);
            }

            #chat::-webkit-scrollbar { width: 6px; }
            #chat::-webkit-scrollbar-track { background: transparent; }
            #chat::-webkit-scrollbar-thumb { background: var(--cn-navy-border); border-radius: 3px; }

            .message {
                display: flex;
                animation: slideIn 0.3s ease-out;
            }

            @keyframes slideIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .message.user {
                justify-content: flex-end;
            }

            .message.user .bubble {
                background: var(--cn-orange);
                color: white;
                border-radius: 18px 18px 4px 18px;
            }

            .message.assistant .bubble {
                background: var(--cn-navy-card);
                border: 1px solid var(--cn-navy-border);
                color: var(--text-primary);
                border-radius: 18px 18px 18px 4px;
            }

            .message.error .bubble {
                background: #3d1a1a;
                border: 1px solid #6b2222;
                color: #f87171;
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
                color: var(--cn-gold);
                text-decoration: underline;
                cursor: pointer;
            }

            .bubble table {
                margin: 8px 0;
                border-collapse: collapse;
                width: 100%;
            }

            .bubble table th {
                background: rgba(255, 255, 255, 0.05);
                padding: 8px;
                text-align: left;
                font-weight: 600;
                color: var(--cn-gold);
                border-bottom: 1px solid var(--cn-navy-border);
            }

            .bubble table td {
                padding: 8px;
                border-bottom: 1px solid var(--cn-navy-border);
                color: var(--text-primary);
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
                background: var(--cn-navy-card);
                border: 1px solid var(--cn-navy-border);
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
                background: var(--cn-orange);
                animation: bounce 1.4s infinite;
            }

            .dot:nth-child(2) { animation-delay: 0.2s; }
            .dot:nth-child(3) { animation-delay: 0.4s; }

            @keyframes bounce {
                0%, 60%, 100% { opacity: 0.4; transform: translateY(0); }
                30% { opacity: 1; transform: translateY(-6px); }
            }

            .input-area {
                padding: 16px 20px;
                background: var(--cn-navy);
                border-top: 1px solid var(--cn-navy-border);
                display: flex;
                gap: 12px;
                flex-shrink: 0;
            }

            #message {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid var(--cn-navy-border);
                border-radius: 24px;
                font-size: 14px;
                font-family: inherit;
                outline: none;
                transition: all 0.2s;
                background: var(--cn-navy-deep);
                color: var(--text-primary);
            }

            #message::placeholder { color: var(--text-muted); }

            #message:focus {
                border-color: var(--cn-orange);
                box-shadow: 0 0 0 3px rgba(217, 109, 50, 0.15);
            }

            #message:disabled {
                background: var(--cn-navy-card);
                cursor: not-allowed;
                opacity: 0.5;
            }

            button {
                padding: 12px 28px;
                background: var(--cn-orange);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 14px;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            button:hover:not(:disabled) {
                background: var(--cn-orange-hover);
                transform: translateY(-1px);
                box-shadow: 0 4px 14px rgba(217, 109, 50, 0.4);
            }

            button:active:not(:disabled) {
                transform: translateY(0);
            }

            button:disabled {
                background: var(--cn-navy-card);
                color: var(--text-muted);
                cursor: not-allowed;
                opacity: 0.6;
            }

            .feature-request-btn {
                background: #1a3a1a;
                border: 1px solid #2d5a2d;
                color: #6fcf97;
                width: 100%;
            }
            .feature-request-btn:hover:not(:disabled) {
                background: #2d5a2d;
                color: white;
                border-color: #6fcf97;
                box-shadow: none;
                transform: none;
            }

            .help-row {
                display: flex;
                gap: 12px;
                align-items: baseline;
                padding: 8px 0;
                border-bottom: 1px solid #243356;
            }
            .help-feature {
                font-size: 13px;
                font-weight: 600;
                color: #e8edf8;
                min-width: 220px;
                flex-shrink: 0;
            }
            .help-examples {
                font-size: 12px;
                color: #8ea4c8;
                line-height: 1.6;
            }
            .help-ex {
                color: #d96d32;
                cursor: pointer;
                font-style: italic;
            }
            .help-ex:hover { text-decoration: underline; color: #eabb5c; }
            .help-note {
                font-size: 12px;
                color: #5a7aaa;
                font-style: italic;
                line-height: 1.5;
            }

            .chat-panel { position: relative; }

            @media (max-width: 768px) {
                .bubble { max-width: 90%; }
                .header-text h1 { font-size: 18px; }
                .header img { height: 36px; }
            }
        </style>
    </head>
    <body>
        <!-- Who are you modal -->
        <div id="nameModal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:200;display:flex;align-items:center;justify-content:center;">
            <div style="background:#162044;border:1px solid #243356;border-radius:16px;padding:36px 40px;width:360px;text-align:center;">
                <div style="font-size:32px;margin-bottom:12px;">👋</div>
                <h2 style="font-size:20px;font-weight:700;color:#ffffff;margin:0 0 6px;">Who's using the assistant?</h2>
                <p style="font-size:13px;color:#eabb5c;margin:0 0 24px;">Select your name to get started</p>
                <select id="staffName" style="width:100%;padding:12px 14px;background:#0f1a35;border:1px solid #243356;border-radius:8px;color:#e8edf8;font-size:15px;font-family:inherit;margin-bottom:20px;outline:none;cursor:pointer;">
                    <option value="">— Select your name —</option>
                    <option>Daniel</option>
                    <option>Devin</option>
                    <option>Jayesh</option>
                    <option>Kelsey</option>
                    <option>Nameera</option>
                    <option>Nia</option>
                    <option>Prashant</option>
                    <option>Reace</option>
                    <option>Steven</option>
                    <option>Venay</option>
                    <option>Vinaya</option>
                </select>
                <button id="startBtn" onclick="confirmName()" style="width:100%;padding:13px;border-radius:8px;background:#d96d32;color:white;font-size:15px;font-weight:700;border:none;cursor:pointer;">Let's go</button>
            </div>
        </div>

        <div class="container">
            <div class="chat-panel">
                <div class="header">
                    <img src="/asset/cnec-logo.jpeg" alt="Code Ninjas Eastvale Chino Logo" style="height:56px; width:auto; object-fit:contain; border-radius:8px;">
                    <div class="header-text">
                        <h1>CNEC Studio Assistant</h1>
                        <p>Your AI operations assistant — just ask</p>
                    </div>
                    <button id="helpBtn" onclick="toggleHelp()" title="What can I ask?" style="margin-left:auto;padding:8px 16px;border-radius:20px;font-size:13px;font-weight:600;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);color:white;cursor:pointer;flex-shrink:0;">? What can I ask</button>
                </div>

                <!-- Help Modal -->
                <div id="helpModal" style="display:none;position:absolute;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:100;overflow-y:auto;">
                    <div style="max-width:680px;margin:40px auto;background:#162044;border:1px solid #243356;border-radius:16px;padding:32px;position:relative;">
                        <button onclick="toggleHelp()" style="position:absolute;top:16px;right:16px;background:transparent;border:none;color:#8ea4c8;font-size:20px;cursor:pointer;padding:4px 8px;border-radius:4px;">✕</button>
                        <h2 style="font-size:20px;font-weight:700;color:#ffffff;margin:0 0 4px;">What can I ask?</h2>
                        <p style="font-size:13px;color:#eabb5c;margin:0 0 24px;">Click any example to send it directly.</p>

                        <!-- Live now -->
                        <div style="margin-bottom:24px;">
                            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;background:#14532d;color:#86efac;padding:4px 10px;border-radius:4px;display:inline-block;margin-bottom:12px;">Live now</div>
                            <div class="help-row"><span class="help-feature">Full daily schedule</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Show me today\'s full schedule"</span> · <span class="help-ex" onclick="helpSend(this)">"What\'s on Friday?"</span></span></div>
                            <div class="help-row"><span class="help-feature">GBS &amp; JR GBS tours</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Any GBS tours tomorrow?"</span> · <span class="help-ex" onclick="helpSend(this)">"List upcoming tours this week"</span></span></div>
                            <div class="help-row"><span class="help-feature">Reschedule a tour</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Reschedule the 3pm tour to 4:30"</span> · <span class="help-ex" onclick="helpSend(this)">"Move Wittie Hughes to Thursday at 5"</span></span></div>
                            <div class="help-row"><span class="help-feature">Student lookup</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Look up Veshant Bhatia"</span> · <span class="help-ex" onclick="helpSend(this)">"What sessions does Alex have coming up?"</span></span></div>
                            <div class="help-row"><span class="help-feature">Cancel a session (single)</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Cancel Alex\'s session on June 20"</span></span></div>
                            <div class="help-row"><span class="help-feature">Move a session (single)</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Move Alex\'s June 18 class to June 20 at 3pm"</span></span></div>
                            <div class="help-row"><span class="help-feature">Summer camp schedule</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"What camps are running next week?"</span> · <span class="help-ex" onclick="helpSend(this)">"Camps for the week of July 17th"</span></span></div>
                            <div class="help-row"><span class="help-feature">Camp roster &amp; enrollment</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Who\'s enrolled in the Minecraft camp?"</span> · <span class="help-ex" onclick="helpSend(this)">"How many kids in the LEGO camp next week?"</span></span></div>
                            <div class="help-row" style="border-bottom:none;"><span class="help-feature">Excel export</span><span class="help-examples"><span class="help-ex" onclick="helpSend(this)">"Download today\'s schedule as Excel"</span> · <span class="help-ex" onclick="helpSend(this)">"Export Friday\'s tours"</span></span></div>
                        </div>

                        <!-- Coming soon -->
                        <div style="margin-bottom:24px;">
                            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;background:#1e3a5f;color:#93c5fd;padding:4px 10px;border-radius:4px;display:inline-block;margin-bottom:12px;">Coming soon</div>
                            <div class="help-row" style="border-bottom:none;"><span class="help-feature">Instant quick-query shortcuts</span><span class="help-note">Sidebar buttons will bypass Claude for faster responses</span></div>
                        </div>

                        <!-- Known limitations -->
                        <div>
                            <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;background:#451a03;color:#fcd34d;padding:4px 10px;border-radius:4px;display:inline-block;margin-bottom:12px;">Known limitations</div>
                            <div class="help-row"><span class="help-feature">Cancel/move all future recurring sessions</span><span class="help-note">API returns success but only affects the targeted session — under investigation</span></div>
                            <div class="help-row" style="border-bottom:none;"><span class="help-feature">Book a new appointment</span><span class="help-note">Blocked — requires a student token only available through the POS, not staff login</span></div>
                        </div>
                    </div>
                </div>

                <div id="chat"></div>

                <div class="input-area">
                    <input type="text" id="message" placeholder="Ask me anything about students, tours, schedules..." autocomplete="off">
                    <button id="sendBtn" onclick="sendMessage();">Send</button>
                </div>
            </div>

            <div class="sidebar">
                <h3>Quick Actions</h3>
                <button class="quick-btn" onclick="quickSend('What is my full schedule today?')">📅 Full schedule today</button>
                <button class="quick-btn" onclick="quickSend('What GBS tours are scheduled today?')">🎮 Today\'s GBS tours</button>

                <div class="sidebar-divider"></div>
                <h3>Schedule</h3>
                <button class="quick-btn" onclick="quickSend('How many students are coming today?')">👥 Student count</button>

                <div class="sidebar-divider"></div>
                <h3>Export</h3>
                <a id="sidebarDownloadBtn" class="download-btn" href="#" title="Fetch a schedule first">📊 Download as Excel</a>

                <div class="sidebar-divider"></div>
                <h3>Feedback</h3>
                <button class="quick-btn feature-request-btn" onclick="startFeatureRequest()">💡 Feature Request</button>
            </div>
        </div>

        <script>
        let isProcessing = false;

        function confirmName() {
            const name = document.getElementById('staffName').value;
            if (!name) { document.getElementById('staffName').style.borderColor = '#d96d32'; return; }
            sessionStorage.setItem('staffName', name);
            document.getElementById('nameModal').style.display = 'none';
        }

        // Always clear name on page load so modal shows every time
        sessionStorage.removeItem('staffName');

        function quickSend(text) {
            if (isProcessing) return;
            const input = document.getElementById('message');
            input.value = text;
            sendMessage();
        }

        function startFeatureRequest() {
            if (isProcessing) return;
            const input = document.getElementById('message');
            input.value = 'FEATURE REQUEST: ';
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
        }

        function toggleHelp() {
            const modal = document.getElementById('helpModal');
            modal.style.display = modal.style.display === 'none' ? 'block' : 'none';
        }

        function helpSend(el) {
            const text = el.textContent.replace(/^"|"$/g, '');
            toggleHelp();
            if (isProcessing) return;
            const input = document.getElementById('message');
            input.value = text;
            sendMessage();
        }

        document.getElementById('helpModal').addEventListener('click', function(e) {
            if (e.target === this) toggleHelp();
        });

        function parseMarkdownLinks(text) {
            return text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        }

        function updateSidebarDownload(exportType, exportLabel) {
            const btn = document.getElementById('sidebarDownloadBtn');
            if (!btn) return;
            if (exportType === 'tours') {
                btn.href = '/api/export/tours';
                btn.textContent = exportLabel === 'gbs_tours' ? '📊 Download GBS tours' : '📊 Download full schedule';
                btn.title = '';
                btn.classList.add('ready');
            } else if (exportType === 'camps') {
                btn.href = '/api/export/camps';
                btn.textContent = '📊 Download camps as Excel';
                btn.title = '';
                btn.classList.add('ready');
            } else if (exportType === 'none') {
                btn.href = '#';
                btn.textContent = '📊 Download as Excel';
                btn.title = 'Fetch a schedule first';
                btn.classList.remove('ready');
            }
            // null = Claude answered from context, no tool ran — leave button as-is
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
            const thinkingBubble = document.createElement('div');
            thinkingBubble.className = 'thinking';
            thinkingBubble.innerHTML = '<span id="status-text">Thinking...</span><div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
            thinkingMsg.appendChild(thinkingBubble);
            chat.appendChild(thinkingMsg);
            chat.scrollTop = chat.scrollHeight;

            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, user_name: sessionStorage.getItem('staffName') || 'Unknown' })
            }).then(r => r.json()).then(data => {
                thinkingMsg.remove();
                if (data.error) {
                    const errorMsg = document.createElement('div');
                    errorMsg.className = 'message error';
                    const errorBubble = document.createElement('div');
                    errorBubble.className = 'bubble';
                    errorBubble.textContent = 'Error: ' + data.error;
                    errorMsg.appendChild(errorBubble);
                    chat.appendChild(errorMsg);
                } else {
                    const assistantMsg = document.createElement('div');
                    assistantMsg.className = 'message assistant';
                    const assistantBubble = document.createElement('div');
                    assistantBubble.className = 'bubble';
                    assistantBubble.innerHTML = parseMarkdownLinks(data.response);
                    updateSidebarDownload(data.export_type, data.export_label);
                    assistantMsg.appendChild(assistantBubble);
                    chat.appendChild(assistantMsg);
                }
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


FEATURE_REQUESTS_FILE = Path("logs/feature_requests.jsonl")


def _save_feature_request(text: str, user: str = "Unknown") -> None:
    FEATURE_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FEATURE_REQUESTS_FILE, "a") as f:
        f.write(json.dumps({"ts": datetime.utcnow().isoformat(), "user": user, "request": text}) + "\n")
    logger.info("Feature request saved by %s: %s", user, text)


@app.route("/api/feature-requests", methods=["GET"])
def get_feature_requests():
    """Return all saved feature requests."""
    try:
        if not FEATURE_REQUESTS_FILE.exists():
            return jsonify({"requests": []})
        entries = []
        with open(FEATURE_REQUESTS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return jsonify({"requests": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages, streaming SSE status updates then final response."""
    data = request.json
    user_message = data.get("message", "").strip()
    user_name = data.get("user_name", "Unknown").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    audit.log_event("user_message", {"message": user_message, "user": user_name})

    # Feature request — save to file and return immediately, no Claude call needed
    if user_message.upper().startswith("FEATURE REQUEST:"):
        request_text = user_message[len("FEATURE REQUEST:"):].strip()
        if request_text:
            _save_feature_request(request_text, user=user_name)
            return jsonify({
                "response": "✅ Thanks for the feedback! Your feature request has been saved and will be reviewed.",
                "statuses": []
            })
        else:
            return jsonify({
                "response": "Please describe your feature request after 'FEATURE REQUEST:'",
                "statuses": []
            })

    try:
        statuses = []
        # Clear camp cache before each call so stale data doesn't bleed into new responses
        if not os.getenv("TEST_MODE", ""):
            chatbot._last_camp_data = None
        response_text = chatbot.chat(user_message, status_callback=lambda msg: statuses.append(msg), user_name=user_name)
        audit.log_event("assistant_response", {"message": response_text, "user": user_name})
        # Tell the client which export endpoint to use
        # "tours"/"camps" → schedule ran, enable button
        # "none"          → non-schedule tool ran, disable button
        # null            → Claude answered from context, leave button as-is
        camp_data = getattr(chatbot, "_last_camp_data", None)
        schedule_fetched = getattr(chatbot, "_last_schedule_fetched", False)
        any_tool_ran = getattr(chatbot, "_last_any_tool_ran", False)
        export_label = getattr(chatbot, "_last_export_label", None)
        if camp_data and camp_data.get("camps"):
            export_type = "camps"
        elif schedule_fetched:
            export_type = "tours"
        elif any_tool_ran:
            export_type = "none"
        else:
            export_type = None
        return jsonify({"response": response_text, "statuses": statuses, "export_type": export_type, "export_label": export_label})
    except Exception as e:
        logger.error("Chat error: %s", e)
        audit.log_event("error", {"error": str(e), "user": user_name})
        return jsonify({"error": str(e)}), 500


@app.route("/api/audit-log", methods=["GET"])
def get_audit_log():
    """Retrieve audit log entries (staff/owner only in production)."""
    try:
        entries = audit.read_log()
        return jsonify({"entries": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """
    Query analytics — most common queries, most called tools, recent history.

    GET /api/analytics             → full summary
    GET /api/analytics?recent=50   → last 50 entries
    """
    try:
        return jsonify({
            "top_intents": analytics.top_intents(limit=10),
            "top_tools":   analytics.top_tools(limit=10),
            "top_queries": analytics.top_queries(limit=10),
            "recent":      analytics.recent(limit=int(request.args.get("recent", 50))),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin")
def admin():
    """Password-protected admin dashboard — feature requests, analytics, recent queries."""
    password = request.args.get("pw", "")
    if password != settings.ADMIN_PASSWORD:
        return """
        <html><head><title>Admin Login</title>
        <style>
            body { font-family: sans-serif; display: flex; align-items: center;
                   justify-content: center; height: 100vh; margin: 0; background: #f3f4f6; }
            form { background: white; padding: 32px; border-radius: 12px;
                   box-shadow: 0 4px 16px rgba(0,0,0,0.1); text-align: center; }
            h2 { margin: 0 0 20px; color: #1a1a2e; }
            input { padding: 10px 16px; border: 1px solid #ddd; border-radius: 8px;
                    font-size: 14px; margin-right: 8px; }
            button { padding: 10px 20px; background: #FF6D00; color: white;
                     border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        </style></head><body>
        <form method="get">
            <h2>🔐 Admin Login</h2>
            <input type="password" name="pw" placeholder="Password" autofocus>
            <button type="submit">Enter</button>
        </form></body></html>
        """, 401

    return f"""
    <html><head><title>CNEC Admin</title>
    <style>
        body {{ font-family: sans-serif; margin: 0; background: #f3f4f6; color: #1a1a2e; }}
        .header {{ background: #1a1a2e; color: white; padding: 16px 32px;
                   display: flex; align-items: center; gap: 12px; }}
        .header h1 {{ margin: 0; font-size: 20px; }}
        .container {{ max-width: 1100px; margin: 32px auto; padding: 0 24px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        .card {{ background: white; border-radius: 12px; padding: 24px;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.07); }}
        .card h2 {{ margin: 0 0 16px; font-size: 16px; color: #FF6D00; }}
        .card.full {{ grid-column: 1 / -1; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ text-align: left; padding: 8px; background: #f3f4f6;
              border-bottom: 2px solid #e5e7eb; }}
        td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
        tr:last-child td {{ border-bottom: none; }}
        .empty {{ color: #999; font-style: italic; padding: 12px 0; }}
        .badge {{ display: inline-block; background: #e0f2fe; color: #0369a1;
                  border-radius: 12px; padding: 2px 8px; font-size: 11px; }}
        .refresh {{ float: right; font-size: 12px; color: #999; }}
    </style></head><body>
    <div class="header">
        <h1>CNEC Admin Dashboard</h1>
        <span style="margin-left: auto; font-size: 13px; opacity: 0.7;">Code Ninjas Eastvale Chino</span>
    </div>
    <div class="container">
        <div class="grid">
            <div class="card full" id="feature-requests">
                <h2>💡 Feature Requests <span class="refresh"><a href="/admin?pw={password}">↻ Refresh</a></span></h2>
                <div id="fr-content">Loading...</div>
            </div>
            <div class="card" id="top-tools">
                <h2>🔧 Most Used Tools</h2>
                <div id="tools-content">Loading...</div>
            </div>
            <div class="card" id="top-queries">
                <h2>💬 Most Common Queries</h2>
                <div id="queries-content">Loading...</div>
            </div>
            <div class="card full" id="recent-queries">
                <h2>🕐 Recent Activity</h2>
                <div id="recent-content">Loading...</div>
            </div>
        </div>
    </div>
    <script>
    async function load() {{
        // Feature requests
        const fr = await fetch('/api/feature-requests').then(r => r.json());
        const frEl = document.getElementById('fr-content');
        if (!fr.requests || fr.requests.length === 0) {{
            frEl.innerHTML = '<p class="empty">No feature requests yet.</p>';
        }} else {{
            const rows = fr.requests.slice().reverse().map(r => {{
                const ts = new Date(r.ts + (r.ts.endsWith('Z') ? '' : 'Z')).toLocaleString('en-US', {{timeZone:'America/Los_Angeles',month:'2-digit',day:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit',hour12:true}});
                return `<tr><td style="color:#999;white-space:nowrap">${{ts}} PT</td><td><span class="badge" style="background:#fef3c7;color:#92400e">${{r.user||'Unknown'}}</span></td><td>${{r.request}}</td></tr>`;
            }}).join('');
            frEl.innerHTML = `<table><thead><tr><th>Submitted</th><th>User</th><th>Request</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}

        // Analytics
        const an = await fetch('/api/analytics').then(r => r.json());

        const toolsEl = document.getElementById('tools-content');
        if (!an.top_tools || an.top_tools.length === 0) {{
            toolsEl.innerHTML = '<p class="empty">No data yet.</p>';
        }} else {{
            const rows = an.top_tools.map(t =>
                `<tr><td>${{t.tool}}</td><td><span class="badge">${{t.count}}</span></td></tr>`
            ).join('');
            toolsEl.innerHTML = `<table><thead><tr><th>Tool</th><th>Calls</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}

        const queriesEl = document.getElementById('queries-content');
        if (!an.top_queries || an.top_queries.length === 0) {{
            queriesEl.innerHTML = '<p class="empty">No data yet.</p>';
        }} else {{
            const rows = an.top_queries.map(q =>
                `<tr><td>${{q.query}}</td><td><span class="badge">${{q.count}}</span></td></tr>`
            ).join('');
            queriesEl.innerHTML = `<table><thead><tr><th>Query</th><th>Count</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}

        const recentEl = document.getElementById('recent-content');
        if (!an.recent || an.recent.length === 0) {{
            recentEl.innerHTML = '<p class="empty">No activity yet.</p>';
        }} else {{
            const rows = an.recent.map(r => {{
                const ts = r.timestamp ? new Date(r.timestamp + (r.timestamp.endsWith('Z') ? '' : 'Z')).toLocaleString('en-US', {{timeZone:'America/Los_Angeles',month:'2-digit',day:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit',hour12:true}}) : '';
                const tools = (r.tools||[]).map(t => t.name).join(', ') || '—';
                const dur = r.total_duration_s ? (r.total_duration_s.toFixed(1)+'s') : '';
                const user = r.user || '—';
                return `<tr>
                    <td style="color:#999;white-space:nowrap">${{ts}} PT</td>
                    <td><span class="badge" style="background:#fef3c7;color:#92400e">${{user}}</span></td>
                    <td>${{r.query||''}}</td>
                    <td><span class="badge">${{tools}}</span></td>
                    <td style="color:#999">${{dur}}</td>
                </tr>`;
            }}).join('');
            recentEl.innerHTML = `<table><thead><tr><th>Time</th><th>User</th><th>Query</th><th>Tool</th><th>Duration</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}
    }}
    load();
    </script>
    </body></html>
    """


@app.route("/api/export/tours", methods=["GET"])
def export_tours():
    """Export today's unified schedule (GBS tours + MyStudio appointments) to Excel."""
    try:
        from export_tours import create_unified_excel_file
        from sites.mystudio.appointments import StudentAppointment
        import asyncio

        if os.getenv("TEST_MODE", "").lower() == "true":
            from format_tours import get_sample_sessions
            from datetime import datetime
            gbs_sessions = get_sample_sessions()
            today = datetime.now()
            def appt(id, student, parent, phone, rank, type, hour, minute):
                return StudentAppointment(
                    id=id, student_name=student, student_id="", parent_name=parent,
                    phone=phone, rank=rank, appointment_type=type,
                    start_time=today.replace(hour=hour, minute=minute, second=0, microsecond=0),
                    end_time=today.replace(hour=hour+1, minute=minute, second=0, microsecond=0),
                    duration_minutes=60, instructor_name="", location="", notes=None,
                )
            appointments = [
                appt("001", "Khai Collins",    "Orlando Collins",  "909-555-0101", "White Belt",  "CREATE (CODING)", 15, 0),
                appt("002", "Levi Otubuah",    "Edmund Otubuah",   "909-555-0102", "White Belt",  "CREATE (CODING)", 15, 0),
                appt("003", "Lucia Zamarripa", "Karla Zamarripa",  "909-555-0103", "Yellow Belt", "CREATE (CODING)", 15, 0),
                appt("004", "Musa Khan",       "Rabab Khan",       "909-555-0104", "ScratchJR",   "SCRATCH PLUS",    15, 0),
                appt("005", "Jacob Niu",       "Meng Niu",         "909-555-0105", "ScratchJR",   "SCRATCH PLUS",    15, 0),
                appt("006", "Aiden Park",      "Ji-Yeon Park",     "909-555-0106", "Orange Belt", "CREATE (CODING)", 16, 0),
                appt("007", "Sofia Rivera",    "Maria Rivera",     "909-555-0107", "Green Belt",  "CREATE (CODING)", 16, 0),
                appt("008", "Noah Williams",   "Lisa Williams",    "909-555-0108", "White Belt",  "JR",              17, 0),
                appt("009", "Zoe Martinez",    "Ana Martinez",     "909-555-0109", "White Belt",  "JR",              17, 0),
                appt("010", "Ethan Brown",     "Karen Brown",      "909-555-0110", "Yellow Belt", "JR",              17, 0),
            ]
        else:
            # Use cached schedule from last chat response (avoids double API calls)
            cached_gbs = getattr(chatbot, "_last_gbs_sessions", None)
            cached_appts = getattr(chatbot, "_last_appointments", None)

            if cached_gbs is not None or cached_appts is not None:
                logger.info("Using cached schedule for Excel export")
                gbs_sessions = cached_gbs or []
                appointments = cached_appts or []
            else:
                from sites.lineleader.auth import get_bearer_token
                from sites.lineleader.schedules import get_todays_sessions, enrich_sessions_with_children
                from sites.mystudio.schedules import get_todays_appointments

                bearer_token = asyncio.run(get_bearer_token())
                gbs_sessions = get_todays_sessions(bearer_token)
                enrich_sessions_with_children(bearer_token, gbs_sessions)
                try:
                    appointments = get_todays_appointments()
                except Exception as e:
                    logger.warning("MyStudio appointments failed for export: %s", e)
                    appointments = []

        if not gbs_sessions and not appointments:
            return jsonify({"error": "No schedule found"}), 400

        filepath = asyncio.run(create_unified_excel_file(gbs_sessions, appointments))

        return send_file(
            filepath,
            as_attachment=True,
            download_name=Path(filepath).name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        audit.log_event("error", {"error": f"Export failed: {str(e)}"})
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/camps", methods=["GET"])
def export_camps():
    """Export the last fetched camp data to Excel."""
    try:
        from export_tours import create_camps_excel_file

        if os.getenv("TEST_MODE", "").lower() == "true":
            # Mock data for test mode
            from sites.mystudio.camps import CampRecord, CampKid
            from datetime import datetime as _dt
            mock_camp = CampRecord(
                event_id="999", parent_id="100", parent_title="2026 Summer Camps",
                title="AM CAMP: Test", enrolled=3, capacity=10,
                start_dt=_dt(2026, 7, 7, 8, 30), end_dt=_dt(2026, 7, 7, 11, 30),
                event_show_status="Y",
            )
            mock_kids = [
                CampKid("Alice Smith", "Bob Smith", "555-0001", "bob@test.com", "Active", mock_camp.title, "9"),
                CampKid("Charlie Lee", "David Lee", "555-0002", "dave@test.com", "Active", mock_camp.title, "10"),
            ]
            camps = [mock_camp]
            rosters = {mock_camp.event_id: mock_kids}
        else:
            camp_data = getattr(chatbot, "_last_camp_data", None)
            if not camp_data or not camp_data.get("all_camps"):
                return jsonify({"error": "No camp data found. Ask about camps first, then download."}), 400
            # Use the full unfiltered camp list so the Excel always contains every camp
            camps = camp_data["all_camps"]
            rosters = dict(camp_data.get("rosters", {}))
            # Fetch rosters for any camp that doesn't have one yet
            from sites.mystudio.camps import get_camp_roster as _get_roster
            for camp in camps:
                if camp.event_id not in rosters:
                    try:
                        rosters[camp.event_id] = _get_roster(camp.event_id, camp.parent_id)
                    except Exception:
                        rosters[camp.event_id] = None

        filepath = create_camps_excel_file(camps, rosters)
        return send_file(
            filepath,
            as_attachment=True,
            download_name=Path(filepath).name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        audit.log_event("error", {"error": f"Camp export failed: {str(e)}"})
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    # Bind to 0.0.0.0 to allow connections from other machines on the network
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
