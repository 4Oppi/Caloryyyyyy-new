import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qsl, unquote

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"
DEFAULT_EXPIRE_DAYS = 7


# ---------------------------------------------------------------------------
# 1. Telegram WebApp initData verification
# ---------------------------------------------------------------------------

def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """
    Verify and parse the Telegram WebApp initData string.

    Telegram sends initData as a URL-encoded string, e.g.:
        query_id=AAH...&user=%7B...%7D&auth_date=1234567890&hash=abcdef...

    Steps per Telegram docs:
      1. Parse into key-value pairs.
      2. Extract the 'hash' field.
      3. Sort remaining pairs alphabetically by key.
      4. Join as "key=value\n..." → data_check_string.
      5. secret_key  = HMAC-SHA256(key="WebAppData", msg=bot_token)
      6. hash_check  = HMAC-SHA256(key=secret_key,   msg=data_check_string)
      7. Compare hash_check (hex) with extracted hash.

    Returns the parsed dict on success.
    Raises HTTPException(401) if the signature is invalid or missing.
    """
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData is empty",
        )

    try:
        # parse_qsl preserves duplicates and ordering; unquote handles %7B etc.
        params = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData could not be parsed",
        )

    received_hash = params.pop("hash", None)
    if received_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData missing 'hash' field",
        )

    # Build data-check string: sorted key=value pairs joined by newline
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )

    # Derive secret key: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    # Compute expected hash
    expected_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData signature is invalid",
        )

    return params


# ---------------------------------------------------------------------------
# 2. JWT creation
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict,
    secret: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Encode a JWT with the given payload.

    Args:
        data: Claims to embed (should include "sub" = telegram_id as str).
        secret: Signing secret (settings.JWT_SECRET).
        expires_delta: Token lifetime; defaults to DEFAULT_EXPIRE_DAYS days.

    Returns:
        Signed JWT string.
    """
    payload = data.copy()
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta if expires_delta is not None
        else timedelta(days=DEFAULT_EXPIRE_DAYS)
    )
    payload["exp"] = expire
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# 3. JWT decoding
# ---------------------------------------------------------------------------

def decode_access_token(token: str, secret: str) -> dict:
    """
    Decode and validate a JWT.

    Raises HTTPException(401) if the token is expired, malformed, or
    the signature does not match.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token is invalid or expired: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# 4. Load User from JWT
# ---------------------------------------------------------------------------

def get_user_from_token(token: str, db: Session) -> User:
    """
    Decode the JWT, extract telegram_id from the 'sub' claim, and
    return the corresponding User row from the database.

    Raises:
        HTTPException(401) – token invalid / missing 'sub'.
        HTTPException(404) – user not found in DB.
    """
    payload = decode_access_token(token, settings.JWT_SECRET)

    telegram_id_str: Optional[str] = payload.get("sub")
    if telegram_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' claim",
        )

    try:
        telegram_id = int(telegram_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 'sub' claim is not a valid integer",
        )

    user = db.get(User, telegram_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {telegram_id} not found",
        )

    return user

