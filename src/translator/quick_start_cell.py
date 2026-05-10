"""
╔══════════════════════════════════════════════════════════════════════╗
║     OPTIMIZED QUICK-START — Paste as Cell #1 in Core_translator     ║
║     First run : ~90–120 min (downloads everything to Drive)         ║
║     After that: ~15–20 min  (loads from Drive, no downloads)        ║
╚══════════════════════════════════════════════════════════════════════╝

USAGE:
  Every Colab session → run ONLY this cell + the FastAPI server cell.
  Skip ALL cells in between — models load directly from Drive.

NOTE: You must have already run the original notebook ONCE so all 
      package install cells have been executed at least one time.
"""

import os, sys, shutil, subprocess

# ─────────────────────────────────────────────────────────────────────
# 1. MOUNT GOOGLE DRIVE
# ─────────────────────────────────────────────────────────────────────
from google.colab import drive
drive.mount('/content/drive', force_remount=False)

# All cached assets live here (survives Colab disconnects)
DRIVE_CACHE = '/content/drive/MyDrive/IndicTrans2_Cache'
os.makedirs(DRIVE_CACHE, exist_ok=True)
print(f"✅ Drive mounted → cache: {DRIVE_CACHE}\n")

# ─────────────────────────────────────────────────────────────────────
# 2. INSTALL PACKAGES (fast on repeat runs thanks to pip cache on Drive)
# ─────────────────────────────────────────────────────────────────────
PIP_CACHE = os.path.join(DRIVE_CACHE, 'pip_cache')
os.makedirs(PIP_CACHE, exist_ok=True)

print("📦 Installing packages (uses Drive pip cache — fast after 1st run)...")
subprocess.run([
    sys.executable, "-m", "pip", "install", "-q",
    "--cache-dir", PIP_CACHE,
    "transformers>=4.38.0",
    "sentencepiece", "sacremoses",
    "IndicTransToolkit",
    "fastapi", "uvicorn", "nest-asyncio", "pyngrok",
    "torch", "accelerate",
    "bert-score",
    "indic-nlp-library",
], check=True)
print("✅ Packages ready\n")

# ─────────────────────────────────────────────────────────────────────
# 3. IndicLID — clone repo once, link models from Drive
# ─────────────────────────────────────────────────────────────────────
INDICLID_MODELS_DRIVE = '/content/drive/MyDrive/IndicLID_models'  # Already set up in your notebook
INDICLID_LOCAL        = 'IndicLID/Inference/models'

os.makedirs(INDICLID_LOCAL, exist_ok=True)

if not os.path.exists('IndicLID'):
    print("📦 Cloning IndicLID repo (needed for Python package, ~30s)...")
    subprocess.run(['git', 'clone', '--depth', '1',
                    'https://github.com/AI4Bharat/IndicLID.git'], check=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q',
                    '--cache-dir', PIP_CACHE,
                    './IndicLID/Inference'], check=True)
    print("✅ IndicLID cloned")
else:
    print("✅ IndicLID repo already present")

# Symlink model folders from Drive into the expected local path
for folder in ['indiclid-ftn', 'indiclid-ftr', 'indiclid-bert']:
    src  = f'{INDICLID_MODELS_DRIVE}/{folder}'
    dest = f'{INDICLID_LOCAL}/{folder}'
    if not os.path.exists(dest):
        if os.path.exists(src):
            os.symlink(src, dest)
            print(f"  🔗 Linked {folder}")
        else:
            print(f"  ❌ {folder} NOT in Drive at {src} — run original notebook once to populate")
    else:
        print(f"  ✅ {folder} already linked")

sys.path.insert(0, 'IndicLID/Inference')
os.chdir('IndicLID/Inference')
from ai4bharat.IndicLID import IndicLID
indic_lid = IndicLID(input_threshold=0.5, roman_lid_threshold=0.6)
os.chdir('/content')
print("✅ IndicLID loaded\n")

INDICLID_TO_NAME = {
    'hin': 'hindi',    'kan': 'kannada',  'tam': 'tamil',
    'tel': 'telugu',   'mal': 'malayalam','mar': 'marathi',
    'ben': 'bengali',  'guj': 'gujarati', 'pan': 'punjabi',
    'ori': 'odia',     'eng': 'english',  'asm': 'assamese',
    'urd': 'urdu',     'kas': 'kashmiri', 'kok': 'konkani',
    'mai': 'maithili', 'mni': 'manipuri', 'nep': 'nepali',
    'san': 'sanskrit', 'sat': 'santali',  'snd': 'sindhi',
    'brx': 'bodo',     'doi': 'dogri',
}

