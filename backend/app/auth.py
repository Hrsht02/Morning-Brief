import datetime
import secrets
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from . import models
from .security import hash_password, verify_password

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def create_access_token(user_id: int) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        return int(user_id) if user_id is not None else None
    except (JWTError, ValueError, TypeError):
        return None


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_error
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_error
    return user


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """Strict: only the 'admin' role. Use this for anything sensitive - user
    management, source/settings changes, deleting data, API key issuance."""
    if user.role != "admin" and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_current_developer_or_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """Looser: 'developer' OR 'admin'. Use this for read-only visibility into
    stats/sources/settings/pending stories, and for the sandboxed test-mode
    actions that never touch real users or real sends."""
    if user.role not in ("developer", "admin") and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Developer or admin access required")
    return user


def generate_random_password_hash() -> str:
    """Used for Google-only sign-ups: the account needs SOME password hash to
    satisfy the DB's NOT NULL constraint, but it must never be a usable,
    guessable, or even known value - only Google sign-in can ever authenticate
    this account. A random 32-byte token, immediately hashed and discarded, does that."""
    return hash_password(secrets.token_urlsafe(32))


# ---------------- Google Sign-In ----------------
def verify_google_id_token(id_token_str: str) -> dict:
    """Verifies a Google ID token's signature and audience, returning the
    decoded claims (email, sub, name, ...) if valid. Raises HTTPException on
    any failure - never returns a partially-trusted result."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Sign-In is not configured on this server (missing GOOGLE_CLIENT_ID)")

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        claims = google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
        if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
            raise ValueError("Token audience mismatch")
        return claims
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google sign-in token: {e}")


# ---------------- API key auth (for the developer sandbox endpoints) ----------------
def get_api_key_context(
    x_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> models.ApiKey:
    """Every /api/v1/* endpoint requires a valid, active API key in the
    X-Api-Key header. Keys are only ever usable for the sandboxed test
    endpoints - see routers/api_v1.py for exactly what this grants."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-Api-Key header")

    prefix = x_api_key[:8]
    candidates = db.query(models.ApiKey).filter(
        models.ApiKey.key_prefix == prefix, models.ApiKey.is_active.is_(True)
    ).all()

    for candidate in candidates:
        if verify_password(x_api_key, candidate.key_hash):
            candidate.last_used_at = datetime.datetime.utcnow()
            db.commit()
            return candidate

    raise HTTPException(status_code=401, detail="Invalid or inactive API key")
