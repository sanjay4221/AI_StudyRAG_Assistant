"""
tests/test_crud.py
------------------
Integration tests for db/crud.py

These tests hit the real DB layer (in-memory SQLite).
They verify that our CRUD operations work correctly end-to-end.

What we test:
  User CRUD    → create, fetch by email, fetch by id
  Session CRUD → create, list, update title, touch, delete
  Message CRUD → add messages, retrieve in order
  Admin CRUD   → promote/demote, get stats
"""

import pytest
from db.crud import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    create_chat_session,
    get_user_sessions,
    get_session_by_id,
    get_session_messages,
    add_message,
    update_session_title,
    touch_session,
    delete_session,
    get_user_stats,
    get_global_stats,
    set_admin,
)
from core.security import hash_password


# ── User CRUD ─────────────────────────────────────────────────────────────────

class TestUserCRUD:

    def test_create_user(self, db_session):
        """create_user returns a User with correct fields."""
        user = create_user(
            db=db_session,
            email="alice@test.com",
            hashed_password=hash_password("pass123"),
            full_name="Alice Smith",
        )
        assert user.id is not None
        assert user.email == "alice@test.com"
        assert user.full_name == "Alice Smith"
        assert user.is_active is True
        assert user.is_admin is False

    def test_email_stored_lowercase(self, db_session):
        """Emails must be normalised to lowercase."""
        user = create_user(db_session, "BOB@TEST.COM", hash_password("pass"))
        assert user.email == "bob@test.com"

    def test_get_user_by_email_found(self, db_session):
        """get_user_by_email returns the user when they exist."""
        create_user(db_session, "carol@test.com", hash_password("pass"))
        found = get_user_by_email(db_session, "carol@test.com")
        assert found is not None
        assert found.email == "carol@test.com"

    def test_get_user_by_email_not_found(self, db_session):
        """get_user_by_email returns None for unknown email."""
        result = get_user_by_email(db_session, "nobody@test.com")
        assert result is None

    def test_get_user_by_email_case_insensitive(self, db_session):
        """Email lookup must be case-insensitive."""
        create_user(db_session, "dave@test.com", hash_password("pass"))
        found = get_user_by_email(db_session, "DAVE@TEST.COM")
        assert found is not None

    def test_get_user_by_id(self, db_session):
        """get_user_by_id returns the correct user."""
        user = create_user(db_session, "eve@test.com", hash_password("pass"))
        found = get_user_by_id(db_session, user.id)
        assert found is not None
        assert found.id == user.id

    def test_get_user_by_id_not_found(self, db_session):
        """get_user_by_id returns None for unknown id."""
        result = get_user_by_id(db_session, 99999)
        assert result is None


# ── Session CRUD ──────────────────────────────────────────────────────────────

class TestSessionCRUD:

    def test_create_session(self, db_session, test_user):
        """create_chat_session returns a session with correct defaults."""
        session = create_chat_session(db_session, test_user.id)
        assert session.id is not None
        assert session.user_id == test_user.id
        assert session.title == "New Chat"

    def test_create_session_with_title(self, db_session, test_user):
        """Sessions can be created with a custom title."""
        session = create_chat_session(db_session, test_user.id, title="Law Notes")
        assert session.title == "Law Notes"

    def test_get_user_sessions_empty(self, db_session, test_user):
        """New user has no sessions."""
        sessions = get_user_sessions(db_session, test_user.id)
        assert sessions == []

    def test_get_user_sessions_returns_all(self, db_session, test_user):
        """get_user_sessions returns all sessions for a user."""
        create_chat_session(db_session, test_user.id, title="Session 1")
        create_chat_session(db_session, test_user.id, title="Session 2")
        sessions = get_user_sessions(db_session, test_user.id)
        assert len(sessions) == 2

    def test_get_session_by_id_correct_user(self, db_session, test_user):
        """get_session_by_id succeeds for the owning user."""
        session = create_chat_session(db_session, test_user.id)
        found   = get_session_by_id(db_session, session.id, test_user.id)
        assert found is not None
        assert found.id == session.id

    def test_get_session_by_id_wrong_user(self, db_session, test_user):
        """get_session_by_id returns None for a different user — security check."""
        session = create_chat_session(db_session, test_user.id)
        other_user_id = test_user.id + 999
        found = get_session_by_id(db_session, session.id, other_user_id)
        assert found is None   # must not leak another user's session

    def test_update_session_title(self, db_session, test_user):
        """update_session_title changes the title correctly."""
        session = create_chat_session(db_session, test_user.id)
        updated = update_session_title(db_session, session, "What is a tort?")
        assert updated.title == "What is a tort?"

    def test_update_session_title_truncated_at_80(self, db_session, test_user):
        """Titles longer than 80 chars are truncated."""
        session = create_chat_session(db_session, test_user.id)
        long_title = "A" * 100
        updated = update_session_title(db_session, session, long_title)
        assert len(updated.title) == 80

    def test_delete_session(self, db_session, test_user):
        """delete_session removes the session from the DB."""
        session  = create_chat_session(db_session, test_user.id)
        sess_id  = session.id
        delete_session(db_session, session)
        found = get_session_by_id(db_session, sess_id, test_user.id)
        assert found is None


