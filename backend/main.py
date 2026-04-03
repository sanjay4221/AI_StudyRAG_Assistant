"""
main.py — FastAPI entry point (v4 — Per-user docs + Streaming)
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import core.config as config
from core.logger import get_logger
from core.exceptions import StudyRAGError
from core.limiter import limiter
from db.database import init_db
from rag.chain import build_qa_chain, ConversationalRetrievalChain
from api.routes import health, documents, chat, auth, admin, tools

logger = get_logger(__name__)

config.validate()
init_db()

app = FastAPI(
    title="Student RAG Assistant",
    version="4.0.0",
    description="Per-user docs + Streaming + Auth + History + Rate Limiting",
)

# ── Rate limiter middleware ────────────────────────────────────────────────────
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handlers ─────────────────────────────────────────────────
@app.exception_handler(StudyRAGError)
async def studyrag_exception_handler(request: Request, exc: StudyRAGError):
    logger.error("StudyRAGError %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_type": exc.__class__.__name__},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.critical("Unhandled exception %s %s", request.method, request.url.path, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})


# ── Per-user QA chain cache ────────────────────────────────────────────────────
# Dict mapping user_id → chain instance
# Each user gets their own chain with their own retriever
_chains: dict[int, ConversationalRetrievalChain] = {}


def get_chain(user_id: int) -> ConversationalRetrievalChain:
    """Return chain for this user, building it lazily on first call."""
    if user_id not in _chains:
        logger.info("Building QA chain for user_id=%d", user_id)
        _chains[user_id] = build_qa_chain(user_id)
    return _chains[user_id]


def reset_chain(user_id: int) -> None:
    """Discard chain for this user — rebuilt on next request."""
    if user_id in _chains:
        del _chains[user_id]
    logger.info("Chain reset for user_id=%d", user_id)


def reset_all_chains() -> None:
    """Discard ALL user chains — used when switching models."""
    _chains.clear()
    logger.info("All chains reset (model switch)")


# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(tools.router)

# ── Frontend ──────────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_login():
        return FileResponse(str(FRONTEND_DIR / "login.html"))

    @app.get("/chat")
    def serve_chat():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/admin")
    def serve_admin():
        return FileResponse(str(FRONTEND_DIR / "admin.html"))

    @app.get("/privacy")
    def serve_privacy():
        return FileResponse(str(FRONTEND_DIR / "privacy.html"))

    @app.get("/terms")
    def serve_terms():
        return FileResponse(str(FRONTEND_DIR / "terms.html"))

logger.info("Application startup complete. Visit http://127.0.0.1:8000")
