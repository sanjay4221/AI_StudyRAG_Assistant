"""
db/models.py
------------
SQLAlchemy ORM models — defines the database tables.

Three tables:
  users        — registered students (id, email, hashed password)
  chat_sessions — one session = one conversation thread per user
  chat_messages — individual Q&A pairs belonging to a session

Relationships:
  User → has many → ChatSessions
  ChatSession → has many → ChatMessages

Why SQLAlchemy ORM instead of raw SQL?
  - Write Python classes, SQLAlchemy generates the SQL
  - Same code works on SQLite (dev) and Postgres (prod) — just change the URL
  - Relationships are navigable as Python attributes (user.sessions)
  - Alembic uses these models to generate migration scripts automatically
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text,
    DateTime, ForeignKey, Boolean,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    """
    Represents a registered student.
    Password is NEVER stored in plain text — only the bcrypt hash.
    """
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name      = Column(String(255), nullable=True)
    is_active      = Column(Boolean, default=True)
    is_admin       = Column(Boolean, default=False)   # admin flag — set manually in DB
    created_at     = Column(DateTime, default=datetime.utcnow)

    # One user → many sessions
    sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",   # delete sessions when user is deleted
        order_by="ChatSession.created_at.desc()",
    )

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class ChatSession(Base):
    """
    A conversation thread — groups related messages together.
    Created automatically on first message if no session is active.

    title: auto-generated from the first question (first 60 chars)
    """
    __tablename__ = "chat_sessions"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title      = Column(String(255), nullable=False, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user     = relationship("User", back_populates="sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
    )

    def __repr__(self):
        return f"<ChatSession id={self.id} user_id={self.user_id} title={self.title!r}>"


class ChatMessage(Base):
    """
    One Q&A pair inside a session.
    Stores both the question and the answer so we can replay the history.

    role: "user" or "assistant" — mirrors the LLM message format
    sources: JSON string of citation chips e.g. '[{"file":"law.pdf","page":2}]'
    model: which Groq model generated this answer
    """
    __tablename__ = "chat_messages"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role       = Column(String(20), nullable=False)        # "user" or "assistant"
    content    = Column(Text, nullable=False)              # the actual message text
    sources    = Column(Text, nullable=True)               # JSON string of citations
    model      = Column(String(100), nullable=True)        # e.g. "llama-3.1-8b-instant"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage id={self.id} role={self.role} session_id={self.session_id}>"
