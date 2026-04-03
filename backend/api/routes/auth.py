"""
api/routes/auth.py
------------------
Authentication endpoints:
  POST /auth/register  → create account, return JWT
  POST /auth/login     → verify credentials, return JWT
  GET  /auth/me        → return current user info (token required)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
import re

from core.logger import get_logger
from core.exceptions import AuthError, UserAlreadyExistsError, StudyRAGError
from core.security import hash_password, verify_password, create_access_token
from core.limiter import limiter
from db.database import get_db
from db.models import User
from db.crud import get_user_by_email, create_user, get_user_by_id
from api.deps import get_current_user

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email:     str
    password:  str
    full_name: str = ""

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email address.")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters.")
        return v


class LoginRequest(BaseModel):
    email:    str
    password: str

    @field_validator("email")
    @classmethod
    def email_clean(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user_id:      int
    email:        str
    full_name:    str
    is_admin:     bool = False


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")
def register(request: Request, req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new student account.
    Returns a JWT token immediately — no need to log in separately.
    Rate limited: 5 attempts per minute per IP.
    """
    logger.info("Register attempt: %s", req.email)

    # Check email not already taken
    if get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # Hash password and create user
    hashed = hash_password(req.password)
    user   = create_user(db, req.email, hashed, req.full_name)

    token = create_access_token(user.id, user.email)
    logger.info("User registered: id=%d email=%s", user.id, user.email)

    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name or "",
        is_admin=user.is_admin,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)):
    """
    Log in with email + password.
    Rate limited: 10 attempts per minute per IP — blocks brute force.
    """
    logger.info("Login attempt: %s", req.email)

    user = get_user_by_email(db, req.email)

    # Use same error message for wrong email OR wrong password
    # (don't reveal which one failed — security best practice)
    if not user or not verify_password(req.password, user.hashed_password):
        logger.warning("Failed login for: %s", req.email)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    token = create_access_token(user.id, user.email)
    logger.info("User logged in: id=%d email=%s", user.id, user.email)

    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name or "",
        is_admin=user.is_admin,
    )


@router.get("/me")
def me(current_user=Depends(get_current_user)):
    """Return the currently logged-in user's info."""
    return {
        "user_id":   current_user.id,
        "email":     current_user.email,
        "full_name": current_user.full_name or "",
    }


@router.delete("/account")
def delete_account(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Permanently delete the logged-in user's account and ALL their data.
    Removes: user record, all chat sessions, all messages.
    Also clears their ChromaDB vector store and uploaded files.
    This action cannot be undone.
    """
    from db.crud import delete_account as _delete_account
    from rag.retriever import clear_user_vectorstore
    from core.config import UPLOAD_DIR
    import shutil

    user_id = int(current_user.id)
    email   = str(current_user.email)

    logger.info("Account deletion requested: user_id=%d email=%s", user_id, email)

    # Clear vector store
    try:
        clear_user_vectorstore(user_id)
    except Exception as exc:
        logger.warning("Could not clear vectorstore for user_id=%d: %s", user_id, exc)

    # Clear uploaded files
    try:
        user_dir = UPLOAD_DIR / f"user_{user_id}"
        if user_dir.exists():
            shutil.rmtree(user_dir)
    except Exception as exc:
        logger.warning("Could not clear uploads for user_id=%d: %s", user_id, exc)

    # Delete from DB (cascades to sessions + messages)
    _delete_account(db, current_user)

    logger.info("Account deleted: user_id=%d email=%s", user_id, email)
    return {"message": "Your account and all data have been permanently deleted."}
