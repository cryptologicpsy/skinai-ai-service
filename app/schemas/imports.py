"""Bulk product import request/response schemas.

Validation here enforces structure (required fields, lengths, numeric
ranges) and request-wide limits (how many products/ingredients, duplicate
external_ids within one request). Anything that fails here never reaches
the database and is rejected as a single 422 for the whole request, with
field-level error messages from Pydantic. Business/database-level failures
on an individual, structurally-valid product (e.g. an unexpected
constraint violation) are a different thing entirely: those are reported
per item in ProductImportResponse.results with status="failed", inside an
HTTP 200 response -- see app/services/import_service.py.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import get_settings

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Trim and collapse internal whitespace.

    Used both for validation (so "  Aqua" and "Aqua " aren't treated as
    different inputs) and, for ingredient names specifically, as the
    canonical form used to match an existing Ingredient case-insensitively
    without merging genuinely different names (see
    app/repositories/ingredient_repository.py).
    """

    return _WHITESPACE_RE.sub(" ", value.strip())


class SourceImportInput(BaseModel):
    """Provenance/verification metadata for one imported product.

    Maps to a new SourceRecord row per product per import run (an
    append-only audit trail, not an upsert) -- see import_service.py.
    """

    source_name: str = Field(..., min_length=1, max_length=255)
    source_url: str | None = Field(default=None, max_length=2048)
    verification_status: str = Field(default="unverified", max_length=50)
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("source_name", "notes", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return normalize_text(value) if isinstance(value, str) else value

    @field_validator("verification_status", mode="before")
    @classmethod
    def _normalize_status(cls, value: object) -> object:
        return normalize_text(value).lower() if isinstance(value, str) else value

    @field_validator("source_name")
    @classmethod
    def _source_name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("source_name must not be blank")
        return value


class IngredientImportItem(BaseModel):
    """One entry in a product's INCI ingredient list."""

    inci_name: str = Field(..., min_length=1, max_length=255)
    common_name: str | None = Field(default=None, max_length=255)
    position: int | None = Field(default=None, ge=0, description="Order in the INCI list")
    concentration_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )

    @field_validator("inci_name", "common_name", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return normalize_text(value) if isinstance(value, str) else value

    @field_validator("inci_name")
    @classmethod
    def _inci_name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("inci_name must not be blank")
        return value


class ProductImportItem(BaseModel):
    """One product to create or update."""

    name: str = Field(..., min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=20_000)
    external_id: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Stable identifier from the source catalogue. When provided, "
            "re-running the same import updates this product instead of "
            "creating a duplicate. Strongly recommended for anything you "
            "intend to re-import."
        ),
    )
    ingredients: list[IngredientImportItem] = Field(default_factory=list)
    source: SourceImportInput | None = None

    @field_validator("name", "brand", "category", "external_id", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return normalize_text(value) if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("external_id")
    @classmethod
    def _blank_external_id_is_none(cls, value: str | None) -> str | None:
        # "" after stripping (e.g. the source sent whitespace) means "not
        # provided", not a literal empty-string identifier.
        return value or None

    @model_validator(mode="after")
    def _check_ingredient_limit(self) -> ProductImportItem:
        limit = get_settings().import_max_ingredients_per_product
        if len(self.ingredients) > limit:
            raise ValueError(
                f"product '{self.name}' has {len(self.ingredients)} ingredients, "
                f"exceeding the limit of {limit} per product"
            )
        return self


class ProductImportRequest(BaseModel):
    """Body of POST /api/v1/admin/imports/products(/file)."""

    products: list[ProductImportItem] = Field(..., min_length=1)
    idempotency_key: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Optional client-supplied key. Re-submitting the same key "
            "returns the original import's stored result instead of "
            "reprocessing -- use this for safe retries."
        ),
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def _strip_idempotency_key(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_text(value) or None
        return value

    @model_validator(mode="after")
    def _check_limits_and_duplicates(self) -> ProductImportRequest:
        settings = get_settings()
        if len(self.products) > settings.import_max_products:
            raise ValueError(
                f"request contains {len(self.products)} products, exceeding the "
                f"limit of {settings.import_max_products}"
            )

        seen: set[str] = set()
        for item in self.products:
            if item.external_id is None:
                continue
            if item.external_id in seen:
                raise ValueError(
                    f"duplicate external_id '{item.external_id}' within the same request"
                )
            seen.add(item.external_id)
        return self


class ProductImportItemResult(BaseModel):
    index: int
    name: str
    external_id: str | None = None
    status: Literal["created", "updated", "failed"]
    product_id: uuid.UUID | None = None
    error: str | None = None


class ProductImportResponse(BaseModel):
    import_id: uuid.UUID
    status: Literal["completed", "completed_with_errors", "failed"]
    total_items: int
    succeeded_items: int
    failed_items: int
    idempotent_replay: bool = False
    results: list[ProductImportItemResult]
    created_at: datetime | None = None