# ── Message CRUD ──────────────────────────────────────────────────────────────

class TestMessageCRUD:

    def test_add_user_message(self, db_session, test_user):
        """add_message stores a user message correctly."""
        session = create_chat_session(db_session, test_user.id)
        msg = add_message(db_session, session.id, role="user", content="What is Xero?")
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "What is Xero?"
        assert msg.session_id == session.id

    def test_add_assistant_message_with_sources(self, db_session, test_user):
        """add_message stores sources as JSON string."""
        import json
        session = create_chat_session(db_session, test_user.id)
        sources = [{"file": "law.pdf", "page": 2}]
        msg = add_message(
            db_session, session.id,
            role="assistant",
            content="Xero is a cloud accounting tool.",
            sources=sources,
            model="llama-3.1-8b-instant",
        )
        assert msg.role == "assistant"
        assert msg.model == "llama-3.1-8b-instant"
        stored_sources = json.loads(msg.sources)
        assert stored_sources[0]["file"] == "law.pdf"

    def test_get_session_messages_order(self, db_session, test_user):
        """Messages are returned in chronological order."""
        session = create_chat_session(db_session, test_user.id)
        add_message(db_session, session.id, role="user",      content="Question 1")
        add_message(db_session, session.id, role="assistant", content="Answer 1")
        add_message(db_session, session.id, role="user",      content="Question 2")

        messages = get_session_messages(db_session, session.id)
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Question 1"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["content"] == "Question 2"

    def test_get_session_messages_sources_decoded(self, db_session, test_user):
        """Sources in retrieved messages should be a list, not a string."""
        session = create_chat_session(db_session, test_user.id)
        add_message(
            db_session, session.id,
            role="assistant", content="Answer",
            sources=[{"file": "doc.pdf", "page": 1}],
        )
        messages = get_session_messages(db_session, session.id)
        assert isinstance(messages[0]["sources"], list)

    def test_messages_deleted_with_session(self, db_session, test_user):
        """Deleting a session cascades to delete its messages."""
        session = create_chat_session(db_session, test_user.id)
        add_message(db_session, session.id, role="user", content="test")
        delete_session(db_session, session)
        # Messages should be gone too (cascade)
        messages = get_session_messages(db_session, session.id)
        assert messages == []


# ── Admin CRUD ────────────────────────────────────────────────────────────────

class TestAdminCRUD:

    def test_set_admin_true(self, db_session, test_user):
        """set_admin promotes a user to admin."""
        updated = set_admin(db_session, test_user, True)
        assert updated.is_admin is True

    def test_set_admin_false(self, db_session, test_user):
        """set_admin demotes an admin back to regular user."""
        set_admin(db_session, test_user, True)
        updated = set_admin(db_session, test_user, False)
        assert updated.is_admin is False

    def test_get_user_stats(self, db_session, test_user):
        """get_user_stats returns correct session and message counts."""
        s1 = create_chat_session(db_session, test_user.id)
        s2 = create_chat_session(db_session, test_user.id)
        add_message(db_session, s1.id, role="user", content="Q1")
        add_message(db_session, s1.id, role="assistant", content="A1")
        add_message(db_session, s2.id, role="user", content="Q2")

        stats = get_user_stats(db_session, test_user.id)
        assert stats["sessions"] == 2
        assert stats["messages"] == 3

    def test_get_global_stats(self, db_session, test_user):
        """get_global_stats returns platform-wide counts."""
        stats = get_global_stats(db_session)
        assert "total_users" in stats
        assert "total_sessions" in stats
        assert "total_messages" in stats
        assert stats["total_users"] >= 1
