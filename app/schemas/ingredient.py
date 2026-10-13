"""Ingredient request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class IngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    inci_name: str
    common_name: str | None = None
    description: str | None = None
