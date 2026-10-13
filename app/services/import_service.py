"""Bulk product import orchestration.

Each product in a request is processed in its own SAVEPOINT
(`session.begin_nested()`), so one bad product cannot abort the rest of
the batch -- its savepoint rolls back, its failure is recorded, and
processing continues. The whole request's successful products are
committed together at the end, alongside a ProductImport row recording
the outcome for every item (used by GET /api/v1/admin/imports/{import_id}
and by idempotent retries).

No embeddings are generated here. `description_embedding` /
`Ingredient.description_embedding` are left NULL; populating them is a
separate, future, explicitly-triggered process (see
app/services/embedding.py).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_import import ProductImport
from app.models.product_ingredient import ProductIngredient
from app.models.source import SourceRecord
from app.repositories.import_repository import ImportRepository
from app.repositories.ingredient_repository import IngredientRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.imports import (
    IngredientImportItem,
    ProductImportItem,
    ProductImportItemResult,
    ProductImportRequest,
    ProductImportResponse,
)

logger = logging.getLogger(__name__)


class ProductImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._products = ProductRepository(session)
        self._ingredients = IngredientRepository(session)
        self._imports = ImportRepository(session)

    async def get_import(self, import_id: uuid.UUID) -> ProductImportResponse | None:
        record = await self._imports.get_by_id(import_id)
        if record is None:
            return None
        return _to_response(record, idempotent_replay=False)

    async def run_import(
        self, request: ProductImportRequest, *, source_label: str | None
    ) -> ProductImportResponse:
        if request.idempotency_key:
            existing = await self._imports.get_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                return _to_response(existing, idempotent_replay=True)

        results = [
            await self._import_one(index, item) for index, item in enumerate(request.products)
        ]

        succeeded = sum(1 for r in results if r.status != "failed")
        failed = len(results) - succeeded
        if failed == 0:
            status = "completed"
        elif succeeded > 0:
            status = "completed_with_errors"
        else:
            status = "failed"

        record = self._imports.create(
            idempotency_key=request.idempotency_key,
            status=status,
            total_items=len(request.products),
            succeeded_items=succeeded,
            failed_items=failed,
            source_label=source_label,
            results=[r.model_dump(mode="json") for r in results],
        )

        try:
            await self._session.commit()
        except IntegrityError:
            # Lost a race against a concurrent request with the same
            # idempotency_key, which committed first. Discard this
            # request's work and return the winner's stored result --
            # the whole point of the key is that both callers see one
            # consistent outcome, not two different sets of side effects.
            await self._session.rollback()
            if request.idempotency_key:
                existing = await self._imports.get_by_idempotency_key(request.idempotency_key)
                if existing is not None:
                    return _to_response(existing, idempotent_replay=True)
            raise

        return _to_response(record, idempotent_replay=False)

    async def _import_one(self, index: int, item: ProductImportItem) -> ProductImportItemResult:
        try:
            async with self._session.begin_nested():
                product, created = await self._upsert_product(item)

                for ingredient_item in item.ingredients:
                    await self._upsert_ingredient_link(product, ingredient_item)

                if item.source is not None:
                    self._session.add(
                        SourceRecord(
                            product_id=product.id,
                            source_name=item.source.source_name,
                            source_url=item.source.source_url,
                            verification_status=item.source.verification_status,
                            notes=item.source.notes,
                        )
                    )

                await self._session.flush()
        except ValueError as exc:
            # A recognized business-rule rejection (see _upsert_product) --
            # the message is ours, safe to return to the caller as-is.
            logger.warning("Bulk import: rejected item %d (%r): %s", index, item.name, exc)
            return ProductImportItemResult(
                index=index,
                name=item.name,
                external_id=item.external_id,
                status="failed",
                error=str(exc),
            )
        except Exception:
            # Anything else (DB driver errors, etc.) is logged in full
            # server-side but never echoed back to the API caller.
            logger.exception(
                "Bulk import: unexpected error processing item %d (%r)", index, item.name
            )
            return ProductImportItemResult(
                index=index,
                name=item.name,
                external_id=item.external_id,
                status="failed",
                error="Could not save this product. See server logs for details.",
            )

        return ProductImportItemResult(
            index=index,
            name=item.name,
            external_id=item.external_id,
            status="created" if created else "updated",
            product_id=product.id,
        )

    async def _upsert_product(self, item: ProductImportItem) -> tuple[Product, bool]:
        existing = (
            await self._products.get_by_external_id(item.external_id)
            if item.external_id is not None
            else await self._products.get_by_name_and_brand(item.name, item.brand)
        )

        if existing is not None:
            if (
                item.external_id is not None
                and existing.external_id is not None
                and existing.external_id != item.external_id
            ):
                raise ValueError(
                    f"product '{item.name}' matched an existing product by name/brand "
                    "that already has a different external_id; refusing to overwrite "
                    "the mapping"
                )
            existing.name = item.name
            existing.brand = item.brand
            existing.category = item.category
            existing.description = item.description
            if item.external_id is not None:
                existing.external_id = item.external_id
            return existing, False

        product = Product(
            name=item.name,
            brand=item.brand,
            category=item.category,
            description=item.description,
            external_id=item.external_id,
        )
        self._session.add(product)
        await self._session.flush()
        return product, True

    async def _upsert_ingredient_link(
        self, product: Product, ingredient_item: IngredientImportItem
    ) -> None:
        ingredient, _ = await self._ingredients.get_or_create(
            inci_name=ingredient_item.inci_name,
            common_name=ingredient_item.common_name,
        )

        stmt = select(ProductIngredient).where(
            ProductIngredient.product_id == product.id,
            ProductIngredient.ingredient_id == ingredient.id,
        )
        link = (await self._session.execute(stmt)).scalar_one_or_none()
        if link is None:
            link = ProductIngredient(product_id=product.id, ingredient_id=ingredient.id)
            self._session.add(link)

        link.position = ingredient_item.position
        link.concentration_percent = ingredient_item.concentration_percent


def _to_response(record: ProductImport, *, idempotent_replay: bool) -> ProductImportResponse:
    return ProductImportResponse(
        import_id=record.id,
        status=record.status,  # type: ignore[arg-type]
        total_items=record.total_items,
        succeeded_items=record.succeeded_items,
        failed_items=record.failed_items,
        idempotent_replay=idempotent_replay,
        results=[ProductImportItemResult(**r) for r in record.results],
        created_at=record.created_at,
    )
