from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import os
from dotenv import load_dotenv
from openai import OpenAI
import logging

from tools.shipping_tracker import get_shipping_status
from prompts.system_prompt_no_vector import SYSTEM_PROMPT_NO_VECTOR

load_dotenv()

# Configure logging - simplified
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Nutraley AI Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load full menu at startup
logger.info("Loading full product catalog...")
with open('data/products.json', 'r') as f:
    FULL_MENU = json.load(f)
logger.info(f"✅ Loaded {len(FULL_MENU)} products from catalog")

# In-memory conversation storage (use Redis/DB in production)
conversations: Dict[str, List[Dict]] = {}

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str

# OpenAI function/tool definition - only shipping tracker
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_shipping_status",
            "description": "Look up order/shipment status by order ID. Use this when customers ask about their order, delivery status, tracking information, or when they mention an order number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID to look up (format: ORD-XXXX, e.g., ORD-1001)"
                    }
                },
                "required": ["order_id"]
            }
        }
    }
]

def get_conversation_history(session_id: str) -> List[Dict]:
    """Get or initialize conversation history with full menu in system prompt"""
    if session_id not in conversations:
        logger.info(f"🆕 New session: {session_id}")

        # Build system prompt with full catalog
        system_content = SYSTEM_PROMPT_NO_VECTOR + "\n\n" + "="*80 + "\nFULL PRODUCT CATALOG:\n" + "="*80 + "\n\n" + json.dumps(FULL_MENU, indent=2)

        conversations[session_id] = [
            {"role": "system", "content": system_content}
        ]

        logger.info(f"📦 Injected {len(FULL_MENU)} products into system prompt")

    return conversations[session_id]

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"💬 User [{request.session_id}]: {request.message}")

        # Get conversation history (includes full menu in system prompt)
        messages = get_conversation_history(request.session_id)

        # Add user message
        messages.append({"role": "user", "content": request.message})

        # Call OpenAI - single call with full menu already in context
        logger.info(f"🤖 Calling OpenAI API (full menu in context)...")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0
        )

        logger.info(f"📊 Tokens - Prompt: {response.usage.prompt_tokens}, Completion: {response.usage.completion_tokens}, Total: {response.usage.total_tokens}")

        response_message = response.choices[0].message

        # Check if tool calls are needed (shipping status)
        if response_message.tool_calls:
            logger.info(f"🔧 Tool call requested: {response_message.tool_calls[0].function.name}")

            # Save assistant message with tool calls
            assistant_message = {
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in response_message.tool_calls
                ]
            }
            messages.append(assistant_message)

            # Execute tool calls
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                if function_name == "get_shipping_status":
                    order_id = function_args.get('order_id')
                    logger.info(f"   Looking up order: {order_id}")

                    function_response = json.dumps(get_shipping_status(order_id))

                    # Add function response to messages
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response
                    })

            # Get final response after tool execution
            logger.info(f"🤖 Calling OpenAI API for final response...")

            second_response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0
            )

            logger.info(f"📊 Tokens - Prompt: {second_response.usage.prompt_tokens}, Completion: {second_response.usage.completion_tokens}, Total: {second_response.usage.total_tokens}")

            final_message = second_response.choices[0].message.content
        else:
            # Direct response without tools
            logger.info(f"✅ Direct response (no tools needed)")
            final_message = response_message.content

        # Add assistant response to history
        messages.append({"role": "assistant", "content": final_message})

        logger.info(f"✅ Response sent ({len(final_message)} chars)")
        logger.info(f"{'='*60}\n")

        return ChatResponse(
            response=final_message,
            session_id=request.session_id
        )

    except Exception as e:
        logger.error(f"❌ Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Nutraley AI Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #7c3aed 0%, #4c1d95 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }

            .container {
                width: 100%;
                max-width: 900px;
                height: 85vh;
                max-height: 800px;
                background: white;
                border-radius: 24px;
                box-shadow: 0 25px 80px rgba(0,0,0,0.25);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            .header {
                background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
                color: white;
                padding: 28px 32px;
                display: flex;
                align-items: center;
                gap: 16px;
            }

            .header-icon {
                width: 48px;
                height: 48px;
                background: rgba(255,255,255,0.2);
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
            }

            .header-text h1 {
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 4px;
            }

            .header-text p {
                font-size: 13px;
                opacity: 0.9;
                font-weight: 400;
            }

            .messages {
                flex: 1;
                overflow-y: auto;
                padding: 24px;
                display: flex;
                flex-direction: column;
                gap: 16px;
                background: #f9fafb;
            }

            .messages::-webkit-scrollbar {
                width: 6px;
            }

            .messages::-webkit-scrollbar-track {
                background: transparent;
            }

            .messages::-webkit-scrollbar-thumb {
                background: #d1d5db;
                border-radius: 3px;
            }

            .message-wrapper {
                display: flex;
                gap: 12px;
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

            .message-wrapper.user {
                flex-direction: row-reverse;
            }

            .avatar {
                width: 36px;
                height: 36px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 18px;
                flex-shrink: 0;
            }

            .avatar.user {
                background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
            }

            .avatar.assistant {
                background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
            }

            .message {
                max-width: 85%;
                padding: 14px 18px;
                border-radius: 16px;
                word-wrap: break-word;
                line-height: 1.5;
                font-size: 14px;
            }

            .message.user {
                background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                color: white;
                border-bottom-right-radius: 4px;
                box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
            }

            .message.assistant {
                background: white;
                color: #1f2937;
                border: 1px solid #e5e7eb;
                border-bottom-left-radius: 4px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }

            .typing-indicator {
                display: flex;
                gap: 6px;
                padding: 14px 18px;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                max-width: fit-content;
            }

            .typing-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #9ca3af;
                animation: typing 1.4s infinite;
            }

            .typing-dot:nth-child(2) { animation-delay: 0.2s; }
            .typing-dot:nth-child(3) { animation-delay: 0.4s; }

            @keyframes typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-10px); }
            }

            .input-area {
                padding: 20px 24px;
                background: white;
                border-top: 1px solid #e5e7eb;
                display: flex;
                gap: 12px;
            }

            input {
                flex: 1;
                padding: 14px 20px;
                border: 2px solid #e5e7eb;
                border-radius: 12px;
                font-size: 14px;
                outline: none;
                font-family: inherit;
                transition: all 0.2s;
            }

            input:focus {
                border-color: #7c3aed;
                box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.1);
            }

            input::placeholder {
                color: #9ca3af;
            }

            button {
                padding: 14px 28px;
                background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
                color: white;
                border: none;
                border-radius: 12px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                font-family: inherit;
                transition: all 0.2s;
                box-shadow: 0 2px 8px rgba(124, 58, 237, 0.3);
            }

            button:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(124, 58, 237, 0.4);
            }

            button:active {
                transform: translateY(0);
            }

            button:disabled {
                background: #d1d5db;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }

            .quick-prompts {
                padding: 16px 24px;
                background: white;
                border-top: 1px solid #e5e7eb;
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                overflow-x: auto;
            }

            .quick-prompt {
                padding: 8px 16px;
                background: #f3f4f6;
                border: 1px solid #e5e7eb;
                border-radius: 20px;
                font-size: 13px;
                color: #374151;
                cursor: pointer;
                transition: all 0.2s;
                white-space: nowrap;
            }

            .quick-prompt:hover {
                background: #e5e7eb;
                border-color: #d1d5db;
            }

            @media (max-width: 768px) {
                .container {
                    height: 100vh;
                    max-height: none;
                    border-radius: 0;
                }

                .message {
                    max-width: 85%;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-icon">🌿</div>
                <div class="header-text">
                    <h1>Nutraley AI Assistant</h1>
                    <p>Your guide to natural, organic products</p>
                </div>
            </div>

            <div class="quick-prompts" id="quickPrompts">
                <div class="quick-prompt" onclick="useQuickPrompt('What oils do you have?')">🛍️ Browse Oils</div>
                <div class="quick-prompt" onclick="useQuickPrompt('I need something heart-healthy')">❤️ Heart Health</div>
                <div class="quick-prompt" onclick="useQuickPrompt('Best oil for deep frying?')">🍳 Cooking Tips</div>
                <div class="quick-prompt" onclick="useQuickPrompt('Show me gluten-free options')">🌾 Gluten-Free</div>
            </div>

            <div class="messages" id="messages"></div>

            <div class="input-area">
                <input type="text" id="input" placeholder="Ask about products, health benefits, or cooking tips..." />
                <button onclick="sendMessage()" id="sendBtn">Send</button>
            </div>
        </div>

        <script>
            const messagesDiv = document.getElementById('messages');
            const input = document.getElementById('input');
            const sendBtn = document.getElementById('sendBtn');
            const quickPromptsDiv = document.getElementById('quickPrompts');
            const sessionId = 'session_' + Date.now();

            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !sendBtn.disabled) sendMessage();
            });

            function useQuickPrompt(prompt) {
                input.value = prompt;
                sendMessage();
            }

            async function sendMessage() {
                const message = input.value.trim();
                if (!message) return;

                sendBtn.disabled = true;
                addMessage('user', message);
                input.value = '';

                const typingWrapper = document.createElement('div');
                typingWrapper.className = 'message-wrapper assistant';
                typingWrapper.innerHTML = `
                    <div class="avatar assistant">🤖</div>
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                `;
                messagesDiv.appendChild(typingWrapper);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message, session_id: sessionId })
                    });

                    const data = await response.json();
                    typingWrapper.remove();
                    addMessage('assistant', data.response);
                } catch (error) {
                    typingWrapper.remove();
                    addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
                }

                sendBtn.disabled = false;
            }

            function addMessage(role, content) {
                const wrapper = document.createElement('div');
                wrapper.className = `message-wrapper ${role}`;

                const avatar = document.createElement('div');
                avatar.className = `avatar ${role}`;
                avatar.textContent = role === 'user' ? '👤' : '🤖';

                const messageContainer = document.createElement('div');

                const message = document.createElement('div');
                message.className = `message ${role}`;
                message.style.whiteSpace = 'pre-wrap';
                message.textContent = content;

                messageContainer.appendChild(message);
                wrapper.appendChild(avatar);
                wrapper.appendChild(messageContainer);
                messagesDiv.appendChild(wrapper);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }

            // Welcome message
            addMessage('assistant', 'Welcome to Nutraley! I can help you with:\\n\\n• Discovering our natural, organic products\\n• Tracking your order status\\n\\nWhat would you like to know?');
        </script>
    </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "ok", "mode": "no_vector", "products_loaded": len(FULL_MENU)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("application:app", host="0.0.0.0", port=8001, reload=True)
