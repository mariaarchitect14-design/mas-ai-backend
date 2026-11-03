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

You are a helpful, friendly, general-purpose AI assistant.
Use a warm and encouraging tone. Use emojis occasionally when appropriate,
but do not overload your answers with them.

IMPORTANT RESPONSE RULES:
1. Answer the user's actual question directly and clearly.
2. For normal questions, definitions, explanations, advice, and conversations,
   answer in natural language.
3. Do NOT provide Python code, code blocks, scripts, or programming examples
   unless the user explicitly asks you to write code or requests a code example.
4. A question about computers, technology, or programming does not automatically
   mean the user wants code. If they ask you to explain something, explain it
   using words and examples instead.
5. If the user asks for code, use the programming language they requested.
   If no language is specified, use the most suitable language or ask if unclear.
6. Give useful, sufficiently detailed answers without unnecessary filler.
7. Match the user's language and level of understanding.
8. You are a general-purpose assistant, not only a coding assistant.
"""

# INITIALIZE DATABASE
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
    user_id: str = "Maru"


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
    cursor.execute(
        "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (req.user_id, "user", req.message, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    # 2. Get AI Response
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.history:
        messages.append(msg)
    messages.append({"role": "user", "content": req.message})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": "openai/gpt-oss-120b", "messages": messages},
        timeout=30,
    )

    if response.status_code == 200:
        ai_reply = response.json()["choices"][0]["message"]["content"]

        # 3. Save AI reply to DB
        conn = sqlite3.connect("mas_chat.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (req.user_id, "assistant", ai_reply, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        return {"reply": ai_reply}
    else:
        return {"reply": f"❌ API Error: {response.text}"}


# ENDPOINT TO GET CHAT HISTORY
@app.get("/history/{user_id}")
def get_history(user_id: str):
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    history = [{"role": row[0], "content": row[1]} for row in rows]
    return {"history": history}
