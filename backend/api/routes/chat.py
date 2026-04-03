"""
api/routes/chat.py
------------------
Chat endpoint — JWT protected, per-user docs, streaming responses.

Key endpoints:
  POST /chat              → streaming SSE response (new messages)
  GET  /sessions          → list user's sessions
  GET  /sessions/{id}     → load past session messages
  DELETE /sessions/{id}   → delete a session
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from core.logger import get_logger
from core.exceptions import StudyRAGError
from core.limiter import limiter
from db.database import get_db
from db.models import User
from db.crud import (
    create_chat_session,
    get_user_sessions,
    get_session_by_id,
    get_session_messages,
    add_message,
    update_session_title,
    touch_session,
    delete_session,
)
from rag.retriever import list_indexed_files
from rag.chain import stream_answer
from api.deps import get_current_user

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])


class QuestionRequest(BaseModel):
    question:   str
    session_id: int | None = None

    @field_validator("question")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Question cannot be empty.")
        if len(v) > 2000:
            raise ValueError("Question too long (max 2000 chars).")
        return v.strip()


# ── Streaming chat ─────────────────────────────────────────────────────────────
@router.post("/chat")
@limiter.limit("30/minute")
def chat(
    request:      Request,
    req:          QuestionRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Stream an answer token by token using Server-Sent Events.
    Rate limited: 30 questions per minute per IP.

    Response format — each line is one SSE message:
      data: {"token": "Xero "}
      data: {"token": "is a "}
      data: {"token": "cloud-based..."}
      data: {"sources": [...], "model": "llama-3.1-8b-instant", "done": true}

    The browser reads these as they arrive and appends each token to the bubble.
    """
    logger.info("Chat stream: user_id=%d session_id=%s", current_user.id, req.session_id)

    # Check user has documents
    if not list_indexed_files(current_user.id):
        raise HTTPException(400, "No documents indexed yet. Please upload a PDF first.")

    # Get or create session
    if req.session_id:
        session = get_session_by_id(db, req.session_id, current_user.id)
        if not session:
            raise HTTPException(404, "Session not found.")
    else:
        session = create_chat_session(db, current_user.id)

    # Save user question immediately
    add_message(db, session.id, role="user", content=req.question)

    # Auto-title session from first question
    if session.title == "New Chat":
        update_session_title(db, session, req.question[:60])

    # Load recent chat history for context
    past    = get_session_messages(db, session.id)
    history = past[:-1]   # exclude the message we just added

    # ── Extract plain Python values BEFORE the generator ─────────────────────
    # The generate() function runs in a separate thread AFTER the DB session
    # is closed. Accessing SQLAlchemy ORM objects (current_user, session)
    # inside the thread causes DetachedInstanceError.
    # Solution: copy all needed values to plain ints/strings now.
    user_id_val    = int(current_user.id)
    session_id_val = int(session.id)
    session_title  = str(session.title)
    question_val   = str(req.question)

    # Buffer for saving to DB after stream completes
    full_answer  = []
    final_sources = []
    final_model   = []

    def generate():
        import json
        from db.database import SessionLocal  # open a fresh DB session for the thread

        # First SSE message — tells frontend which session to track
        yield f"data: {json.dumps({'session_id': session_id_val, 'session_title': session_title})}\n\n"

        for event in stream_answer(question_val, user_id_val, history):
            if event.startswith("data: "):
                try:
                    payload = json.loads(event[6:])
                    if "token" in payload:
                        full_answer.append(payload["token"])
                    if payload.get("done"):
                        final_sources.extend(payload.get("sources", []))
                        final_model.append(payload.get("model", ""))
                except Exception:
                    pass
            yield event

        # Stream complete — save answer using a FRESH DB session
        answer_text = "".join(full_answer)
        if answer_text:
            thread_db = SessionLocal()
            try:
                from db.crud import add_message as _add, touch_session as _touch
                from db.crud import get_session_by_id as _get_session
                _add(
                    thread_db,
                    session_id_val,
                    role="assistant",
                    content=answer_text,
                    sources=final_sources,
                    model=final_model[0] if final_model else "",
                )
                s = _get_session(thread_db, session_id_val, user_id_val)
                if s:
                    _touch(thread_db, s)
                logger.info("Saved streamed answer session_id=%d len=%d", session_id_val, len(answer_text))
            except Exception as exc:
                logger.error("Failed to save streamed answer: %s", exc)
            finally:
                thread_db.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",    # disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Session management ────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    sessions = get_user_sessions(db, current_user.id)
    return {
        "sessions": [
            {
                "id":         s.id,
                "title":      s.title,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
def load_session(
    session_id:   int,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    session = get_session_by_id(db, session_id, current_user.id)
    if not session:
        raise HTTPException(404, "Session not found.")
    messages = get_session_messages(db, session_id)
    return {
        "session_id":    session.id,
        "session_title": session.title,
        "messages":      messages,
    }


@router.delete("/sessions/{session_id}")
def remove_session(
    session_id:   int,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    session = get_session_by_id(db, session_id, current_user.id)
    if not session:
        raise HTTPException(404, "Session not found.")
    delete_session(db, session)
    return {"message": f"Session '{session.title}' deleted."}
