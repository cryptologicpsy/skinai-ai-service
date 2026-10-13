"""products.external_id + product_imports tracking table

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 00:00:00

Forward-only addition for bulk product import support. Does not alter
anything created by 0001_initial_schema -- `products` gains one new
nullable column plus a unique constraint; a new standalone table is added.

external_id (nullable, unique) is the stable identifier bulk imports use
to update an existing product instead of creating a duplicate on re-run.
A plain UNIQUE constraint is correct here even though the column is
nullable: PostgreSQL treats multiple NULLs as distinct, so any number of
products may still have no external_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_products_external_id", "products", ["external_id"])

    op.create_table(
        "product_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("succeeded_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column(
            "results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_product_imports_idempotency_key"),
    )
    op.create_index("ix_product_imports_status", "product_imports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_product_imports_status", table_name="product_imports")
    op.drop_table("product_imports")
    op.drop_constraint("uq_products_external_id", "products", type_="unique")
    op.drop_column("products", "external_id")
