"""Source / verification metadata for products and ingredients."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, id_column

if TYPE_CHECKING:
    from app.models.ingredient import Ingredient
    from app.models.product import Product


class SourceRecord(Base, TimestampMixin):
    """Where a piece of product/ingredient data came from, and its
    verification status.

    Exactly one of `product_id` / `ingredient_id` must be set, enforced by
    a CHECK constraint, so a single table can back both entity types
    without a loosely-typed polymorphic foreign key.
    """

    __tablename__ = "source_records"
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL)::int + (ingredient_id IS NOT NULL)::int = 1",
            name="ck_source_record_single_owner",
        ),
    )

    id: Mapped[uuid.UUID] = id_column()
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # unverified | verified | disputed -- kept as a plain string rather than
    # a DB enum so new statuses don't require a migration.
    verification_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unverified", server_default="unverified"
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped[Product | None] = relationship(back_populates="sources")
    ingredient: Mapped[Ingredient | None] = relationship(back_populates="sources")
