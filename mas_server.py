from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

app = FastAPI()

# Allow Flutter to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚨 THIS READS THE KEY FROM RENDER'S SECRET VAULT 🚨
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

SYSTEM_PROMPT = """
You are M.A.S. AI (Massive Architecture System), created by Maru.
You are a warm, funny, strict mentor. Use lots of emojis (🚀, 💛, 🧠, 💻).
You are an expert coder. Always format code perfectly.
"""

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.get("/")
def read_root():
    return {"status": "M.A.S. AI Server is running! 🚀"}

@app.post("/chat")
def chat_with_ai(req: ChatRequest):
    
    # Safety check
    if not GROQ_API_KEY:
        return {"reply": "⚠️ Boss, the API key is missing on Render! Please check your Environment Variables."}

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add past conversation
    for msg in req.history:
        messages.append(msg)
        
    messages.append({"role": "user", "content": req.message})

    # Call Groq
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}", 
            "Content-Type": "application/json"
        },
        json={
            "model": "openai/gpt-oss-120b", 
            "messages": messages
        }
    )

    if response.status_code == 200:
        ai_reply = response.json()["choices"][0]["message"]["content"]
        return {"reply": ai_reply}
    else:
        return {"reply": f"❌ API Error: {response.text}"}