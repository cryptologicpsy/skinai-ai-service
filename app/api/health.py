"""Unversioned health/readiness endpoints.

Kept outside /api/v1 since they are infrastructure endpoints (used by
orchestrators, load balancers, etc.), not part of the versioned API
contract.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.session import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check")
async def health() -> dict[str, str]:
    """Process is up. Does not touch the database."""

    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness check")
async def readiness() -> JSONResponse:
    """Process is up AND the database is reachable."""

    if await check_database_connection():
        return JSONResponse(status_code=200, content={"status": "ok", "database": "reachable"})
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "database": "unreachable"},
    )
