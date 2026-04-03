"""
api/routes/tools.py
-------------------
Study tool endpoints — all JWT protected.

POST /tools/quiz      → generate MCQ quiz from user's documents
POST /tools/summarise → generate structured document summary
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.logger import get_logger
from core.exceptions import LLMError, StudyRAGError
from core.limiter import limiter
from fastapi import Request
from db.database import get_db
from db.models import User
from api.deps import get_current_user
from rag.retriever import list_indexed_files
from rag.tools import generate_quiz, summarise_documents

logger = get_logger(__name__)
router = APIRouter(prefix="/tools", tags=["tools"])


class QuizRequest(BaseModel):
    num_questions: int = 10
    difficulty:    str = "medium"   # easy / medium / hard


@router.post("/quiz")
@limiter.limit("10/minute")
def quiz(
    request:      Request,
    req:          QuizRequest       = QuizRequest(),
    current_user: User              = Depends(get_current_user),
    db:           Session           = Depends(get_db),
):
    """Generate an MCQ quiz from the user's indexed documents."""
    if not list_indexed_files(current_user.id):
        raise HTTPException(400, "No documents indexed. Please upload a PDF first.")

    if req.num_questions < 3 or req.num_questions > 20:
        raise HTTPException(400, "Number of questions must be between 3 and 20.")

    if req.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(400, "Difficulty must be: easy, medium, or hard.")

    try:
        result = generate_quiz(
            user_id=current_user.id,
            num_questions=req.num_questions,
            difficulty=req.difficulty,
        )
    except LLMError as exc:
        raise HTTPException(502, exc.message)
    except Exception as exc:
        logger.error("Quiz generation failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Quiz generation failed: {exc}")

    return result


@router.post("/summarise")
@limiter.limit("10/minute")
def summarise(
    request:      Request,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Generate a structured study summary of the user's indexed documents."""
    if not list_indexed_files(current_user.id):
        raise HTTPException(400, "No documents indexed. Please upload a PDF first.")

    try:
        result = summarise_documents(user_id=current_user.id)
    except LLMError as exc:
        raise HTTPException(502, exc.message)
    except Exception as exc:
        logger.error("Summarise failed: %s", exc, exc_info=True)
        raise HTTPException(500, f"Summarise failed: {exc}")

    return result
