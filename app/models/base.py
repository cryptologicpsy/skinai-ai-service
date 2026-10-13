"""Shared model mixins and column helpers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds server-managed created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def id_column() -> Mapped[uuid.UUID]:
    """Primary key column: a client-generated UUID4.

    Generated in Python (not via a Postgres default) so IDs are available
    before a row is flushed, without requiring the pgcrypto extension.
    """

    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
