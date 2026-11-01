import hmac
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError

SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(days=7)

ANON_LIMIT = 2
SESSION_COOKIE = "session"
ANON_COOKIE = "anon_count"


def create_access_token(user_id: int, user_email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": user_email,
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_EXPIRE,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def _anon_mac(count: int) -> str:
    return hmac.new(
        SECRET_KEY.encode(),
        f"anon:{count}".encode(),
        hashlib.sha256,
    ).hexdigest()


def encode_anon_cookie(count: int) -> str:
    return f"{count}:{_anon_mac(count)}"


def decode_anon_cookie(value: str) -> int | None:
    """Return the verified count, or None if the cookie is missing or tampered."""
    try:
        count_str, mac = value.split(":", 1)
        count = int(count_str)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(_anon_mac(count), mac):
        return None
    return count
