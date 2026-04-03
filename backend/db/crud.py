"""
db/crud.py
----------
CRUD operations — Create, Read, Update, Delete.
All database logic lives here. Routes call these functions, never query directly.

Why separate CRUD from routes?
  - Routes handle HTTP (request/response)
  - CRUD handles data (database queries)
  - Makes unit testing trivial — test CRUD without spinning up FastAPI
  - If we add an admin panel later, it reuses the same CRUD functions
"""

import json
from datetime import datetime
from sqlalchemy.orm import Session

from core.logger import get_logger
from db.models import User, ChatSession, ChatMessage

logger = get_logger(__name__)


# ── User operations ───────────────────────────────────────────────────────────

def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by email. Returns None if not found."""
    return db.query(User).filter(User.email == email.lower().strip()).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Look up a user by primary key."""
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, hashed_password: str, full_name: str = "") -> User:
    """
    Insert a new user row.
    Password must already be hashed before calling this — never pass plain text.
    """
    user = User(
        email=email.lower().strip(),
        hashed_password=hashed_password,
        full_name=full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("New user created: id=%d email=%s", user.id, user.email)
    return user


# ── Session operations ────────────────────────────────────────────────────────

def create_chat_session(db: Session, user_id: int, title: str = "New Chat") -> ChatSession:
    """Create a new conversation thread for a user."""
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info("New chat session: id=%d user_id=%d", session.id, user_id)
    return session


def get_user_sessions(db: Session, user_id: int) -> list[ChatSession]:
    """
    Return all sessions for a user, newest first.
    Used to populate the session list in the sidebar.
    """
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


def get_session_by_id(db: Session, session_id: int, user_id: int) -> ChatSession | None:
    """
    Fetch a session by ID — also checks it belongs to this user.
    Prevents one student from reading another student's chat.
    """
    return (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        .first()
    )


def update_session_title(db: Session, session: ChatSession, title: str) -> ChatSession:
    """Update session title (called after the first message sets the topic)."""
    session.title      = title[:80]   # cap at 80 chars
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


def touch_session(db: Session, session: ChatSession) -> None:
    """Update updated_at so sessions sort correctly by last activity."""
    session.updated_at = datetime.utcnow()
    db.commit()


def delete_session(db: Session, session: ChatSession) -> None:
    """Delete a session and all its messages (cascade handles messages)."""
    db.delete(session)
    db.commit()
    logger.info("Deleted chat session id=%d", session.id)


# ── Message operations ────────────────────────────────────────────────────────

def add_message(
    db: Session,
    session_id: int,
    role: str,
    content: str,
    sources: list | None = None,
    model: str | None = None,
) -> ChatMessage:
    """
    Persist one message (user question OR assistant answer).

    sources is stored as a JSON string:
      [{"file": "law.pdf", "page": 2}, ...]
    """
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        sources=json.dumps(sources) if sources else None,
        model=model,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_session_messages(db: Session, session_id: int) -> list[dict]:
    """
    Return all messages for a session as plain dicts (ready for JSON response).
    Sources are decoded from JSON string back to list.
    """
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id":         m.id,
            "role":       m.role,
            "content":    m.content,
            "sources":    json.loads(m.sources) if m.sources else [],
            "model":      m.model,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


# ── Admin operations ──────────────────────────────────────────────────────────

def get_all_users(db: Session) -> list[User]:
    """Return all users ordered by registration date."""
    return db.query(User).order_by(User.created_at.desc()).all()


def get_user_stats(db: Session, user_id: int) -> dict:
    """Return session and message counts for a user."""
    from db.models import ChatSession, ChatMessage
    session_count = db.query(ChatSession).filter(ChatSession.user_id == user_id).count()
    message_count = (
        db.query(ChatMessage)
        .join(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .count()
    )
    return {"sessions": session_count, "messages": message_count}


def get_global_stats(db: Session) -> dict:
    """Return platform-wide stats for the admin dashboard."""
    from db.models import ChatSession, ChatMessage
    return {
        "total_users":    db.query(User).count(),
        "active_users":   db.query(User).filter(User.is_active == True).count(),
        "total_sessions": db.query(ChatSession).count(),
        "total_messages": db.query(ChatMessage).count(),
    }


def delete_user(db: Session, user: User) -> None:
    """Delete a user and all their data (cascade handles sessions + messages)."""
    db.delete(user)
    db.commit()
    logger.info("Deleted user id=%d email=%s", user.id, user.email)


def set_admin(db: Session, user: User, is_admin: bool) -> User:
    """Promote or demote a user to/from admin."""
    user.is_admin = is_admin
    db.commit()
    db.refresh(user)
    return user


def delete_account(db: Session, user: User) -> None:
    """
    Permanently delete a user and ALL their data.
    Cascade handles sessions and messages automatically.
    Called by DELETE /auth/account endpoint.
    """
    logger.info("Account deletion: user_id=%d email=%s", user.id, user.email)
    db.delete(user)
    db.commit()
