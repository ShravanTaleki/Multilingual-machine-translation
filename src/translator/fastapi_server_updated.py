"""
Context-Aware FastAPI Translation Server
=========================================
INSTRUCTIONS: Copy-paste this entire code into the LAST code cell of
Core_translator.ipynb (replacing the existing FastAPI cell) and run it.

This version accepts conversation history from the Spring Boot backend
and replays it into ConversationContext before translating, enabling
context-aware translation (pronoun resolution, follow-ups, etc.).
"""

!pip install -q fastapi uvicorn nest-asyncio pyngrok

import nest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from pyngrok import ngrok
import uvicorn
import threading
from typing import List, Optional

nest_asyncio.apply()

app = FastAPI()

class HistoryEntry(BaseModel):
    speaker: str
    text: str

class TranslateRequest(BaseModel):
    text: str
    target_language: str
    history: Optional[List[HistoryEntry]] = []

@app.post("/translate")
def translate(req: TranslateRequest):
    try:
        # Build context from conversation history
        ctx = ConversationContext(max_history=5)
        if req.history:
            for entry in req.history:
                ctx.add(speaker=entry.speaker, text=entry.text)
        result = agentic_translate_v2(
            user_text=req.text,
            target_language=req.target_language,
            context=ctx,
            speaker="User"
        )
        return {"translation": result["translation"]}
    except Exception as e:
        return {"translation": req.text, "error": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}

# Start ngrok tunnel
public_url = ngrok.connect(8000)
url = public_url.public_url
print(f"\n✅ Public URL: {url}")
print(f"   Use this in application.properties: translator.api.url={url}\n")

# Start server
def run():
    uvicorn.run(app, host="0.0.0.0", port=8000)

thread = threading.Thread(target=run, daemon=True)
thread.start()
