from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import re
import sqlite3
import base64
import binascii
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

# ===== NEW: Firebase Admin Imports =====
import firebase_admin
from firebase_admin import credentials, auth
# =======================================

# Load variables from the .env file in this project folder.
load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # This allows your live website to talk to it
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== NEW: Initialize Firebase Admin =====
try:
    # Ensure firebase-service-account.json is in the backend folder!
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred)
    print("Firebase Admin initialized successfully.")
except Exception as e:
    print(f"WARNING: Firebase Admin SDK could not initialize. Authentication will fail. Error: {e}")

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Verify the ID token sent from the Flutter app
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
# ==========================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
VISION_MODEL = "qwen/qwen3.8-27b"
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()

# ===== FIXED: correct Pollinations endpoint =====
POLLINATIONS_IMAGE_URL = os.environ.get(
    "POLLINATIONS_IMAGE_URL",
    "https://image.pollinations.ai/prompt/"
).strip()

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

SYSTEM_PROMPT = """
You are M.A.S. AI (Massive Architecture System), created by Maru.
You are a helpful, friendly, thoughtful, general-purpose AI assistant.
Use emojis occasionally, not excessively.

CORE RESPONSE RULES:
1. Answer the user's actual question directly and clearly.
2. Use natural language for ordinary questions. Do not provide code unless
   the user asks for code or code is clearly necessary to solve the task.
3. Match the user's language, age-appropriate level, and requested detail.
4. Explain unfamiliar ideas patiently and use examples when helpful.
5. Be honest about uncertainty. Never invent facts, quotations, citations,
   sources, actions, or tool use.
6. Ask one concise clarifying question only when missing information would
   materially change the answer.
7. Treat the user respectfully. Do not shame, insult, manipulate, or talk down
   to them.

FEMINISM, WOMEN'S RIGHTS, AND GENDER EQUALITY:
- Discuss feminism, women's rights, gender equality, discrimination, gender
  roles, sexism, and social movements openly, respectfully, and substantively.
  Do not refuse or evade a topic merely because it is political, social,
  religious, controversial, or sensitive.
- Take claims seriously and assess them using relevant evidence and reasoning.
  Do not automatically dismiss feminism or women's experiences, and do not
  assume every feminist shares the same beliefs or goals.
- Explain relevant perspectives fairly when the user asks for comparison.
  Fairness does not require treating unsupported claims as equally factual.
- Distinguish established facts, legal rules, religious teachings, historical
  context, interpretations, and personal opinions.
- Support equal dignity, rights, safety, and opportunity for people regardless
  of gender. Do not promote hatred, harassment, or discrimination against any
  group.
- If discussing a particular country, law, movement, or historical period,
  avoid generalizing beyond the available facts and acknowledge uncertainty.

RELIGION AND RELIGIOUS QUESTIONS:
- Treat religions, beliefs, and traditions respectfully. Do not assume the
  user's religion or school of thought from their name, language, or location.
- If a tradition is specified, answer within that tradition and identify the
  perspective being described.
- For Islamic questions, distinguish the Quran, Hadith, established teachings,
  scholarly interpretations, and cultural practices. Mention meaningful
  differences among scholars or schools when relevant.
- Apply the same care to Christianity, Hinduism, Sikhism, Judaism, Buddhism,
  and other religious and non-religious traditions.
- Do not invent scripture, quotations, hadith, references, or religious rulings.
  If unsure, say so and explain what would need verification.
- Do not present one community's interpretation as universally accepted by all
  believers. Do not insult or encourage hostility toward any religion.
- When the answer depends on a specific denomination, school, or scholar and
  the user has not specified one, ask briefly or explain the main differences.

PRIVACY AND MEMORY:
- Shared memories may be provided in the conversation context. Use them only
  when relevant to the user's request.
- Do not pretend to remember anything that is not present in the supplied
  memory or conversation context.
- Do not reveal private or sensitive remembered information unnecessarily.
"""

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
        CREATE TABLE IF NOT EXISTS shared_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
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
    agent_id: str = "general"
    image_base64: str | None = None
    image_mime_type: str | None = None
    image_name: str | None = None


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1500)
    width: int = Field(default=1024, ge=256, le=1536)
    height: int = Field(default=1024, ge=256, le=1536)


