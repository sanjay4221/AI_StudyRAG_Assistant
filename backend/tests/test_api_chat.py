"""
tests/test_api_chat.py
----------------------
API tests for chat and session management endpoints.

What we test:
  POST /chat            → auth required, no docs error, session created
  GET  /sessions        → returns user's sessions
  GET  /sessions/{id}   → loads messages, rejects wrong user
  DELETE /sessions/{id} → deletes session, rejects wrong user

Streaming note:
  The /chat endpoint returns a StreamingResponse (SSE).
  TestClient reads the full streamed response as text.
  We verify the SSE format and that session_id is returned.
"""

import json
import pytest
from unittest.mock import patch
from db.crud import create_chat_session, add_message


# ── Chat endpoint ─────────────────────────────────────────────────────────────

class TestChat:

    def test_chat_requires_auth(self, client):
        """POST /chat without token returns 403."""
        r = client.post("/chat", json={"question": "What is a tort?"})
        assert r.status_code == 403

    def test_chat_rejects_empty_question(self, client, auth_headers):
        """Empty question string returns 422."""
        r = client.post("/chat", json={"question": "   "}, headers=auth_headers)
        assert r.status_code == 422

    def test_chat_rejects_too_long_question(self, client, auth_headers):
        """Question over 2000 chars returns 422."""
        r = client.post(
            "/chat",
            json={"question": "x" * 2001},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_chat_no_documents_returns_400(self, client, auth_headers):
        """Asking without any indexed docs returns 400."""
        with patch("api.routes.chat.list_indexed_files", return_value=[]):
            r = client.post(
                "/chat",
                json={"question": "What is a tort?"},
                headers=auth_headers,
            )
        assert r.status_code == 400
        assert "upload" in r.json()["detail"].lower()

    def test_chat_streams_sse_events(self, client, auth_headers, db_session, test_user):
        """
        When docs exist, /chat returns SSE stream with session_id and tokens.
        We mock stream_answer to avoid calling Groq API in tests.
        """
        def mock_stream(question, user_id, history):
            yield f"data: {json.dumps({'token': 'Xero '})}\n\n"
            yield f"data: {json.dumps({'token': 'is great.'})}\n\n"
            yield f"data: {json.dumps({'sources': [], 'model': 'test-model', 'done': True})}\n\n"

        with patch("api.routes.chat.list_indexed_files", return_value=["xero.pdf"]), \
             patch("api.routes.chat.stream_answer", side_effect=mock_stream):

            r = client.post(
                "/chat",
                json={"question": "What is Xero?"},
                headers=auth_headers,
            )

        assert r.status_code == 200
        # Response should contain SSE data lines
        text = r.text
        assert "data:" in text
        assert "session_id" in text

    def test_chat_invalid_session_id_returns_404(self, client, auth_headers):
        """Passing a non-existent session_id returns 404."""
        with patch("api.routes.chat.list_indexed_files", return_value=["doc.pdf"]):
            r = client.post(
                "/chat",
                json={"question": "test", "session_id": 99999},
                headers=auth_headers,
            )
        assert r.status_code == 404


# ── Sessions ──────────────────────────────────────────────────────────────────

class TestSessions:

    def test_list_sessions_requires_auth(self, client):
        """GET /sessions without token returns 403."""
        r = client.get("/sessions")
        assert r.status_code == 403

    def test_list_sessions_empty(self, client, auth_headers):
        """New user has no sessions."""
        r = client.get("/sessions", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["sessions"] == []

    def test_list_sessions_returns_user_sessions(self, client, auth_headers, db_session, test_user):
        """Returns sessions belonging to the logged-in user."""
        create_chat_session(db_session, test_user.id, title="Session A")
        create_chat_session(db_session, test_user.id, title="Session B")

        r = client.get("/sessions", headers=auth_headers)
        assert r.status_code == 200
        sessions = r.json()["sessions"]
        assert len(sessions) == 2
        titles = [s["title"] for s in sessions]
        assert "Session A" in titles
        assert "Session B" in titles

    def test_load_session_returns_messages(self, client, auth_headers, db_session, test_user):
        """GET /sessions/{id} returns the session with its messages."""
        session = create_chat_session(db_session, test_user.id, title="Law session")
        add_message(db_session, session.id, role="user",      content="What is negligence?")
        add_message(db_session, session.id, role="assistant", content="Negligence is...")

        r = client.get(f"/sessions/{session.id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["session_title"] == "Law session"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    def test_load_session_wrong_user_returns_404(self, client, db_session, test_user):
        """
        A different user cannot load another user's session.
        Returns 404 (not 403) — don't reveal the session exists.
        """
        from db.crud import create_user
        from core.security import hash_password, create_access_token

        other = create_user(db_session, "other@test.com", hash_password("pass"))
        other_token = create_access_token(other.id, other.email)
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # Session belongs to test_user
        session = create_chat_session(db_session, test_user.id)

        # other user tries to load it
        r = client.get(f"/sessions/{session.id}", headers=other_headers)
        assert r.status_code == 404

    def test_delete_session(self, client, auth_headers, db_session, test_user):
        """DELETE /sessions/{id} removes the session."""
        session = create_chat_session(db_session, test_user.id, title="To delete")
        r = client.delete(f"/sessions/{session.id}", headers=auth_headers)
        assert r.status_code == 200
        assert "deleted" in r.json()["message"].lower()

    def test_delete_session_wrong_user_returns_404(self, client, db_session, test_user):
        """Cannot delete another user's session."""
        from db.crud import create_user
        from core.security import hash_password, create_access_token

        other = create_user(db_session, "attacker@test.com", hash_password("pass"))
        other_token = create_access_token(other.id, other.email)
        other_headers = {"Authorization": f"Bearer {other_token}"}

        session = create_chat_session(db_session, test_user.id)
        r = client.delete(f"/sessions/{session.id}", headers=other_headers)
        assert r.status_code == 404
