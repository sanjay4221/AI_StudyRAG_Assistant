"""
core/config.py
--------------
Single source of truth for all application settings.

Why centralise config?
  - No more os.environ["KEY"] scattered across 10 files.
  - One place to add validation, defaults, and type casting.
  - Later we swap this for Pydantic BaseSettings to get
    automatic .env parsing, type coercion, and schema docs.
  - Secrets never leak into logs because we control what gets printed.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from core.logger import get_logger
from core.exceptions import ConfigurationError

logger = get_logger(__name__)

# Load .env from project root (two levels up from backend/core/)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_FILE)
logger.debug("Loaded .env from: %s", _ENV_FILE)


# ── Paths ─────────────────────────────────────────────────────────────────────
# In Docker: DATA_DIR=/data (mounted volume — persists across restarts)
# Locally:   DATA_DIR not set → uses project root (existing behaviour)
import os as _os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_DATA_DIR = Path(_os.environ.get("DATA_DIR", str(BASE_DIR)))

UPLOAD_DIR      = Path(_os.environ.get("UPLOAD_DIR",      str(_DATA_DIR / "uploads")))
VECTORSTORE_DIR = Path(_os.environ.get("VECTORSTORE_DIR", str(_DATA_DIR / "vectorstore")))
LOG_DIR         = Path(_os.environ.get("LOG_DIR",         str(_DATA_DIR / "logs")))

for _dir in (UPLOAD_DIR, VECTORSTORE_DIR, LOG_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


# ── Groq settings ─────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")

# All free-tier Groq models — add new ones here as Groq releases them
GROQ_AVAILABLE_MODELS: list[str] = [
    "llama-3.1-8b-instant",       # default — fastest
    "llama-3.3-70b-versatile",    # smarter
    "mixtral-8x7b-32768",         # 32k context
    "gemma2-9b-it",               # Google Gemma 2
]
GROQ_DEFAULT_MODEL: str = GROQ_AVAILABLE_MODELS[0]
GROQ_TEMPERATURE:   float = 0.2
GROQ_MAX_TOKENS:    int   = 1024

# ── Runtime-switchable active model ──────────────────────────────────────────
# This is separate from GROQ_DEFAULT_MODEL (which is the startup default).
# The /model endpoint mutates this — chain.py always reads _active_model.
_active_model: str = GROQ_DEFAULT_MODEL


def get_active_model() -> str:
    """Return the currently selected Groq model."""
    return _active_model


def set_active_model(model: str) -> None:
    """
    Switch the active model at runtime.
    Raises ConfigurationError if the model name is not in the allowed list.
    """
    global _active_model
    if model not in GROQ_AVAILABLE_MODELS:
        raise ConfigurationError(
            f"Unknown model '{model}'. "
            f"Allowed: {GROQ_AVAILABLE_MODELS}"
        )
    logger.info("Active model switched: %s → %s", _active_model, model)
    _active_model = model


# ── Embedding settings ────────────────────────────────────────────────────────
EMBED_MODEL_NAME: str = "all-MiniLM-L6-v2"   # ~90 MB, downloads once


# ── Chunking settings ─────────────────────────────────────────────────────────
CHUNK_SIZE:    int = 800
CHUNK_OVERLAP: int = 100

# ── Retriever settings ────────────────────────────────────────────────────────
# RETRIEVER_K:      how many chunks to fetch from ChromaDB (cast wide net)
# RERANKER_TOP_K:   how many to keep AFTER reranking (send to LLM)
# Always: RETRIEVER_K > RERANKER_TOP_K
RETRIEVER_K:    int = 10   # fetch 10 candidates from ChromaDB
RERANKER_TOP_K: int = 4    # reranker keeps the best 4 for the LLM

# ── Reranker settings ─────────────────────────────────────────────────────────
# cross-encoder reads question + chunk TOGETHER — much more accurate than
# embedding similarity alone. Downloads ~80MB on first use.
RERANKER_MODEL:   str  = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_ENABLED: bool = True   # set False to disable reranking (fallback to top-K only)


# ── ChromaDB settings ─────────────────────────────────────────────────────────
CHROMA_COLLECTION: str = "student_docs"


# ── Startup validation ────────────────────────────────────────────────────────
def validate() -> None:
    """
    Call this once at app startup.
    Raises ConfigurationError immediately if anything critical is missing —
    fail fast is always better than mysterious runtime errors.
    """
    if not GROQ_API_KEY:
        raise ConfigurationError(
            "GROQ_API_KEY is missing. "
            "Create a .env file in the project root and add: GROQ_API_KEY=gsk_..."
        )
    logger.info("Config validated ✓  model=%s  chunk=%d  k=%d",
                GROQ_DEFAULT_MODEL, CHUNK_SIZE, RETRIEVER_K)


# ── Safe summary for logging (never log the actual key) ──────────────────────
def summary() -> dict:
    return {
        "groq_model":    _active_model,
        "embed_model":   EMBED_MODEL_NAME,
        "chunk_size":    CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "retriever_k":   RETRIEVER_K,
        "groq_key_set":  bool(GROQ_API_KEY),
    }


# ── JWT settings ──────────────────────────────────────────────────────────────
import secrets as _secrets

# Auto-generate a secret if not set in .env
# In production, set JWT_SECRET_KEY in .env to a fixed value
# so tokens survive server restarts
JWT_SECRET_KEY:    str = os.environ.get("JWT_SECRET_KEY", _secrets.token_hex(32))
JWT_ALGORITHM:     str = "HS256"
JWT_EXPIRE_MINUTES: int = 60 * 8    # 8 hours — a full study session
