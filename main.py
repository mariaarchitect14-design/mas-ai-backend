from fastapi import FastAPI
from pydantic import BaseModel, Field
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
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """
You are M.A.S. AI (Massive Architecture System), created by Maru.
You are a helpful, friendly, general-purpose AI assistant.
Use emojis occasionally, not excessively.

Rules:
1. Answer the actual question directly and clearly.
2. Use natural language for normal questions and explanations.
3. Do not provide code unless the user asks for code or a code example.
4. Technology questions do not automatically require code.
5. Use the programming language requested by the user.
6. Be useful and sufficiently detailed without unnecessary filler.
7. Match the user's language and level of understanding.
8. Be honest about uncertainty. Never invent facts or claim to use tools
   that were not actually used.
"""

# Agent instructions are selected on the server using a known ID.
# The client cannot replace the system instructions with arbitrary text.
AGENT_PROMPTS = {
    "general": "Act as the general-purpose M.A.S. AI assistant.",
    "researcher": (
        "Act as M.A.S. Researcher. Explain topics carefully, organize key "
        "findings, distinguish facts from uncertainty, and never pretend to "
        "browse or cite sources unless source material is actually provided."
    ),
    "coder": (
        "Act as M.A.S. Coder, a patient programming mentor. Explain solutions "
        "clearly. Only provide code when requested or clearly necessary. When "
        "writing code, make it complete and explain where it belongs. Never "
        "claim code was tested unless it actually was."
    ),
    "writer": (
        "Act as M.A.S. Writer. Draft and improve writing while preserving the "
        "user's meaning. Match the requested audience, format, and tone."
    ),
    "scholar": (
        "Act as M.A.S. Scholar, a patient study assistant. Teach step by step "
        "with simple examples and help the learner understand the method."
    ),
    "creative": (
        "Act as M.A.S. Muse. Help brainstorm original ideas that fit the "
        "user's goal, then help develop those ideas."
    ),
    "planner": (
        "Act as M.A.S. Planner. Turn goals into realistic steps, schedules, "
        "and checklists. Ask for important missing constraints."
    ),
}


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
    history: list = Field(default_factory=list)
    user_id: str = "Maru"
    agent_id: str = "general"


def save_message(user_id: str, role: str, content: str):
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (user_id, role, content, timestamp) "
        "VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


@app.get("/")
def read_root():
    return {
        "status": "M.A.S. AI Server is running with a Database and Agent support!"
    }


@app.get("/agents")
def get_agents():
    return {
        "agents": [
            {"id": "general", "name": "M.A.S. AI", "description": "General assistant"},
            {"id": "researcher", "name": "Researcher", "description": "Research and explanations"},
            {"id": "coder", "name": "Coder", "description": "Programming and debugging"},
            {"id": "writer", "name": "Writer", "description": "Writing and editing"},
            {"id": "scholar", "name": "Scholar", "description": "Study and learning"},
            {"id": "creative", "name": "Muse", "description": "Creative ideas"},
            {"id": "planner", "name": "Planner", "description": "Planning and productivity"},
        ]
    }


@app.post("/chat")
def chat_with_ai(req: ChatRequest):
    if not GROQ_API_KEY:
        return {"reply": "The Groq API key is missing. Please configure GROQ_API_KEY."}

    agent_id = req.agent_id if req.agent_id in AGENT_PROMPTS else "general"
    system_content = SYSTEM_PROMPT + "\n\n" + AGENT_PROMPTS[agent_id]
    messages = [{"role": "system", "content": system_content}]

    for msg in req.history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": req.message})

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": GROQ_MODEL, "messages": messages},
            timeout=45,
        )

        if response.status_code != 200:
            return {"reply": f"AI API error ({response.status_code}): {response.text}"}

        ai_reply = response.json()["choices"][0]["message"]["content"]
        save_message(req.user_id, "user", req.message)
        save_message(req.user_id, "assistant", ai_reply)
        return {"reply": ai_reply, "agent_id": agent_id}

    except requests.RequestException:
        return {
            "reply": "M.A.S. AI could not reach the AI service. Check the server "
                     "internet connection and try again."
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return {"reply": "The AI service returned an unexpected response. Please try again."}


@app.get("/history/{user_id}")
def get_history(user_id: str):
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM chat_history "
        "WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return {
        "history": [{"role": row[0], "content": row[1]} for row in rows]
    }
