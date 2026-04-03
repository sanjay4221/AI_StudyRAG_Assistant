"""
core/security.py
----------------
Password hashing and JWT tokens.

Using bcrypt directly (not via passlib) to avoid passlib's
internal 72-byte self-check bug on some Windows environments.
"""

import hashlib
import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt

from core.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES
from core.logger import get_logger
from core.exceptions import AuthError

logger = get_logger(__name__)


# ── Password hashing ──────────────────────────────────────────────────────────
def _prepare(plain_password: str) -> bytes:
    """
    SHA-256 pre-hash → always 32 bytes → safely within bcrypt's 72-byte limit.
    Returns bytes (bcrypt works with bytes not strings).
    """
    return hashlib.sha256(plain_password.encode("utf-8")).digest()


def hash_password(plain_password: str) -> str:
    """Hash a password. Returns a string for storing in the DB."""
    hashed = bcrypt.hashpw(_prepare(plain_password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored hash."""
    try:
        return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))
    except Exception as exc:
        logger.warning("Password verification error: %s", exc)
        return False


# ── JWT tokens ────────────────────────────────────────────────────────────────
def create_access_token(user_id: int, email: str) -> str:
    """Create a signed JWT token for a logged-in user."""
    payload = {
        "user_id": user_id,
        "email":   email,
        "exp":     datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.debug("JWT created for user_id=%d", user_id)
    return token


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Returns payload {user_id, email} if valid.
    Raises AuthError if expired, tampered, or malformed.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if "user_id" not in payload:
            raise AuthError("Token payload is missing user_id.")
        return payload
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise AuthError("Token is invalid or expired. Please log in again.") from exc
