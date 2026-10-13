"""Protection for /api/v1/admin/* endpoints: shared-secret auth, a
process-local rate limit, and a request-size guard.

Threat model and limitations (see README "Security notes" for the full
picture):

- This is a single shared secret (`ADMIN_API_KEY`), not per-user
  authentication or authorization. It is meant for trusted server-side
  callers only (an internal script, CI, or the existing Node.js backend
  calling server-to-server) -- never embed it in browser-facing frontend
  code, and CORS is not a substitute for this check.
- The rate limiter is an in-memory fixed window, local to this process. It
  resets on restart and does not coordinate across multiple app replicas.
  Adequate for a single-instance internal admin API; revisit if ever
  horizontally scaled.

The request body-size guard lives in app/core/middleware.py (real ASGI
middleware, not a route dependency -- it needs to run before routing/body
parsing, which only middleware can guarantee).
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

_api_key_header = APIKeyHeader(name="X-Admin-Api-Key", auto_error=False)


async def require_admin_api_key(provided_key: str | None = Depends(_api_key_header)) -> None:
    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured on this deployment.",
        )
    if not provided_key or not secrets.compare_digest(provided_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key.",
        )


class FixedWindowRateLimiter:
    """A plain fixed-window limiter: at most `limit` calls per `key` within
    any rolling `window_seconds` window. Intentionally simple -- see module
    docstring for what this does and doesn't protect against.
    """

    def __init__(self, *, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        now = time.monotonic()
        async with self._lock:
            hits = self._hits[key]
            cutoff = now - self._window_seconds
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self._limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many import requests. Try again later.",
                )
            hits.append(now)


_import_rate_limiter: FixedWindowRateLimiter | None = None


def _get_import_rate_limiter() -> FixedWindowRateLimiter:
    global _import_rate_limiter
    if _import_rate_limiter is None:
        _import_rate_limiter = FixedWindowRateLimiter(
            limit=get_settings().admin_import_rate_limit_per_minute
        )
    return _import_rate_limiter


async def rate_limit_admin_imports(provided_key: str | None = Depends(_api_key_header)) -> None:
    # Only reached if require_admin_api_key (listed first on the route)
    # already passed, so provided_key is the valid admin key here.
    await _get_import_rate_limiter().check(provided_key or "unknown")
