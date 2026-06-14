"""Sliding-window in-process rate limiters.

Two flavours:
- `llm_rate_limit(n)` — per-USER, used on authenticated LLM endpoints.
- `_ip_rate_limit_check(request, key, n)` — per-IP (honours X-Forwarded-For),
  used on anonymous public endpoints (hub chat/lead).

Both are in-process; in a multi-instance deployment migrate to Redis.
"""

from __future__ import annotations

import time as _time
from collections import defaultdict, deque
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request

from core.security import get_current_user

_USER_HITS: Dict[str, deque] = defaultdict(deque)
_IP_HITS: Dict[str, deque] = defaultdict(deque)


def llm_rate_limit(max_per_minute: int = 20):
    """Per-user 60s sliding window. Returns a FastAPI Depends."""

    async def _dep(current_user: Dict[str, Any] = Depends(get_current_user)):
        uid = current_user["user_id"]
        now = _time.time()
        dq = _USER_HITS[uid]
        while dq and dq[0] < now - 60:
            dq.popleft()
        if len(dq) >= max_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Trop de requêtes IA — patientez quelques secondes (limite: {max_per_minute}/min).",
            )
        dq.append(now)
        return current_user

    return _dep


def _client_ip(request: Request) -> str:
    """Resolve the real client IP behind a (chain of) proxy(ies).

    The K8s ingress rotates between several proxy pods so request.client.host
    is unreliable. We trust X-Forwarded-For (left-most non-private) when set.
    """
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        for part in xff.split(","):
            ip = part.strip()
            if ip:
                return ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _ip_rate_limit_check(request: Request, key: str, max_per_minute: int) -> None:
    """Per-IP sliding window (60s). Raises 429 when over budget."""
    ip = _client_ip(request)
    bucket = f"{key}:{ip}"
    now = _time.time()
    dq = _IP_HITS[bucket]
    while dq and dq[0] < now - 60:
        dq.popleft()
    if len(dq) >= max_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests — please slow down (limit: {max_per_minute}/min).",
        )
    dq.append(now)


__all__ = ["llm_rate_limit", "_ip_rate_limit_check", "_client_ip"]
