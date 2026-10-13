"""Database operations for bulk-import job tracking."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_import import ProductImport


class ImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, import_id: uuid.UUID) -> ProductImport | None:
        return await self._session.get(ProductImport, import_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> ProductImport | None:
        stmt = select(ProductImport).where(ProductImport.idempotency_key == idempotency_key)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def create(self, **fields: Any) -> ProductImport:
        record = ProductImport(**fields)
        self._session.add(record)
        return record
