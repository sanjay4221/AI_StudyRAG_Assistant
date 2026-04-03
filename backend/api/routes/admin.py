"""
api/routes/admin.py
-------------------
Admin-only endpoints — all require is_admin=True on the User.

GET  /admin/stats              → platform-wide counts
GET  /admin/users              → all users with stats
GET  /admin/users/{id}         → one user's full detail
GET  /admin/users/{id}/sessions → all chat sessions for a user
DELETE /admin/users/{id}       → delete user + all their data
POST /admin/users/{id}/promote → make user an admin
POST /admin/users/{id}/demote  → remove admin from user
POST /admin/users/{id}/deactivate → disable account
POST /admin/users/{id}/activate   → re-enable account
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.logger import get_logger
from db.database import get_db
from db.models import User
from db.crud import (
    get_all_users,
    get_user_by_id,
    get_user_stats,
    get_global_stats,
    get_user_sessions,
    get_session_messages,
    delete_user,
    set_admin,
)
from rag.retriever import list_indexed_files
from api.deps import get_admin_user

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _user_detail(db: Session, user: User) -> dict:
    """Build a full detail dict for one user."""
    stats = get_user_stats(db, user.id)
    try:
        docs = list_indexed_files(user.id)
    except Exception:
        docs = []
    return {
        "id":         user.id,
        "email":      user.email,
        "full_name":  user.full_name or "",
        "is_active":  user.is_active,
        "is_admin":   user.is_admin,
        "created_at": user.created_at.isoformat(),
        "documents":  docs,
        "sessions":   stats["sessions"],
        "messages":   stats["messages"],
    }


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def stats(
    admin: User    = Depends(get_admin_user),
    db:    Session = Depends(get_db),
):
    """Global platform stats — user counts, session counts, message counts."""
    data = get_global_stats(db)
    logger.info("Admin stats requested by user_id=%d", admin.id)
    return data


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    admin: User    = Depends(get_admin_user),
    db:    Session = Depends(get_db),
):
    """List all registered users with their stats and indexed documents."""
    users = get_all_users(db)
    logger.info("Admin user list requested by user_id=%d  count=%d", admin.id, len(users))
    return {"users": [_user_detail(db, u) for u in users]}


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """Get full detail for one user."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    return _user_detail(db, user)


@router.get("/users/{user_id}/sessions")
def user_sessions(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """List all chat sessions for a user, with message previews."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")

    sessions = get_user_sessions(db, user_id)
    result   = []
    for s in sessions:
        msgs = get_session_messages(db, s.id)
        result.append({
            "id":         s.id,
            "title":      s.title,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "messages":   msgs,
        })
    return {"sessions": result}


# ── User management ───────────────────────────────────────────────────────────

@router.delete("/users/{user_id}")
def remove_user(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """
    Delete a user and ALL their data — sessions, messages, documents.
    Also clears their ChromaDB collection.
    This cannot be undone.
    """
    if user_id == admin.id:
        raise HTTPException(400, "You cannot delete your own account.")

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")

    # Clear their vector store
    try:
        from rag.retriever import clear_user_vectorstore
        clear_user_vectorstore(user_id)
    except Exception as exc:
        logger.warning("Could not clear vectorstore for user_id=%d: %s", user_id, exc)

    delete_user(db, user)
    logger.warning("Admin user_id=%d deleted user_id=%d email=%s", admin.id, user_id, user.email)
    return {"message": f"User '{user.email}' and all their data deleted."}


@router.post("/users/{user_id}/promote")
def promote_user(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """Grant admin privileges to a user."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    set_admin(db, user, True)
    logger.info("Admin user_id=%d promoted user_id=%d", admin.id, user_id)
    return {"message": f"'{user.email}' is now an admin."}


@router.post("/users/{user_id}/demote")
def demote_user(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """Remove admin privileges from a user."""
    if user_id == admin.id:
        raise HTTPException(400, "You cannot demote yourself.")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    set_admin(db, user, False)
    return {"message": f"'{user.email}' admin access removed."}


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """Disable a user account — they can no longer log in."""
    if user_id == admin.id:
        raise HTTPException(400, "You cannot deactivate yourself.")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    user.is_active = False
    db.commit()
    return {"message": f"'{user.email}' account deactivated."}


@router.post("/users/{user_id}/activate")
def activate_user(
    user_id: int,
    admin:   User    = Depends(get_admin_user),
    db:      Session = Depends(get_db),
):
    """Re-enable a deactivated user account."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    user.is_active = True
    db.commit()
    return {"message": f"'{user.email}' account activated."}
