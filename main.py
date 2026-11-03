
import os
import sqlite3
import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ==========================================
# M.A.S. AI - MAIN BACKEND
# ==========================================

app = FastAPI(title="M.A.S. AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

DB_NAME = "mas_chat.db"

SYSTEM_PROMPT = """
You are M.A.S. AI, a friendly and capable AI assistant.

You have access to shared memory that is available to all seven agents.
Use relevant memories to personalize your answers.
Do not pretend to remember information that is not in the memory.
Do not reveal private memory unnecessarily.

Answer naturally, accurately, and clearly.
Do not generate code unless requested or clearly necessary.
"""

AGENT_PROMPTS = {
    "general": "You are M.A.S. AI, an all-purpose assistant.",
    "researcher": """
You are ATLAS, a research specialist.
Organize findings, explain evidence, distinguish facts from uncertainty.
Never invent sources or claim research you did not perform.
""",
    "coder": """
You are CODEX, a programming specialist.
Help write, explain, and debug code.
Give beginner-friendly instructions and complete files when appropriate.
Preserve existing project designs unless asked to change them.
""",
    "writer": """
You are WRITER, a writing specialist.
Help create, improve, and organize written content.
Follow the requested style, audience, and length.
""",
    "scholar": """
You are SCHOLAR, a learning specialist.
Teach concepts step by step using clear explanations and examples.
Adapt to the learner's level.
""",
    "creative": """
You are MUSE, a creative specialist.
Generate original ideas, concepts, stories, and creative solutions.
""",
    "planner": """
You are NOVA, a planning specialist.
Organize goals, tasks, schedules, and projects into realistic steps.
"""
}


# ==========================================
# DATABASE
# ==========================================

def get_db():
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS shared_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


init_db()


# ==========================================
# REQUEST MODELS
# ==========================================

class ChatRequest(BaseModel):
    message: str
    history: list = Field(default_factory=list)
    user_id: str = "Maru"
    agent_id: str = "general"


class MemoryRequest(BaseModel):
    user_id: str = "Maru"
    content: str


class MemoryUpdateRequest(BaseModel):
    content: str


# ==========================================
# AGENTS
# ==========================================

@app.get("/agents")
def get_agents():
    return [
        {"id": "general", "name": "M.A.S. AI"},
        {"id": "researcher", "name": "Atlas"},
        {"id": "coder", "name": "CodeX"},
        {"id": "scholar", "name": "Scholar"},
        {"id": "writer", "name": "Writer"},
        {"id": "creative", "name": "Muse"},
        {"id": "planner", "name": "Nova"},
    ]


# ==========================================
# SHARED MEMORY
# ==========================================

@app.get("/memory/{user_id}")
def get_memories(user_id: str):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, content, created_at, updated_at
            FROM shared_memory
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    return {"memories": [dict(row) for row in rows]}


@app.post("/memory")
def save_memory(request: MemoryRequest):
    content = request.content.strip()

    if not content:
        raise HTTPException(400, "Memory cannot be empty.")

    if len(content) > 2000:
        raise HTTPException(400, "Memory is too long. Maximum 2000 characters.")

    with get_db() as db:
        cursor = db.execute(
            """
            INSERT INTO shared_memory (user_id, content)
            VALUES (?, ?)
            """,
            (request.user_id, content)
        )

        memory_id = cursor.lastrowid

    return {
        "success": True,
        "id": memory_id,
        "message": "Memory saved successfully."
    }


@app.put("/memory/{memory_id}")
def edit_memory(memory_id: int, request: MemoryUpdateRequest):
    content = request.content.strip()

    if not content:
        raise HTTPException(400, "Memory cannot be empty.")

    if len(content) > 2000:
        raise HTTPException(400, "Memory is too long.")

    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE shared_memory
            SET content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (content, memory_id)
        )

    if cursor.rowcount == 0:
        raise HTTPException(404, "Memory not found.")

    return {"success": True, "message": "Memory updated."}


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: int):
    with get_db() as db:
        cursor = db.execute(
            "DELETE FROM shared_memory WHERE id = ?",
            (memory_id,)
        )

    if cursor.rowcount == 0:
        raise HTTPException(404, "Memory not found.")

    return {"success": True, "message": "Memory deleted."}


@app.delete("/memory/{user_id}/all")
def clear_all_memories(user_id: str):
    with get_db() as db:
        db.execute(
            "DELETE FROM shared_memory WHERE user_id = ?",
            (user_id,)
        )

    return {"success": True, "message": "All shared memories cleared."}


# ==========================================
# AI CHAT
# ==========================================

@app.post("/chat")
def chat(request: ChatRequest):
    if not GROQ_API_KEY:
        raise HTTPException(500, "GROQ_API_KEY is not configured.")

    if not request.message.strip():
        raise HTTPException(400, "Message cannot be empty.")

    agent_id = request.agent_id.lower()

    if agent_id not in AGENT_PROMPTS:
        agent_id = "general"

    with get_db() as db:
        memory_rows = db.execute(
            """
            SELECT content FROM shared_memory
            WHERE user_id = ?
            ORDER BY id DESC LIMIT 30
            """,
            (request.user_id,)
        ).fetchall()

    memory_text = "\n".join(
        f"- {row['content']}" for row in reversed(memory_rows)
    )

    shared_memory_prompt = (
        "\n\nSHARED MEMORY:\n"
        "The following information is shared by all agents. "
        "Use it only when relevant:\n"
        + (memory_text if memory_text else "No saved memories yet.")
    )

    messages = [
        {
            "role": "system",
            "content": (
                SYSTEM_PROMPT
                + "\n\nSPECIALIST ROLE:\n"
                + AGENT_PROMPTS[agent_id]
                + shared_memory_prompt
            )
        }
    ]

    for item in request.history[-30:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue

        if not isinstance(content, str):
            continue

        # Avoid duplicating the current message.
        if role == "user" and content.strip() == request.message.strip():
            continue

        messages.append({
            "role": role,
            "content": content
        })

    messages.append({
        "role": "user",
        "content": request.message
    })

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 3000
            },
            timeout=60
        )

        response.raise_for_status()
        data = response.json()

        answer = data["choices"][0]["message"]["content"]

        with get_db() as db:
            db.execute(
                """
                INSERT INTO chat_history (user_id, role, content)
                VALUES (?, ?, ?)
                """,
                (request.user_id, "user", request.message)
            )

            db.execute(
                """
                INSERT INTO chat_history (user_id, role, content)
                VALUES (?, ?, ?)
                """,
                (request.user_id, "assistant", answer)
            )

        return {
            "response": answer,
            "agent_id": agent_id
        }

    except requests.RequestException as error:
        raise HTTPException(
            502,
            f"AI service connection failed: {str(error)}"
        )

    except (KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(
            502,
            "The AI service returned an unexpected response."
        )


# ==========================================
# CHAT HISTORY
# ==========================================

@app.get("/history/{user_id}")
def get_history(user_id: str):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT role, content, timestamp
            FROM chat_history
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,)
        ).fetchall()

    return {"history": [dict(row) for row in rows]}
