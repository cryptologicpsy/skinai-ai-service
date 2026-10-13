"""Database operations for products."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class ProductRepository:
    """Encapsulates all product queries. No business logic here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_products(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        stmt = select(Product)
        count_stmt = select(func.count()).select_from(Product)

        if category:
            stmt = stmt.where(Product.category == category)
            count_stmt = count_stmt.where(Product.category == category)
        if brand:
            stmt = stmt.where(Product.brand == brand)
            count_stmt = count_stmt.where(Product.brand == brand)
        if q:
            pattern = f"%{q}%"
            search_filter = or_(
                Product.name.ilike(pattern),
                Product.brand.ilike(pattern),
                Product.description.ilike(pattern),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        stmt = stmt.order_by(Product.name).limit(limit).offset(offset)

        total = (await self._session.execute(count_stmt)).scalar_one()
        items = (await self._session.execute(stmt)).scalars().all()
        return list(items), total

    async def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return await self._session.get(Product, product_id)

    async def get_by_external_id(self, external_id: str) -> Product | None:
        stmt = select(Product).where(Product.external_id == external_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_name_and_brand(self, name: str, brand: str | None) -> Product | None:
        """Best-effort fallback match for products imported without an
        external_id. Case-insensitive on both fields; NULL brand matches
        NULL brand. Not DB-enforced (no uniqueness constraint on
        name+brand) -- supply external_id for guaranteed idempotency.
        """

        stmt = select(Product).where(func.lower(Product.name) == name.lower())
        if brand is None:
            stmt = stmt.where(Product.brand.is_(None))
        else:
            stmt = stmt.where(func.lower(Product.brand) == brand.lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()
