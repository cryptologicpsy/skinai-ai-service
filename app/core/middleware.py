"""ASGI middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Rejects oversized requests under `path_prefix` with 413, before
    routing or body parsing happens -- unlike a route-level dependency,
    middleware is guaranteed to run first.

    Content-Length-only: a client using chunked transfer-encoding without
    Content-Length bypasses this specific check. The reverse proxy / ASGI
    server in front of this service should also enforce a hard body-size
    cap; this is defense in depth, not the only layer.
    """

    def __init__(self, app, *, path_prefix: str) -> None:
        super().__init__(app)
        self._path_prefix = path_prefix

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(self._path_prefix):
            settings = get_settings()
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    size = int(content_length)
                except ValueError:
                    size = None
                if size is not None and size > settings.import_max_json_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": (
                                f"Request body of {size} bytes exceeds the "
                                f"{settings.import_max_json_body_bytes}-byte limit "
                                "for bulk imports."
                            )
                        },
                    )
        return await call_next(request)
