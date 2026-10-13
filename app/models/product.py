"""Product model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base
from app.models.base import TimestampMixin, id_column

if TYPE_CHECKING:
    from app.models.product_ingredient import ProductIngredient
    from app.models.source import SourceRecord

_EMBEDDING_DIM = get_settings().embedding_dimension


class Product(Base, TimestampMixin):
    """A skincare product."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = id_column()
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Embedding of `description` (and/or other product text) for semantic
    # search. Populated later by an embedding service; nullable until then.
    description_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(_EMBEDDING_DIM), nullable=True
    )

    ingredient_links: Mapped[list[ProductIngredient]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    sources: Mapped[list[SourceRecord]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Product(id={self.id!r}, name={self.name!r})"
