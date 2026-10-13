"""Database operations for ingredients."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient import Ingredient


class IngredientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_inci_name_ci(self, inci_name: str) -> Ingredient | None:
        """Case-insensitive exact match.

        Deliberately case-insensitive (not fuzzy/synonym matching): "Aqua"
        and "AQUA" resolve to the same ingredient, but "Aqua" and "Water"
        never do. Whitespace is assumed already normalized by the caller
        (see app.schemas.imports.normalize_text).
        """

        stmt = select(Ingredient).where(func.lower(Ingredient.inci_name) == inci_name.lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_or_create(
        self, *, inci_name: str, common_name: str | None
    ) -> tuple[Ingredient, bool]:
        """Return (ingredient, created). Race-safe: if a concurrent import
        creates the same (case-insensitive) name first, the unique
        constraint on inci_name catches it and this falls back to the row
        that won, instead of erroring the whole product out.
        """

        existing = await self.get_by_inci_name_ci(inci_name)
        if existing is not None:
            return existing, False

        ingredient = Ingredient(inci_name=inci_name, common_name=common_name)
        try:
            async with self._session.begin_nested():
                self._session.add(ingredient)
                await self._session.flush()
        except IntegrityError:
            existing = await self.get_by_inci_name_ci(inci_name)
            if existing is None:
                raise
            return existing, False
        return ingredient, True
