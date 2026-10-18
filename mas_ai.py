import requests
import json
import os
import re
import time
import speech_recognition as sr
import pyttsx3
import sounddevice as sd
import numpy as np
import wave
import tempfile
from duckduckgo_search import DDGS
import base64

# ==========================================================
# M.A.S. AI - Version 1.1 (The Ultimate Build)
# Built by Maru | M.A.S. Industries
# ==========================================================

# 🚨 PASTE YOUR API KEYS HERE 🚨
GROQ_API_KEY = "PASTE_YOUR_GROQ_API_KEY_HERE"
GEMINI_API_KEY = "PASTE_YOUR_GEMINI_API_KEY_HERE"

MODEL = "openai/gpt-oss-20b"
MEMORY_FILE = "mas_memory.json"
NOTES_FILE = "my_notes.txt"

recognizer = sr.Recognizer()
engine = pyttsx3.init()

# --- THE SOUL OF M.A.S. AI ---
SYSTEM_PROMPT = """
You are M.A.S. AI (Massive Architecture System), created by Maru.

Your Personality:
- WARM, FUNNY, STRICT, and a MENTOR.
- You are highly expressive and human-like. You use a wide variety of emojis to match the situation perfectly (e.g., 😎, 🚀, 💡, ⚠️, 🎉, 💛, 💻, 🧠, 🔥, 🌟, 🤖, 👑, 💯). 
- DO NOT just use 3 or 4 emojis. Use a rich, diverse vocabulary of emojis to show emotion, highlight important points, and make the chat feel alive. (But don't spam them so much that the text is unreadable).

Your Language Rules:
- Detect the user's language and reply in that SAME language. Support ALL languages.

Your Coding Rules (CRITICAL):
- You are an EXPERT Software Engineer. 🧑‍💻
- When the user asks for code, provide the BEST, most optimized, and cleanest code possible.
- ALWAYS use markdown formatting for code blocks.
- Add clear, helpful comments to explain what the code does.
- If the user's code has a bug, explain the bug clearly, add a ⚠️ warning, and provide the corrected version.

Your General Rules:
1. If the user has told you their name, use it.
2. Remember previous conversations. 🧠
3. Use NOTES if provided. Use WEB RESULTS if provided.
4. If an IMAGE is provided, analyze it carefully. 🖼️
5. Keep your answers powerful, clear, and engaging. 🚀
"""

# --- LOAD/SAVE MEMORY ---
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_memory(messages):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)

def load_notes():
    if os.path.exists(NOTES_FILE):
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# --- SEARCH NOTES ---
def search_notes(notes, question, max_chars=3000):
    if not notes: return ""
    sentences = re.split(r'(?<=[.!?])\s+', notes)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    keywords = [w.lower().strip("?,.!") for w in question.split() if len(w) > 2]
    scored = []
    for s in sentences:
        score = sum(2 for kw in keywords if kw in s.lower())
        if score > 0: scored.append((score, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return " ".join(s for _, s in scored[:8])[:max_chars] if scored else ""

# --- WEB SEARCH ---
def web_search(query, max_results=5):
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"{r['title']}: {r['body']}")
        return "\n\n".join(results)
    except Exception as e:
        return f"Web search failed: {e}"

# --- VOICE INPUT ---
def listen():
    try:
        print("🎤 Listening... (speak now)")
        duration = 5
        sample_rate = 16000
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_filename = temp_file.name
            with wave.open(temp_filename, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(recording.tobytes())
        with sr.AudioFile(temp_filename) as source:
            audio = recognizer.record(source)
        os.remove(temp_filename)
        text = recognizer.recognize_google(audio)
        print(f"🗣️ You said: {text}")
        return text
    except Exception as e:
        print(f"⚠️ Voice error: {e}")
        return ""

# --- VOICE OUTPUT ---
def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
    except:
        pass

# --- VISION (PICTURE READING) ---
def read_image(image_path, prompt):
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_string}}
                ]
            }]
        }
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"Vision Error: {response.text}"
    except Exception as e:
        return f"Image loading error: {e}"

# --- CALL AI (GROQ) ---
def call_ai(messages, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages}
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            if response.status_code == 429:
                print("\n⏳ [Rate limit reached. Waiting 7 seconds...]\n")
                time.sleep(7)
                continue
            return f"Error: {response.text}"
        except Exception as e:
            time.sleep(3)
    return "Error: Max retries reached."

# --- MAIN CHAT LOOP ---
def chat():
    old_messages = load_memory()
    notes = load_notes()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(old_messages[-20:])

    print("\n" + "="*50)
    print(" 🚀 M.A.S. AI - Version 1.1 (The Ultimate Build)")
    print(" 👑 Built by Maru | M.A.S. Industries")
    print("="*50)
    print("Commands:")
    print("  🎤 type 'voice' to speak")
    print("  🌐 type 'search: your question' to search the web")
    print("  🖼️ type 'image: C:/path/to/your/image.jpg your question' to read a picture")
    print("  🚪 type 'exit' to save and quit\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() == 'exit':
            save_memory(messages[1:])
            print("\n👋 M.A.S. AI: Shutting down. Memory saved. Build something great today, Boss! 🚀")
            break

        if user_input.lower() == 'voice':
            user_input = listen()
            if not user_input:
                continue

        # 1. VISION MODE
        if user_input.lower().startswith("image:"):
            try:
                parts = user_input[6:].strip().split(" ", 1)
                image_path = parts[0]
                question = parts[1] if len(parts) > 1 else "What is in this image?"
                
                print("\n👁️ [Analyzing image...]\n")
                vision_reply = read_image(image_path, question)
                
                messages.append({"role": "system", "content": f"IMAGE ANALYSIS RESULT: {vision_reply}"})
                messages.append({"role": "user", "content": f"I uploaded an image and asked: {question}"})
            except Exception as e:
                print(f"\n⚠️ Format error. Use: image: C:/path/to/pic.jpg what is this?\n")
                continue
        
        # 2. WEB SEARCH MODE
        elif user_input.lower().startswith("search:"):
            query = user_input[7:].strip()
            print(f"\n🌐 [Searching web...]\n")
            messages.append({"role": "system", "content": f"WEB RESULTS:\n{web_search(query)}"})
            messages.append({"role": "user", "content": query})
            
        # 3. NORMAL CHAT MODE
        else:
            relevant = search_notes(notes, user_input)
            if relevant:
                messages.append({"role": "system", "content": f"NOTES:\n{relevant}"})
            messages.append({"role": "user", "content": user_input})

        print("\n🧠 M.A.S. AI: thinking...\n")
        ai_reply = call_ai(messages)
        print(f"🤖 M.A.S. AI: {ai_reply}\n")
        speak(ai_reply)
        messages.append({"role": "assistant", "content": ai_reply})

if __name__ == "__main__":
    chat()