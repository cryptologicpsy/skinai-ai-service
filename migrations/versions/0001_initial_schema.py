"""initial schema: products, ingredients, product_ingredients, source_records

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed at migration-authoring time from the EMBEDDING_DIMENSION setting in
# effect when this migration was generated (default 1536, matching OpenAI's
# text-embedding-3-small). Changing the embedding model/dimension later
# requires a NEW migration that alters these columns -- editing this file
# after it has shipped would not change already-created databases.
_EMBEDDING_DIM = get_settings().embedding_dimension


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_embedding", Vector(_EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("inci_name", sa.String(length=255), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_embedding", Vector(_EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("inci_name", name="uq_ingredients_inci_name"),
    )
    op.create_index("ix_ingredients_inci_name", "ingredients", ["inci_name"])

    op.create_table(
        "product_ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ingredient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("concentration_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("product_id", "ingredient_id", name="uq_product_ingredient"),
    )
    op.create_index("ix_product_ingredients_product_id", "product_ingredients", ["product_id"])
    op.create_index(
        "ix_product_ingredients_ingredient_id", "product_ingredients", ["ingredient_id"]
    )

    op.create_table(
        "source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ingredient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=50),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(product_id IS NOT NULL)::int + (ingredient_id IS NOT NULL)::int = 1",
            name="ck_source_record_single_owner",
        ),
    )
    op.create_index("ix_source_records_product_id", "source_records", ["product_id"])
    op.create_index("ix_source_records_ingredient_id", "source_records", ["ingredient_id"])


def downgrade() -> None:
    op.drop_table("source_records")
    op.drop_table("product_ingredients")
    op.drop_table("ingredients")
    op.drop_table("products")
    op.execute("DROP EXTENSION IF EXISTS vector")
