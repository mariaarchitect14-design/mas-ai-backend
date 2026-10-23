from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

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

class ChatRequest(BaseModel):
    message: str
    history: list = []

class VisionRequest(BaseModel):
    prompt: str
    image_base64: str

@app.get("/")
def read_root():
    return {"status": "M.A.S. AI Server is running! 🚀"}

@app.post("/chat")
def chat_with_ai(req: ChatRequest):
    if not GROQ_API_KEY:
        return {"reply": "⚠️ Boss, the Groq API key is missing!"}

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
        return {"reply": response.json()["choices"][0]["message"]["content"]}
    else:
        return {"reply": f"❌ API Error: {response.text}"}

@app.post("/vision")
def analyze_image(req: VisionRequest):
    if not GROQ_API_KEY:
        return {"reply": "⚠️ Boss, the Groq API key is missing!"}

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        image_url = f"data:image/jpeg;base64,{req.image_base64}"

        payload = {
            "model": "qwen/qwen3.8-27b", # 🚨 NEW WORKING MODEL
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": req.prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        }

        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            return {"reply": response.json()["choices"][0]["message"]["content"]}
        else:
            return {"reply": f"Groq Vision Error: {response.text}"}

    except Exception as e:
        return {"reply": f"Server Error: {e}"}