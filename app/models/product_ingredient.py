"""Association model linking products to their ingredients."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, id_column

if TYPE_CHECKING:
    from app.models.ingredient import Ingredient
    from app.models.product import Product


class ProductIngredient(Base, TimestampMixin):
    """One ingredient's entry in a product's ingredient list.

    `position` captures ordering within the label (lower = listed earlier,
    i.e. typically higher concentration under INCI labelling conventions).
    `concentration_percent` is optional, since it is rarely public for
    cosmetic products.
    """

    __tablename__ = "product_ingredients"
    __table_args__ = (
        UniqueConstraint("product_id", "ingredient_id", name="uq_product_ingredient"),
    )

    id: Mapped[uuid.UUID] = id_column()
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    concentration_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    product: Mapped[Product] = relationship(back_populates="ingredient_links")
    ingredient: Mapped[Ingredient] = relationship(back_populates="product_links")
