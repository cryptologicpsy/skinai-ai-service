"""fix ingredients.inci_name index/constraint to match the ORM model

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 00:00:00

0001 created *both* a named unique constraint (`uq_ingredients_inci_name`)
*and* a separate plain (non-unique) index (`ix_ingredients_inci_name`) on
`ingredients.inci_name`. The SQLAlchemy model has only ever declared one
combined unique index (`unique=True, index=True`), so the separate plain
index was pure redundant write overhead with zero query benefit -- running
`alembic check` against the model surfaced this drift.

This migration removes both and recreates a single unique index with the
same name the model expects, preserving the exact same uniqueness
guarantee and lookup performance with one less index to maintain. Not
destructive: no data is affected, and the operation is fully reversible
(see downgrade).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_ingredients_inci_name", "ingredients", type_="unique")
    op.drop_index("ix_ingredients_inci_name", table_name="ingredients")
    op.create_index("ix_ingredients_inci_name", "ingredients", ["inci_name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ingredients_inci_name", table_name="ingredients")
    op.create_index("ix_ingredients_inci_name", "ingredients", ["inci_name"], unique=False)
    op.create_unique_constraint("uq_ingredients_inci_name", "ingredients", ["inci_name"])