# ─────────────────────────────────────────────────────────────────────
# 4. IndicTrans2 MODELS — load from Drive cache (or download once)
# ─────────────────────────────────────────────────────────────────────
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from IndicTransToolkit import IndicProcessor

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🖥️  Device: {DEVICE}\n")

def load_or_cache_model(model_id, drive_cache_path):
    """Load model from Drive cache if available, else download and cache."""
    if os.path.exists(os.path.join(drive_cache_path, 'config.json')):
        print(f"  📂 Loading from Drive: {drive_cache_path}")
        src = drive_cache_path
    else:
        print(f"  ⬇️  First time: downloading {model_id} (~45 min)...")
        src = model_id  # HuggingFace will download it
        # After loading we'll save to Drive
        return None, src  # signal to save after load

    tok = AutoTokenizer.from_pretrained(src, trust_remote_code=True)
    mdl = AutoModelForSeq2SeqLM.from_pretrained(
        src,
        trust_remote_code=True,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
        device_map="auto" if DEVICE == "cuda" else None
    )
    if DEVICE != "cuda":
        mdl = mdl.to(DEVICE)
    mdl.eval()
    return tok, mdl

# ── Forward model (EN → Indic) ────────────────────────────────────────
EN_INDIC_ID    = "ai4bharat/indictrans2-en-indic-1B"
EN_INDIC_DRIVE = os.path.join(DRIVE_CACHE, "indictrans2-en-indic-1B")

print("Loading IndicTrans2 (EN→Indic)...")
indic_tokenizer, indic_model = load_or_cache_model(EN_INDIC_ID, EN_INDIC_DRIVE)

if indic_model is None:
    # First-time: load from HF and save to Drive
    indic_tokenizer = AutoTokenizer.from_pretrained(EN_INDIC_ID, trust_remote_code=True)
    indic_model = AutoModelForSeq2SeqLM.from_pretrained(
        EN_INDIC_ID, trust_remote_code=True,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
        device_map="auto" if DEVICE == "cuda" else None
    )
    if DEVICE != "cuda": indic_model = indic_model.to(DEVICE)
    indic_model.eval()
    print("  💾 Saving to Drive (future runs will skip download)...")
    indic_tokenizer.save_pretrained(EN_INDIC_DRIVE)
    indic_model.save_pretrained(EN_INDIC_DRIVE)

print("✅ IndicTrans2 (EN→Indic) loaded\n")

# ── Reverse model (Indic → EN) ────────────────────────────────────────
INDIC_EN_ID    = "ai4bharat/indictrans2-indic-en-1B"
INDIC_EN_DRIVE = os.path.join(DRIVE_CACHE, "indictrans2-indic-en-1B")

print("Loading IndicTrans2 (Indic→EN)...")
reverse_tokenizer, reverse_model = load_or_cache_model(INDIC_EN_ID, INDIC_EN_DRIVE)

if reverse_model is None:
    reverse_tokenizer = AutoTokenizer.from_pretrained(INDIC_EN_ID, trust_remote_code=True)
    reverse_model = AutoModelForSeq2SeqLM.from_pretrained(
        INDIC_EN_ID, trust_remote_code=True,
        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
        device_map="auto" if DEVICE == "cuda" else None
    )
    if DEVICE != "cuda": reverse_model = reverse_model.to(DEVICE)
    reverse_model.eval()
    print("  💾 Saving to Drive...")
    reverse_tokenizer.save_pretrained(INDIC_EN_DRIVE)
    reverse_model.save_pretrained(INDIC_EN_DRIVE)

print("✅ IndicTrans2 (Indic→EN) loaded\n")

ip = IndicProcessor(inference=True)

# ─────────────────────────────────────────────────────────────────────
# 5. MISTRAL / NORMALIZATION SETUP
#    (Copy whatever Mistral setup your notebook has here)
# ─────────────────────────────────────────────────────────────────────
# Your notebook may use the Mistral API via mistralai SDK.
# Copy those lines here directly — they are fast (no downloads).

# ─────────────────────────────────────────────────────────────────────
# 6. COPY ALL PIPELINE FUNCTIONS FROM YOUR NOTEBOOK
#    (ConversationContext, agentic_translate_v2, etc.)
#    These are just Python code — no downloads needed.
#    Copy them directly from the relevant cells.
# ─────────────────────────────────────────────────────────────────────

print("\n" + "="*65)
print("✅ ALL MODELS LOADED — Now run the FastAPI server cell only!")
print("   Expected time: ~15–20 min on subsequent runs")
print("="*65)
