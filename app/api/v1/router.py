"""Aggregates all /api/v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import admin_imports, products

api_router = APIRouter()
api_router.include_router(products.router)
api_router.include_router(admin_imports.router)
