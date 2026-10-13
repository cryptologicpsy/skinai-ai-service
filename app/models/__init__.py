"""ORM models.

Importing this package registers every model class on `Base.metadata` and
in SQLAlchemy's mapper registry. This must happen before any relationship
using a string-based forward reference (e.g. `Mapped["ProductIngredient"]`)
is resolved, and before Alembic autogeneration can see the full schema.
"""

from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.source import SourceRecord

__all__ = ["Product", "Ingredient", "ProductIngredient", "SourceRecord"]
