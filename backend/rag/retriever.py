"""
rag/retriever.py
----------------
Per-user vector store access and retriever construction.

Key change from v1:
  Every function now accepts user_id (int).
  Each user gets their own ChromaDB collection:
    user_1  →  collection "user_1_docs"
    user_2  →  collection "user_2_docs"

Benefits:
  - Student A clearing docs never affects Student B
  - Each student only searches their own PDFs
  - Easy to wipe one user's data without touching others
  - In future: per-user usage limits, storage quotas
"""

import shutil
from langchain_chroma import Chroma
from langchain.schema import BaseRetriever

from core.config import VECTORSTORE_DIR, RETRIEVER_K
from core.logger import get_logger
from core.exceptions import VectorStoreError
from rag.embeddings import get_embeddings

logger = get_logger(__name__)


def _collection_name(user_id: int) -> str:
    """
    Build a unique ChromaDB collection name for a user.
    e.g. user_id=3 → "user_3_docs"

    Rules:
      - Must be unique per user
      - ChromaDB collection names: only letters, numbers, underscores, hyphens
      - Max 63 characters
    """
    return f"user_{user_id}_docs"


def get_vectorstore(user_id: int) -> Chroma:
    """Open (or create) the ChromaDB collection for this specific user."""
    collection = _collection_name(user_id)
    try:
        vs = Chroma(
            collection_name=collection,
            embedding_function=get_embeddings(),
            persist_directory=str(VECTORSTORE_DIR),
        )
        logger.debug("Opened vectorstore for user_id=%d collection=%s", user_id, collection)
        return vs
    except Exception as exc:
        logger.error("Failed to open vectorstore for user_id=%d: %s", user_id, exc, exc_info=True)
        raise VectorStoreError(f"Could not open vector store: {exc}") from exc


def get_retriever(user_id: int) -> BaseRetriever:
    """Build a similarity-search retriever scoped to this user's documents."""
    logger.debug("Building retriever for user_id=%d k=%d", user_id, RETRIEVER_K)
    return get_vectorstore(user_id).as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVER_K},
    )


def list_indexed_files(user_id: int) -> list[str]:
    """Return sorted list of PDF filenames indexed by this user."""
    try:
        data  = get_vectorstore(user_id).get()
        files = {m.get("source_file", "unknown") for m in data["metadatas"] if m}
        logger.debug("user_id=%d indexed files: %s", user_id, files)
        return sorted(files)
    except Exception as exc:
        logger.warning("Could not list files for user_id=%d: %s", user_id, exc)
        return []


def clear_user_vectorstore(user_id: int) -> None:
    """
    Delete only THIS user's collection — other users unaffected.
    Uses ChromaDB's delete_collection() instead of wiping the whole folder.
    """
    collection = _collection_name(user_id)
    logger.warning("Clearing collection for user_id=%d collection=%s", user_id, collection)
    try:
        vs = get_vectorstore(user_id)
        vs.delete_collection()
        logger.info("Collection cleared for user_id=%d ✓", user_id)
    except Exception as exc:
        logger.error("Failed to clear collection for user_id=%d: %s", user_id, exc, exc_info=True)
        raise VectorStoreError(f"Could not clear your document store: {exc}") from exc


def clear_vectorstore() -> None:
    """
    Wipe the entire vectorstore folder — all users.
    Only called by admin-level reset (used during migration/dev).
    """
    logger.warning("Clearing ENTIRE vectorstore at: %s", VECTORSTORE_DIR)
    try:
        if VECTORSTORE_DIR.exists():
            shutil.rmtree(VECTORSTORE_DIR)
            VECTORSTORE_DIR.mkdir(exist_ok=True)
        logger.info("Entire vectorstore cleared ✓")
    except Exception as exc:
        logger.error("Failed to clear vectorstore: %s", exc, exc_info=True)
        raise VectorStoreError(f"Could not clear vectorstore: {exc}") from exc
