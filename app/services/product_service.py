"""Business logic for products.

Thin today (it mostly delegates to the repository); kept separate from the
repository so validation, authorization, or cross-entity logic has a clear
home as the service grows, without the API layer talking to SQLAlchemy
directly.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.repositories.product_repository import ProductRepository


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = ProductRepository(session)

    async def list_products(
        self,
        *,
        q: str | None,
        category: str | None,
        brand: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        return await self._repository.list_products(
            q=q, category=category, brand=brand, limit=limit, offset=offset
        )

    async def get_product(self, product_id: uuid.UUID) -> Product | None:
        return await self._repository.get_by_id(product_id)
