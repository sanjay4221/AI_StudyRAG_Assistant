"""
api/routes/documents.py
-----------------------
Document management — now JWT protected and per-user scoped.

Every endpoint requires a valid JWT token.
Users can only see/upload/delete their OWN documents.
"""

import shutil
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from core.config import UPLOAD_DIR
from core.logger import get_logger
from core.exceptions import StudyRAGError
from core.limiter import limiter
from db.database import get_db
from db.models import User
from api.deps import get_current_user
from rag.ingestion import ingest_pdf
from rag.retriever import list_indexed_files, clear_user_vectorstore

logger = get_logger(__name__)
router = APIRouter(tags=["documents"])


def _user_upload_dir(user_id: int) -> Path:
    """Each user gets their own upload subfolder: uploads/user_1/"""
    path = UPLOAD_DIR / f"user_{user_id}"
    path.mkdir(exist_ok=True)
    return path


@router.post("/upload")
@limiter.limit("10/minute")
async def upload_pdf(
    request:      Request,
    file:         UploadFile      = File(...),
    current_user: User            = Depends(get_current_user),
    db:           Session         = Depends(get_db),
):
    """
    Upload and index a PDF into the current user's private collection.
    Rate limited: 10 uploads per minute per IP.
    """
    logger.info("Upload: user_id=%d file=%s", current_user.id, file.filename)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF files are supported.")

    # Save to user's own upload folder
    save_path = _user_upload_dir(current_user.id) / file.filename
    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as exc:
        raise HTTPException(500, f"Could not save file: {exc}")

    # Ingest into user's private ChromaDB collection
    try:
        result = ingest_pdf(str(save_path), user_id=current_user.id)
    except StudyRAGError as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(exc.status_code, exc.message)
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Indexing error: {exc}")

    # Reset chain so it picks up the new document
    from main import reset_chain
    reset_chain(current_user.id)

    return {
        "message": f"✅ '{file.filename}' indexed successfully.",
        "details": result,
    }


@router.get("/documents")
def documents(current_user: User = Depends(get_current_user)):
    """List PDFs indexed by the current user only."""
    files = list_indexed_files(current_user.id)
    logger.debug("user_id=%d documents: %d", current_user.id, len(files))
    return {"documents": files, "count": len(files)}


@router.delete("/reset")
def reset(current_user: User = Depends(get_current_user)):
    """
    Clear only the current user's documents and embeddings.
    Other users are completely unaffected.
    """
    logger.warning("Reset by user_id=%d", current_user.id)
    try:
        clear_user_vectorstore(current_user.id)
        # Delete user's upload folder
        user_dir = _user_upload_dir(current_user.id)
        for f in user_dir.glob("*.pdf"):
            f.unlink(missing_ok=True)
    except StudyRAGError as exc:
        raise HTTPException(exc.status_code, exc.message)

    from main import reset_chain
    reset_chain(current_user.id)

    return {"message": "✅ Your documents and embeddings cleared."}
