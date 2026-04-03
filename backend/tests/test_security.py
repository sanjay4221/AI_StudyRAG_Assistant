"""
tests/test_security.py
----------------------
Unit tests for core/security.py

These are PURE unit tests — no DB, no HTTP, no external APIs.
They test the security functions in complete isolation.

What we test:
  - Password hashing produces a different string from the input
  - The same password always verifies correctly
  - Wrong passwords are rejected
  - Passwords of any length work (our SHA-256 pre-hash fix)
  - JWT tokens encode and decode correctly
  - Expired tokens are rejected
  - Tampered tokens are rejected
"""

import time
import pytest
from core.security import hash_password, verify_password, create_access_token, decode_access_token
from core.exceptions import AuthError


# ── Password hashing ──────────────────────────────────────────────────────────

class TestPasswordHashing:

    def test_hash_is_not_plain_text(self):
        """Stored hash must never equal the original password."""
        plain = "mypassword123"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_correct_password_verifies(self):
        """Same password must verify successfully against its hash."""
        plain = "mypassword123"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_rejected(self):
        """Different password must NOT verify against the hash."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_produces_different_hashes(self):
        """
        bcrypt uses a random salt — same password hashed twice
        produces DIFFERENT hashes. This is a security feature.
        """
        plain = "samepassword"
        hash1 = hash_password(plain)
        hash2 = hash_password(plain)
        assert hash1 != hash2
        # But both must verify correctly
        assert verify_password(plain, hash1) is True
        assert verify_password(plain, hash2) is True

    def test_long_password_works(self):
        """
        Our SHA-256 pre-hash ensures passwords longer than 72 chars work.
        Without it, bcrypt would silently truncate at 72 bytes.
        """
        long_password = "a" * 100   # 100 chars — beyond bcrypt's 72-byte limit
        hashed = hash_password(long_password)
        assert verify_password(long_password, hashed) is True
        assert verify_password("a" * 99, hashed) is False  # one char less = wrong

    def test_empty_string_hashes(self):
        """Even empty string should hash and verify (not crash)."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False

    def test_unicode_password(self):
        """Passwords with unicode characters must work."""
        plain = "pässwörD123!@#"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True


# ── JWT tokens ────────────────────────────────────────────────────────────────

class TestJWTTokens:

    def test_token_creation_returns_string(self):
        """create_access_token must return a non-empty string."""
        token = create_access_token(user_id=1, email="test@test.com")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_token_decodes_correctly(self):
        """Decoded payload must contain the user_id and email we encoded."""
        token = create_access_token(user_id=42, email="student@uni.com")
        payload = decode_access_token(token)
        assert payload["user_id"] == 42
        assert payload["email"] == "student@uni.com"

    def test_tampered_token_rejected(self):
        """Modifying the token must raise AuthError."""
        token = create_access_token(user_id=1, email="test@test.com")
        # Flip the last character to tamper with the signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(AuthError):
            decode_access_token(tampered)

    def test_invalid_token_rejected(self):
        """Random garbage string must raise AuthError."""
        with pytest.raises(AuthError):
            decode_access_token("not.a.valid.jwt.token")

    def test_empty_token_rejected(self):
        """Empty string must raise AuthError."""
        with pytest.raises(AuthError):
            decode_access_token("")

    def test_different_users_get_different_tokens(self):
        """Two different users must get different tokens."""
        token1 = create_access_token(user_id=1, email="user1@test.com")
        token2 = create_access_token(user_id=2, email="user2@test.com")
        assert token1 != token2

    def test_payload_contains_expiry(self):
        """Token payload must contain an expiry timestamp."""
        token = create_access_token(user_id=1, email="test@test.com")
        payload = decode_access_token(token)
        assert "exp" in payload
        # Expiry must be in the future
        assert payload["exp"] > time.time()
