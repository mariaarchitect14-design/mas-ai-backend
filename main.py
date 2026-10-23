from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚨 MAKE SURE BOTH KEYS ARE SET IN FASTAPI CLOUD DASHBOARD
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

SYSTEM_PROMPT = """
You are M.A.S. AI (Massive Architecture System), created by Maru.
You are a warm, funny, strict mentor. Use lots of emojis (🚀, 💛, 🧠, 💻).
You are an expert coder. Always format code perfectly.
"""

# 🚨 TWO DIFFERENT REQUESTS
class ChatRequest(BaseModel):
    message: str
    history: list = []

class VisionRequest(BaseModel):
    prompt: str
    image_base64: str

@app.get("/")
def read_root():
    return {"status": "M.A.S. AI Server is running! 🚀"}

# 🚨 ENDPOINT 1: CHAT
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
        json={"model": "openai/gpt-oss-120b", "messages": messages}
    )

    if response.status_code == 200:
        return {"reply": response.json()["choices"][0]["message"]["content"]}
    else:
        return {"reply": f"❌ API Error: {response.text}"}

# 🚨 ENDPOINT 2: VISION (THE NEW ONE)
@app.post("/vision")
def analyze_image(req: VisionRequest):
    if not GEMINI_API_KEY:
        return {"reply": "⚠️ Boss, the Gemini API key is missing!"}
    if not GROQ_API_KEY:
        return {"reply": "⚠️ Boss, the Groq API key is missing!"}

    try:
        # Send image to Gemini to read it
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [
                    {"text": req.prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": req.image_base64}}
                ]
            }]
        }
        vision_response = requests.post(url, headers=headers, json=payload)
        
        if vision_response.status_code != 200:
            return {"reply": f"Gemini Vision Error: {vision_response.text}"}

        image_analysis = vision_response.json()['candidates'][0]['content']['parts'][0]['text']

        # Send Gemini's description to Groq for the M.A.S. AI personality
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"I uploaded an image and asked: '{req.prompt}'. Here is what the image contains: {image_analysis}. Please respond to me based on this."}
        ]

        groq_response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "openai/gpt-oss-120b", "messages": messages}
        )

        if groq_response.status_code == 200:
            return {"reply": groq_response.json()["choices"][0]["message"]["content"]}
        else:
            return {"reply": f"Groq Error: {groq_response.text}"}

    except Exception as e:
        return {"reply": f"Server Error: {e}"}