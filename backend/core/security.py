"""Shared FastAPI dependencies for authentication + JWT helpers.

`get_current_user` is the canonical dependency for any protected route.
Accepts EITHER a JWT bearer token (email/password / Google OAuth issued)
OR a session token stored in `user_sessions` (Emergent OAuth callback).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, Optional

import jwt
from fastapi import Header, HTTPException
from passlib.context import CryptContext

from core.db import db, _now

JWT_SECRET = os.environ.get("JWT_SECRET", "etoh_dev_secret_change_me")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MINUTES = int(os.environ.get("JWT_EXP_MINUTES", "10080"))  # 7 days

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def create_jwt(user_id: str, email: str) -> str:
    now = _now()
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Resolve the user behind the request. 401 if missing/invalid."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()

    user_id: Optional[str] = None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        # Fallback to session token (Emergent Google OAuth flow)
        session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if not session:
            raise HTTPException(status_code=401, detail="Invalid token")
        from datetime import timezone as _tz
        exp = session.get("expires_at")
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=_tz.utc)
        if exp and exp < _now():
            raise HTTPException(status_code=401, detail="Session expired")
        user_id = session.get("user_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


__all__ = [
    "get_current_user",
    "create_jwt",
    "hash_password",
    "verify_password",
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "JWT_EXP_MINUTES",
]
