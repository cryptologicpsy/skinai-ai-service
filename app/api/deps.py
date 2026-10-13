"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.import_service import ProductImportService
from app.services.product_service import ProductService


async def get_product_service(
    session: AsyncSession = Depends(get_db),
) -> ProductService:
    return ProductService(session)


async def get_import_service(
    session: AsyncSession = Depends(get_db),
) -> ProductImportService:
    return ProductImportService(session)
