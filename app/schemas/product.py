"""Product request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductRead(BaseModel):
    """Public representation of a product.

    Deliberately excludes `description_embedding`: it is a large numeric
    vector with no value to API consumers and shouldn't be serialized on
    every list/detail response.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime
