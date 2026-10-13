"""Ingredient model."""

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


class Ingredient(Base, TimestampMixin):
    """A cosmetic ingredient, identified by its INCI name."""

    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = id_column()
    inci_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    common_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Embedding of `description` / general knowledge text about this
    # ingredient, for semantic search over skincare knowledge.
    description_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(_EMBEDDING_DIM), nullable=True
    )

    product_links: Mapped[list[ProductIngredient]] = relationship(back_populates="ingredient")
    sources: Mapped[list[SourceRecord]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Ingredient(id={self.id!r}, inci_name={self.inci_name!r})"
