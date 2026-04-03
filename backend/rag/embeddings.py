"""
rag/embeddings.py
-----------------
Embedding model setup — isolated so swapping providers is a one-file change.

Current: HuggingFace MiniLM (local CPU, free, ~90 MB)
Future swap options:
  - OpenAI text-embedding-3-small  (better quality, costs money)
  - Cohere embed-v3                (multilingual)
  - Ollama nomic-embed-text        (local GPU)

Engineering note:
  We cache the model in a module-level variable (_embeddings).
  Loading a sentence-transformer model takes ~2 seconds and allocates
  ~300 MB of RAM — we never want to do that per-request.
"""

from langchain_huggingface import HuggingFaceEmbeddings

from core.config import EMBED_MODEL_NAME
from core.logger import get_logger
from core.exceptions import VectorStoreError

logger = get_logger(__name__)

# Module-level cache — loaded once, reused for the lifetime of the process
_embeddings: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Return the shared embedding model, loading it on first call.

    Thread safety note: FastAPI runs with a single Uvicorn worker by default
    in dev mode, so this is safe. For multi-worker prod deployments we'd use
    a process initializer or a shared embedding service.
    """
    global _embeddings

    if _embeddings is not None:
        return _embeddings

    logger.info("Loading embedding model: %s (first call — this takes a few seconds)", EMBED_MODEL_NAME)
    try:
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Embedding model loaded ✓")
    except Exception as exc:
        logger.error("Failed to load embedding model: %s", exc, exc_info=True)
        raise VectorStoreError(f"Could not load embedding model '{EMBED_MODEL_NAME}': {exc}") from exc

    return _embeddings
