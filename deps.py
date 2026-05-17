from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_user_from_token
from app.database import get_db  # noqa: F401  (re-exported for convenience)
from app.models import User


def get_current_user(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
) -> User:
    """
    FastAPI dependency that extracts and validates the Bearer token from
    the Authorization header, then returns the authenticated User.

    Usage in a router:
        @router.get("/me")
        def me(user: User = Depends(get_current_user)):
            ...

    Raises:
        HTTPException(401) – header missing, token malformed, or expired.
        HTTPException(404) – token valid but user not found in DB.
    """
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer '",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ")

    # get_user_from_token decodes the JWT and fetches the User row;
    # it raises 401 on bad tokens and 404 if the user no longer exists.
    return get_user_from_token(token, db)

