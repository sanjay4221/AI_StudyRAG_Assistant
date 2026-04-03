"""
api/deps.py
-----------
Shared FastAPI dependencies.

get_current_user() is the JWT auth guard — add it to any route that
requires a logged-in user:

    @router.post("/chat")
    def chat(req: ..., current_user = Depends(get_current_user)):
        # current_user is a User ORM object
        # current_user.id, current_user.email are available

How JWT auth works in FastAPI:
  1. Browser sends:  Authorization: Bearer eyJhbG...
  2. get_current_user extracts the token from the header
  3. Decodes and verifies the JWT signature + expiry
  4. Looks up the user_id in the database
  5. Returns the User object — or raises 401 if anything fails

This is a FastAPI Dependency — it runs BEFORE your route function.
If it raises HTTPException, the route never executes.
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from core.security import decode_access_token
from core.exceptions import AuthError
from core.logger import get_logger
from db.database import get_db
from db.crud import get_user_by_id
from db.models import User

logger = get_logger(__name__)

# HTTPBearer extracts the token from the Authorization: Bearer <token> header
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Verify the JWT token and return the logged-in User.
    Raises HTTP 401 if the token is missing, invalid, or expired.
    """
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload["user_id"]
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.message)

    user = get_user_by_id(db, user_id)
    if not user:
        logger.warning("JWT valid but user not found: user_id=%d", user_id)
        raise HTTPException(status_code=401, detail="User account not found.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency — requires the logged-in user to be an admin.
    Use on any admin-only route:
        @router.get("/admin/users")
        def list_users(admin = Depends(get_admin_user)):
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
