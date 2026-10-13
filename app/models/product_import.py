"""Bulk product import job tracking."""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, id_column


class ProductImport(Base, TimestampMixin):
    """A single bulk-import request and its outcome.

    One row per call to POST /api/v1/admin/imports/products(/file),
    created once processing finishes (not updated mid-flight -- imports in
    this service are small and synchronous, so there is no useful
    intermediate "running" state to persist). `idempotency_key` lets a
    client safely retry the exact same submission: a repeat with the same
    key returns this stored result instead of reprocessing.
    """

    __tablename__ = "product_imports"

    id: Mapped[uuid.UUID] = id_column()
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    # "completed" | "completed_with_errors" | "failed"
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded_items: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failed_items: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # e.g. "json-body" or the uploaded filename, for operator debugging only.
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Per-item results: [{"index", "name", "external_id", "status",
    # "product_id", "error"}, ...]. Sanitized (no SQL/stack traces) before
    # being stored here -- this is served back verbatim by the GET endpoint.
    results: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ProductImport(id={self.id!r}, status={self.status!r})"
