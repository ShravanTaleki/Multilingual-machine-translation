import os
import sys
import subprocess
import time
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import torch
import re
from collections import deque
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# 1. Ensure IndicTransToolkit is patched for Transformers 4.40+
import site
try:
    import transformers.tokenization_utils
    import transformers.tokenization_utils_base
    transformers.tokenization_utils.PreTrainedTokenizerBase = transformers.tokenization_utils_base.PreTrainedTokenizerBase
except:
    pass

from IndicTransToolkit import IndicProcessor
from mistralai import Mistral

app = FastAPI()

# Configuration
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Starting Local Translation Server on: {DEVICE}")

# Initialize Mistral Client
MISTRAL_API_KEY = "4z6ODhUVWjulnakUUfbwCHkswHpyUjNY"
mistral_client = Mistral(api_key=MISTRAL_API_KEY)

# Models Base Path
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# 2. Setup IndicLID automatically
INDICLID_REPO = os.path.join(MODELS_DIR, "IndicLID")
if not os.path.exists(INDICLID_REPO):
    print("Cloning IndicLID repo locally...")
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/AI4Bharat/IndicLID.git", INDICLID_REPO], check=True)

sys.path.insert(0, os.path.join(INDICLID_REPO, 'Inference'))
try:
    from ai4bharat.IndicLID import IndicLID
    os.chdir(os.path.join(INDICLID_REPO, 'Inference'))
    indic_lid = IndicLID(input_threshold=0.5, roman_lid_threshold=0.6)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("IndicLID loaded")
except Exception as e:
    print(f"Could not load IndicLID (Requires downloading model binaries). Will use fallback detection: {e}")
    indic_lid = None
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 3. Load IndicTrans2 Models
print("Loading IndicTrans2 EN->Indic (1B parameters)...")
EN_INDIC_ID = "ai4bharat/indictrans2-en-indic-1B"
indic_tokenizer = AutoTokenizer.from_pretrained(EN_INDIC_ID, trust_remote_code=True, cache_dir=MODELS_DIR)
indic_model = AutoModelForSeq2SeqLM.from_pretrained(
    EN_INDIC_ID, trust_remote_code=True, cache_dir=MODELS_DIR,
    torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
    device_map="auto" if DEVICE == "cuda" else None
)
if DEVICE != "cuda": indic_model = indic_model.to(DEVICE)
indic_model.eval()

print("Loading IndicTrans2 Indic->EN (1B parameters)...")
INDIC_EN_ID = "ai4bharat/indictrans2-indic-en-1B"
reverse_tokenizer = AutoTokenizer.from_pretrained(INDIC_EN_ID, trust_remote_code=True, cache_dir=MODELS_DIR)
reverse_model = AutoModelForSeq2SeqLM.from_pretrained(
    INDIC_EN_ID, trust_remote_code=True, cache_dir=MODELS_DIR,
    torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
    device_map="auto" if DEVICE == "cuda" else None
)
if DEVICE != "cuda": reverse_model = reverse_model.to(DEVICE)
reverse_model.eval()

ip = IndicProcessor(inference=True)
print("All Translation Models Loaded!")

# Languages Map
LANG_CODE = {
    "hindi": "hin_Deva", "kannada": "kan_Knda", "tamil": "tam_Taml",
    "telugu": "tel_Telu", "malayalam": "mal_Mlym", "marathi": "mar_Deva",
    "bengali": "ben_Beng", "gujarati": "guj_Gujr", "punjabi": "pan_Guru",
    "odia": "ory_Orya", "english": "eng_Latn"
}

# 4. Context Logic
class ConversationContext:
    def __init__(self, max_history=5):
        self.history = deque(maxlen=max_history)
    def add(self, speaker, text):
        self.history.append({"speaker": speaker, "text": text})
    def format_for_prompt(self):
        return "\n".join([f"[{e['speaker']}]: {e['text']}" for e in self.history]) if self.history else "(No history)"
    def __len__(self): return len(self.history)

