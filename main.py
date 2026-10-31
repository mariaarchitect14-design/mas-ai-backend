from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import sqlite3
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

SYSTEM_PROMPT = """
You are M.A.S. AI (Massive Architecture System), created by Maru.
You are a warm, funny, strict mentor. Use lots of emojis (🚀, 💛, 🧠, 💻).
You are an expert coder. Always format code perfectly.
"""

# 🚨 INITIALIZE DATABASE 🚨
def init_db():
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

class ChatRequest(BaseModel):
    message: str
    history: list = []
    user_id: str = "Maru" # Default user

@app.get("/")
def read_root():
    return {"status": "M.A.S. AI Server is running with a Database! 🚀"}

@app.post("/chat")
def chat_with_ai(req: ChatRequest):
    if not GROQ_API_KEY:
        return {"reply": "⚠️ Boss, the Groq API key is missing!"}

    # 1. Save user message to DB
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                   (req.user_id, "user", req.message, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    # 2. Get AI Response
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.history:
        messages.append(msg)
    messages.append({"role": "user", "content": req.message})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "openai/gpt-oss-120b", "messages": messages},
        timeout=30
    )

    if response.status_code == 200:
        ai_reply = response.json()["choices"][0]["message"]["content"]
        
        # 3. Save AI reply to DB
        conn = sqlite3.connect("mas_chat.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                       (req.user_id, "assistant", ai_reply, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        return {"reply": ai_reply}
    else:
        return {"reply": f"❌ API Error: {response.text}"}

# 🚨 NEW ENDPOINT TO GET CHAT HISTORY 🚨
@app.get("/history/{user_id}")
def get_history(user_id: str):
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    history = [{"role": row[0], "content": row[1]} for row in rows]
    return {"history": history}