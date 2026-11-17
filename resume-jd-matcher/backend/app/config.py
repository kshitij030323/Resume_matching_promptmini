"""Central configuration (paths + environment switches)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines); real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BACKEND_DIR / ".env")
DATA_DIR = BACKEND_DIR / "data"
RESUME_DIR = DATA_DIR / "resumes"
JOB_DIR = DATA_DIR / "jobs"
LABELS_PATH = DATA_DIR / "human_rankings.json"
STORAGE_DIR = BACKEND_DIR / "storage"
EXTRACT_CACHE_DIR = STORAGE_DIR / "extracted"
CHROMA_DIR = STORAGE_DIR / "chroma"
REPORTS_DIR = BACKEND_DIR / "reports"
WEB_DIST_DIR = PROJECT_DIR / "web" / "dist"

# --- LLM -----------------------------------------------------------------------------
# auto: Gemini if a Gemini key is configured, else Claude if Anthropic credentials
# exist, else offline. "gemini" / "anthropic" pin one provider.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")                   # Claude model
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")          # Gemini model
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
LLM_SETTINGS_PATH = BACKEND_DIR / "storage" / "llm_settings.json"        # key saved from the UI
EXTRACTION_EFFORT = os.getenv("EXTRACTION_EFFORT", "low")   # structured extraction is easy
CHAIN_EFFORT = os.getenv("CHAIN_EFFORT", "medium")          # gap analysis needs judgement
DISABLE_LLM = os.getenv("DISABLE_LLM", "").lower() in {"1", "true", "yes"}

# --- Embedding models ---------------------------------------------------------------
GLOVE_NAME = "glove-wiki-gigaword-100"
GLOVE_KV_PATH = STORAGE_DIR / f"{GLOVE_NAME}.kv"
MINILM_MODEL = os.getenv("MINILM_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
BGE_MODEL = os.getenv("BGE_MODEL", "BAAI/bge-small-en-v1.5")

for d in (STORAGE_DIR, EXTRACT_CACHE_DIR, CHROMA_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)
