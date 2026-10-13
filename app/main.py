"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

import app.models  # noqa: F401  -- registers all ORM models before first use
from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import MaxBodySizeMiddleware

configure_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "SkinAI AI backend service: an independent Python/FastAPI service "
        "for skincare product, ingredient, and (future) embedding/RAG "
        "functionality. Does not replace or communicate with the existing "
        "Node.js/Express + MongoDB backend."
    ),
)

app.add_middleware(MaxBodySizeMiddleware, path_prefix=f"{settings.api_v1_prefix}/admin/imports")

if settings.cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)
