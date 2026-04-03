"""
rag/ingestion.py
----------------
PDF ingestion pipeline: Load → Split → Embed → Store.
Now scoped per user — each PDF goes into user_{id}_docs collection.
"""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from core.config import CHUNK_SIZE, CHUNK_OVERLAP, UPLOAD_DIR
from core.logger import get_logger
from core.exceptions import IngestionError, UnsupportedFileError
from rag.retriever import get_vectorstore

logger = get_logger(__name__)


def _validate_file(filepath: str) -> Path:
    """Check the file exists, is readable, and is a PDF."""
    path = Path(filepath)
    if not path.exists():
        raise IngestionError(f"File not found: {filepath}")
    if path.suffix.lower() != ".pdf":
        raise UnsupportedFileError(
            f"Unsupported file type '{path.suffix}'. Only PDF files are accepted."
        )
    if path.stat().st_size == 0:
        raise IngestionError(f"File is empty: {path.name}")
    return path


def _load_pdf(path: Path) -> list[Document]:
    """Load PDF pages using PyPDFLoader."""
    logger.info("Loading PDF: %s", path.name)
    try:
        loader = PyPDFLoader(str(path))
        pages  = loader.load()
    except Exception as exc:
        logger.error("PyPDFLoader failed for '%s': %s", path.name, exc, exc_info=True)
        raise IngestionError(
            f"Could not read '{path.name}'. The file may be corrupted or scanned."
        ) from exc

    if not pages:
        raise IngestionError(f"'{path.name}' has no extractable text.")

    logger.info("Loaded %d pages from '%s'", len(pages), path.name)
    return pages


def _split_documents(pages: list[Document], filename: str) -> list[Document]:
    """Split pages into overlapping chunks and tag with source metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", "!", "?", " ", ""],
    )
    chunks = splitter.split_documents(pages)
    for chunk in chunks:
        chunk.metadata["source_file"] = filename
    logger.info("Split into %d chunks", len(chunks))
    return chunks


def _embed_and_store(chunks: list[Document], filename: str, user_id: int) -> None:
    """Embed chunks and persist to THIS USER's ChromaDB collection."""
    logger.info("Storing %d chunks for user_id=%d file='%s'", len(chunks), user_id, filename)
    try:
        vs = get_vectorstore(user_id)   # ← user-scoped collection
        vs.add_documents(chunks)
        logger.info("Stored embeddings for user_id=%d file='%s' ✓", user_id, filename)
    except Exception as exc:
        logger.error("Failed to store embeddings: %s", exc, exc_info=True)
        raise IngestionError(f"Embedding/storage failed for '{filename}': {exc}") from exc


def ingest_pdf(filepath: str, user_id: int) -> dict:
    """
    Full ingestion pipeline for one PDF.
    NOW REQUIRES user_id — stores into user's private collection.
    Returns: {filename, pages, chunks}
    """
    path = _validate_file(filepath)
    logger.info("=== Ingestion start: user_id=%d file=%s ===", user_id, path.name)

    pages  = _load_pdf(path)
    chunks = _split_documents(pages, path.name)
    _embed_and_store(chunks, path.name, user_id)

    result = {"filename": path.name, "pages": len(pages), "chunks": len(chunks)}
    logger.info("=== Ingestion complete: %s ===", result)
    return result