def normalize_with_context(current_message, context, speaker="User", detected_language="english"):
    if not mistral_client: return current_message
    if len(current_message.strip().split()) <= 2: return current_message
    
    sys_prompt = "Rewrite ONLY the CURRENT MESSAGE into clear, grammatical English. Expand slang. Use conversation history to resolve pronouns."
    user_prompt = f"HISTORY:\n{context.format_for_prompt()}\n\nCURRENT ({speaker}):\n{current_message}"
    
    try:
        res = mistral_client.chat.complete(
            model="open-mistral-nemo",
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.0, max_tokens=200
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        print(f"Mistral Error: {e}")
        return current_message

# Translation Logic
def translate_indic_to_english(sentences, src_lang="hin_Deva"):
    batch = ip.preprocess_batch(sentences, src_lang=src_lang, tgt_lang="eng_Latn", visualize=False)
    inputs = reverse_tokenizer(batch, truncation=True, padding="longest", max_length=256, return_tensors="pt").to(DEVICE)
    with torch.inference_mode():
        generated = reverse_model.generate(**inputs, use_cache=True, max_length=256, num_beams=5, num_return_sequences=1)
    decoded = reverse_tokenizer.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return ip.postprocess_batch(decoded, lang="eng_Latn")

def translate_english_to_indic(sentences, tgt_lang="hin_Deva"):
    batch = ip.preprocess_batch(sentences, src_lang="eng_Latn", tgt_lang=tgt_lang, visualize=False)
    inputs = indic_tokenizer(batch, truncation=True, padding="longest", max_length=256, return_tensors="pt").to(DEVICE)
    with torch.inference_mode():
        generated = indic_model.generate(**inputs, use_cache=True, max_length=256, num_beams=5, num_return_sequences=1)
    decoded = indic_tokenizer.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return ip.postprocess_batch(decoded, lang=tgt_lang)

def detect_language(text):
    # Basic fallback if IndicLID isn't setup with binaries
    if re.search(r'[\u0900-\u097F]', text): return "hindi", "hin_Deva", False # Devanagari
    if re.search(r'[\u0C80-\u0CFF]', text): return "kannada", "kan_Knda", False # Kannada
    if re.search(r'[\u0B80-\u0BFF]', text): return "tamil", "tam_Taml", False # Tamil
    if re.search(r'[\u0C00-\u0C7F]', text): return "telugu", "tel_Telu", False # Telugu
    if re.search(r'[\u0D00-\u0D7F]', text): return "malayalam", "mal_Mlym", False # Malayalam
    if re.search(r'[\u0980-\u09FF]', text): return "bengali", "ben_Beng", False # Bengali
    return "english", "eng_Latn", True # Fallback

# API Definition
class HistoryEntry(BaseModel):
    speaker: str
    text: str

class TranslateRequest(BaseModel):
    text: str
    target_language: str
    history: list[HistoryEntry] = []

@app.post("/translate")
def translate_endpoint(req: TranslateRequest):
    try:
        ctx = ConversationContext(max_history=5)
        for entry in req.history: ctx.add(entry.speaker, entry.text)
        
        target_language = req.target_language.lower()
        tgt_code = LANG_CODE.get(target_language, "eng_Latn")
        
        # 1. Detect
        lang, lang_code, is_romanized = detect_language(req.text)
        
        # 2. Normalize
        normalized = req.text
        if is_romanized or target_language != "english":
            normalized = normalize_with_context(req.text, ctx, speaker="User", detected_language=lang)
            print(f"[{lang.upper()} -> {target_language.upper()}] Normalizing: '{req.text}' -> '{normalized}'")
            
        # 3. Translate
        if target_language == "english":
            if lang != "english":
                final_translation = translate_indic_to_english([normalized], src_lang=lang_code)[0]
            else:
                final_translation = normalized
        else:
            if lang != "english" and not is_romanized and lang != target_language:
                # Pivot
                eng_pivot = translate_indic_to_english([normalized], src_lang=lang_code)[0]
                final_translation = translate_english_to_indic([eng_pivot], tgt_lang=tgt_code)[0]
            else:
                # Direct
                final_translation = translate_english_to_indic([normalized], tgt_lang=tgt_code)[0]
                
        return {"translation": final_translation}
    except Exception as e:
        print(f"Translation Error: {e}")
        return {"translation": req.text, "error": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
