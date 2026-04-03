"""
api/routes/health.py
--------------------
Health check + model switching endpoints.
/health is public — no JWT needed, used by frontend before login.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import GROQ_AVAILABLE_MODELS, get_active_model, set_active_model, summary
from core.exceptions import ConfigurationError
from core.logger import get_logger
from core.limiter import limiter
from db.database import get_db

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.limit("60/minute")
def health(request: Request, db: Session = Depends(get_db)):
    """
    Public health check — no JWT required.
    Returns system status. Doc count is now per-user so we
    report registered user count instead.
    """
    from db.models import User
    user_count = db.query(User).count()
    logger.debug("Health check — registered users: %d", user_count)
    return {
        "status":  "ok",
        "message": "Student RAG Assistant is running 🎓",
        "llm":     f"Groq / {get_active_model()}",
        "embed":   "all-MiniLM-L6-v2",
        "users":   user_count,
        "config":  summary(),
    }


class ModelSwitchRequest(BaseModel):
    model: str


@router.post("/model")
def switch_model(req: ModelSwitchRequest):
    """Switch the active Groq model at runtime — resets all user chains."""
    try:
        set_active_model(req.model)
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    # Reset ALL user chains so they rebuild with the new model
    from main import reset_all_chains
    reset_all_chains()

    logger.info("Model switched to: %s", req.model)
    return {
        "message":      f"✅ Model switched to '{req.model}'",
        "active_model": req.model,
        "available":    GROQ_AVAILABLE_MODELS,
    }


@router.get("/models")
def list_models():
    """List all available Groq models and which one is active."""
    return {
        "active":    get_active_model(),
        "available": GROQ_AVAILABLE_MODELS,
    }
