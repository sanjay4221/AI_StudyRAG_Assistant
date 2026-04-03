"""
tests/test_api_auth.py
----------------------
API-level tests for authentication endpoints.

These are HTTP integration tests — they call the real FastAPI endpoints
through a TestClient, which exercises the full request/response cycle
including validation, dependency injection, and DB operations.

What we test:
  POST /auth/register  → success, duplicate email, weak password
  POST /auth/login     → success, wrong password, unknown email
  GET  /auth/me        → valid token, no token, expired token
"""

import pytest


# ── Register ──────────────────────────────────────────────────────────────────

class TestRegister:

    def test_register_success(self, client):
        """New user registration returns token + user info."""
        r = client.post("/auth/register", json={
            "email":     "newstudent@uni.com",
            "password":  "securepass123",
            "full_name": "New Student",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["email"] == "newstudent@uni.com"
        assert data["full_name"] == "New Student"
        assert data["user_id"] is not None

    def test_register_duplicate_email(self, client, test_user):
        """Registering with an existing email returns 409 Conflict."""
        r = client.post("/auth/register", json={
            "email":    "student@test.com",   # same as test_user fixture
            "password": "anotherpass123",
        })
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"].lower()

    def test_register_short_password(self, client):
        """Password shorter than 6 characters is rejected with 422."""
        r = client.post("/auth/register", json={
            "email":    "weak@test.com",
            "password": "123",   # too short
        })
        assert r.status_code == 422

    def test_register_invalid_email(self, client):
        """Invalid email format is rejected."""
        r = client.post("/auth/register", json={
            "email":    "notanemail",
            "password": "validpass123",
        })
        assert r.status_code == 422

    def test_register_missing_fields(self, client):
        """Missing required fields returns 422."""
        r = client.post("/auth/register", json={"email": "only@email.com"})
        assert r.status_code == 422

    def test_register_without_full_name(self, client):
        """full_name is optional — registration works without it."""
        r = client.post("/auth/register", json={
            "email":    "noname@test.com",
            "password": "validpass123",
        })
        assert r.status_code == 200
        assert r.json()["full_name"] == ""

    def test_register_token_is_usable(self, client):
        """Token returned at registration must work on protected endpoints."""
        r = client.post("/auth/register", json={
            "email":    "tokencheck@test.com",
            "password": "validpass123",
        })
        token = r.json()["access_token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:

    def test_login_success(self, client, test_user):
        """Correct credentials return a JWT token."""
        r = client.post("/auth/login", json={
            "email":    "student@test.com",
            "password": "testpass123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["email"] == "student@test.com"

    def test_login_wrong_password(self, client, test_user):
        """Wrong password returns 401."""
        r = client.post("/auth/login", json={
            "email":    "student@test.com",
            "password": "wrongpassword",
        })
        assert r.status_code == 401
        # Error message must not hint whether email or password is wrong
        assert "incorrect" in r.json()["detail"].lower()

    def test_login_unknown_email(self, client):
        """Unknown email returns 401 (same message as wrong password)."""
        r = client.post("/auth/login", json={
            "email":    "ghost@test.com",
            "password": "anypassword",
        })
        assert r.status_code == 401

    def test_login_case_insensitive_email(self, client, test_user):
        """Login works with uppercase email."""
        r = client.post("/auth/login", json={
            "email":    "STUDENT@TEST.COM",
            "password": "testpass123",
        })
        assert r.status_code == 200


# ── Me (protected route) ──────────────────────────────────────────────────────

class TestMe:

    def test_me_with_valid_token(self, client, auth_headers, test_user):
        """GET /auth/me returns user info with a valid token."""
        r = client.get("/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "student@test.com"
        assert data["user_id"] == test_user.id

    def test_me_without_token(self, client):
        """GET /auth/me without a token returns 403 (missing credentials)."""
        r = client.get("/auth/me")
        assert r.status_code == 403

    def test_me_with_invalid_token(self, client):
        """GET /auth/me with a garbage token returns 403."""
        r = client.get("/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
        assert r.status_code == 403

    def test_me_with_wrong_scheme(self, client):
        """Token must use Bearer scheme."""
        r = client.get("/auth/me", headers={"Authorization": "Basic abc123"})
        assert r.status_code == 403