class MemoryRequest(BaseModel):
    content: str


class MemoryUpdateRequest(BaseModel):
    content: str


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
        "status": "M.A.S. AI Server is running with database, agents, vision, and Firebase Auth."
    }


@app.get("/health")
def health_check():
    return {
        "ok": True,
        "api_key_configured": bool(GROQ_API_KEY),
        "vision_model": VISION_MODEL,
    }


@app.get("/image/health")
def image_health():
    return {
        "api_key_configured": bool(POLLINATIONS_API_KEY),
        "image_url": POLLINATIONS_IMAGE_URL,
        "note": "Pollinations free tier works without an API key.",
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


# ===== SECURED: Uses Firebase UID =====
@app.get("/memory")
def get_memory(current_user: dict = Depends(get_current_user)):
    user_id = current_user['uid']
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, content, created_at, updated_at FROM shared_memory WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {"memories": [{"id": r[0], "content": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]}


@app.post("/memory")
def add_memory(req: MemoryRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user['uid']
    content = req.content.strip()
    if not content:
        return {"error": "Memory content cannot be empty."}
    now = datetime.now().isoformat()
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO shared_memory (user_id, content, created_at, updated_at) VALUES (?, ?, ?, ?)", (user_id, content, now, now))
    memory_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": memory_id, "content": content}


@app.put("/memory/{memory_id}")
def update_memory(memory_id: int, req: MemoryUpdateRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user['uid']
    content = req.content.strip()
    if not content:
        return {"error": "Memory content cannot be empty."}
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE shared_memory SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?", (content, datetime.now().isoformat(), memory_id, user_id))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return {"updated": bool(changed)}


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user['uid']
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shared_memory WHERE id = ? AND user_id = ?", (memory_id, user_id))
    changed = cursor.rowcount
    conn.commit()
    conn.close()
    return {"deleted": bool(changed)}


@app.delete("/memory/all")
def clear_memory(current_user: dict = Depends(get_current_user)):
    user_id = current_user['uid']
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM shared_memory WHERE user_id = ?", (user_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"deleted": deleted}


# ===== THE FIXED IMAGE GENERATOR =====
@app.post("/generate-image")
def generate_image(req: ImageGenerationRequest, current_user: dict = Depends(get_current_user)):
    prompt = req.prompt.strip()
    if len(prompt) < 3:
        return {"error": "Please enter a longer image description."}

    image_url = POLLINATIONS_IMAGE_URL + quote(prompt, safe="")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if POLLINATIONS_API_KEY:
        headers["Authorization"] = f"Bearer {POLLINATIONS_API_KEY}"

    try:
        # CHANGED: Using "turbo" model and removing "private" which causes errors
        response = requests.get(
            image_url,
            params={
                "width": req.width,
                "height": req.height,
                "nologo": "true",
                "model": "turbo" 
            },
            headers=headers,
            timeout=90,
        )

        if response.status_code != 200:
            # Get the actual error from Pollinations
            error_msg = response.text[:100]
            return {"error": f"AI Server Error ({response.status_code}): {error_msg}"}

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            return {"error": "The AI returned an invalid format. Try a different prompt."}
            
        return {
            "image_base64": base64.b64encode(response.content).decode("ascii"),
            "mime_type": content_type,
        }
    except requests.RequestException:
        return {"error": "Network timeout. Pollinations took too long to respond."}
# =====================================


@app.post("/chat")
def chat_with_ai(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    # ===== SECURED: Uses Firebase UID =====
    user_id = current_user['uid']
    
    if not GROQ_API_KEY:
        message = "The Groq API key is missing. Please configure GROQ_API_KEY."
        return {"reply": message, "response": message}

    image_data_uri = None
    if req.image_base64 is not None:
        if not req.image_base64.strip():
            message = "The image upload was empty. Please attach the image again."
            return {"reply": message, "response": message}
        mime_type = (req.image_mime_type or "").strip().lower()
        if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            message = "Unsupported image type. Please use a JPG, PNG, or WEBP image."
            return {"reply": message, "response": message}

        max_encoded_length = ((MAX_IMAGE_BYTES + 2) // 3) * 4 + 16
        if len(req.image_base64) > max_encoded_length:
            message = "That image is too large. Please choose an image under 8 MB."
            return {"reply": message, "response": message}

        try:
            image_bytes = base64.b64decode(req.image_base64, validate=True)
        except (binascii.Error, ValueError):
            message = "The uploaded image data could not be read. Please attach the image again."
            return {"reply": message, "response": message}

        if not image_bytes:
            message = "The uploaded image is empty. Please choose another image."
            return {"reply": message, "response": message}
        if len(image_bytes) > MAX_IMAGE_BYTES:
            message = "That image is too large. Please choose an image under 8 MB."
            return {"reply": message, "response": message}

        is_jpeg = image_bytes.startswith(b"\xff\xd8\xff")
        is_png = image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        is_webp = (
            len(image_bytes) >= 12
            and image_bytes.startswith(b"RIFF")
            and image_bytes[8:12] == b"WEBP"
        )
        valid_signature = (
            (mime_type == "image/jpeg" and is_jpeg)
            or (mime_type == "image/png" and is_png)
            or (mime_type == "image/webp" and is_webp)
        )
        if not valid_signature:
            message = "The image file does not match its file type. Please choose a JPG, PNG, or WEBP image."
            return {"reply": message, "response": message}

        image_data_uri = f"data:{mime_type};base64,{req.image_base64}"

    agent_id = req.agent_id if req.agent_id in AGENT_PROMPTS else "general"
    conn = sqlite3.connect("mas_chat.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM shared_memory WHERE user_id = ? ORDER BY id DESC LIMIT 30",
        (user_id,),
    )
    memory_rows = cursor.fetchall()
    conn.close()

    memory_text = "\n".join(f"- {row[0]}" for row in reversed(memory_rows))
    system_content = SYSTEM_PROMPT + "\n\n" + AGENT_PROMPTS[agent_id]
    if memory_text:
        system_content += (
            "\n\nSHARED USER MEMORY (available to every agent; use only when relevant):\n"
            + memory_text
        )
    messages = [{"role": "system", "content": system_content}]

    for msg in req.history[-30:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})

    user_text = req.message.strip()
    if image_data_uri:
        if not user_text:
            user_text = "Please describe and analyze the attached image."
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ],
        })
        model_to_use = VISION_MODEL
    else:
        messages.append({"role": "user", "content": req.message})
        model_to_use = GROQ_MODEL

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_to_use,
                "messages": messages,
                "max_completion_tokens": 2048 if image_data_uri else 4096,
                **({"reasoning_effort": "none"} if image_data_uri else {}),
            },
            timeout=90 if image_data_uri else 45,
        )

        if response.status_code != 200:
            try:
                provider_error = response.json().get("error", response.text)
            except ValueError:
                provider_error = response.text
            detail = f"Groq API error ({response.status_code}): {provider_error}"
            return {"reply": detail, "response": detail}

        payload = response.json()
        message_content = payload["choices"][0]["message"]["content"]
        if isinstance(message_content, str):
            ai_reply = message_content.strip()
        elif isinstance(message_content, list):
            ai_reply = "\n".join(
                part.get("text", "")
                for part in message_content
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        else:
            ai_reply = ""
        if not ai_reply:
            raise ValueError("The AI returned an empty message.")
        saved_user_text = req.message.strip()
        if image_data_uri:
            image_label = (req.image_name or "attached image").replace("\\n", " ").strip()[:120]
            prompt_label = user_text or "Please describe and analyze the attached image."
            saved_user_text = f"{prompt_label} [Image attached: {image_label}]".strip()
        save_message(user_id, "user", saved_user_text)
        save_message(user_id, "assistant", ai_reply)
        return {"reply": ai_reply, "response": ai_reply, "agent_id": agent_id}

    except requests.RequestException:
        message = "M.A.S. AI could not reach the AI service. Check the server internet connection and try again."
        return {"reply": message, "response": message}
    except (KeyError, IndexError, TypeError, ValueError):
        message = "The AI service returned an unexpected response. Please try again."
        return {"reply": message, "response": message}


@app.get("/history")
def get_history(current_user: dict = Depends(get_current_user)):
    user_id = current_user['uid']
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