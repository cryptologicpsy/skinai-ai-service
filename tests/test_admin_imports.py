from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_deps import FixedWindowRateLimiter
from app.core.config import get_settings
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.source import SourceRecord
from app.services import import_service as import_service_module

IMPORT_URL = "/api/v1/admin/imports/products"
IMPORT_FILE_URL = "/api/v1/admin/imports/products/file"


@contextmanager
def override_setting(name: str, value: object) -> Iterator[None]:
    """Temporarily mutate the cached Settings singleton for one test."""

    settings = get_settings()
    original = getattr(settings, name)
    setattr(settings, name, value)
    try:
        yield
    finally:
        setattr(settings, name, original)


def _valid_payload(**overrides: object) -> dict:
    payload = {
        "products": [
            {
                "name": "Fixture Gentle Cleanser",
                "brand": "Fixture Labs",
                "category": "cleanser",
                "description": "Synthetic test fixture product.",
                "external_id": "FIXTURE-SKU-1",
                "ingredients": [
                    {"inci_name": "Aqua", "position": 1},
                    {
                        "inci_name": "Glycerin",
                        "common_name": "Glycerin",
                        "position": 2,
                        "concentration_percent": "5.50",
                    },
                ],
                "source": {
                    "source_name": "Manufacturer website",
                    "source_url": "https://example.test/fixture-cleanser",
                    "verification_status": "verified",
                    "notes": "Synthetic fixture, not a real source.",
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


# --- Auth -------------------------------------------------------------


async def test_import_rejected_without_api_key(client: AsyncClient) -> None:
    response = await client.post(IMPORT_URL, json=_valid_payload())
    assert response.status_code == 401


async def test_import_rejected_with_wrong_api_key(client: AsyncClient) -> None:
    response = await client.post(
        IMPORT_URL, json=_valid_payload(), headers={"X-Admin-Api-Key": "wrong-key"}
    )
    assert response.status_code == 401


async def test_import_disabled_when_admin_api_key_unset(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    with override_setting("admin_api_key", None):
        response = await client.post(IMPORT_URL, json=_valid_payload(), headers=admin_headers)
    assert response.status_code == 503


# --- Valid import -------------------------------------------------------


async def test_valid_import_creates_product_ingredients_and_source(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    response = await client.post(IMPORT_URL, json=_valid_payload(), headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_items"] == 1
    assert body["succeeded_items"] == 1
    assert body["failed_items"] == 0
    assert body["results"][0]["status"] == "created"
    product_id = body["results"][0]["product_id"]
    assert product_id is not None

    product = await db_session.get(Product, uuid.UUID(product_id))
    assert product is not None
    assert product.external_id == "FIXTURE-SKU-1"

    # Queried directly rather than via lazy-loaded relationships: those
    # require an active async greenlet context that a plain `await
    # session.get(...)` followed by attribute access doesn't provide.
    link_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ProductIngredient)
            .where(ProductIngredient.product_id == product.id)
        )
    ).scalar_one()
    assert link_count == 2

    sources = (
        (
            await db_session.execute(
                select(SourceRecord).where(SourceRecord.product_id == product.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(sources) == 1
    assert sources[0].source_name == "Manufacturer website"


# --- Structural validation (422, whole request rejected) ----------------


async def test_missing_required_name_returns_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _valid_payload()
    del payload["products"][0]["name"]
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 422


async def test_blank_inci_name_returns_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _valid_payload()
    payload["products"][0]["ingredients"] = [{"inci_name": "   "}]
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 422


async def test_duplicate_external_id_within_request_returns_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _valid_payload(
        products=[
            {"name": "Product A", "external_id": "DUP"},
            {"name": "Product B", "external_id": "DUP"},
        ]
    )
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 422
    assert "duplicate external_id" in str(response.json())


async def test_exceeds_max_products_limit_returns_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    limit = get_settings().import_max_products
    payload = {"products": [{"name": f"Product {i}"} for i in range(limit + 1)]}
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 422
    assert "exceeding the limit" in str(response.json())


async def test_exceeds_max_ingredients_per_product_returns_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    limit = get_settings().import_max_ingredients_per_product
    payload = _valid_payload()
    payload["products"][0]["ingredients"] = [
        {"inci_name": f"Ingredient {i}"} for i in range(limit + 1)
    ]
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 422
    assert "exceeding the limit" in str(response.json())


async def test_oversized_body_returns_413(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    with override_setting("import_max_json_body_bytes", 10):
        response = await client.post(IMPORT_URL, json=_valid_payload(), headers=admin_headers)
    assert response.status_code == 413


# --- Duplicate avoidance / idempotent re-run -----------------------------


async def test_reimport_same_external_id_updates_instead_of_duplicating(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    first = await client.post(
        IMPORT_URL,
        json=_valid_payload(products=[{"name": "Original Name", "external_id": "EXT-1"}]),
        headers=admin_headers,
    )
    assert first.json()["results"][0]["status"] == "created"

    second = await client.post(
        IMPORT_URL,
        json=_valid_payload(products=[{"name": "Updated Name", "external_id": "EXT-1"}]),
        headers=admin_headers,
    )
    assert second.status_code == 200
    assert second.json()["results"][0]["status"] == "updated"

    count = (
        await db_session.execute(
            select(func.count()).select_from(Product).where(Product.external_id == "EXT-1")
        )
    ).scalar_one()
    assert count == 1


async def test_reimport_without_external_id_falls_back_to_name_and_brand(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    base = {"name": "Fallback Product", "brand": "Fallback Brand"}
    await client.post(
        IMPORT_URL,
        json=_valid_payload(products=[{**base, "description": "v1"}]),
        headers=admin_headers,
    )
    second = await client.post(
        IMPORT_URL,
        json=_valid_payload(products=[{**base, "description": "v2"}]),
        headers=admin_headers,
    )
    assert second.json()["results"][0]["status"] == "updated"

    stmt = select(Product).where(Product.name == "Fallback Product")
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].description == "v2"


async def test_idempotency_key_replay_does_not_reprocess(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    payload = _valid_payload(idempotency_key="retry-key-1")
    first = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert first.status_code == 200
    assert first.json()["idempotent_replay"] is False

    # A different payload under the same key is still a replay: the key
    # identifies the operation, not the content.
    different_payload = _valid_payload(
        idempotency_key="retry-key-1",
        products=[{"name": "Should Not Be Created"}],
    )
    second = await client.post(IMPORT_URL, json=different_payload, headers=admin_headers)
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert second.json()["import_id"] == first.json()["import_id"]

    count = (
        await db_session.execute(
            select(func.count()).select_from(Product).where(Product.name == "Should Not Be Created")
        )
    ).scalar_one()
    assert count == 0


# --- Ingredient normalization --------------------------------------------


async def test_ingredient_name_normalization_merges_case_and_whitespace_variants(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post(
        IMPORT_URL,
        json=_valid_payload(
            products=[{"name": "Product One", "ingredients": [{"inci_name": "Aqua"}]}]
        ),
        headers=admin_headers,
    )
    await client.post(
        IMPORT_URL,
        json=_valid_payload(
            products=[{"name": "Product Two", "ingredients": [{"inci_name": "  AQUA  "}]}]
        ),
        headers=admin_headers,
    )

    stmt = select(Ingredient).where(func.lower(Ingredient.inci_name) == "aqua")
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1


async def test_different_ingredient_names_are_not_merged(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post(
        IMPORT_URL,
        json=_valid_payload(
            products=[
                {
                    "name": "Two Ingredient Product",
                    "ingredients": [{"inci_name": "Aqua"}, {"inci_name": "Water"}],
                }
            ]
        ),
        headers=admin_headers,
    )

    stmt = select(Ingredient).where(Ingredient.inci_name.in_(["Aqua", "Water"]))
    rows = (await db_session.execute(stmt)).scalars().all()
    assert {row.inci_name for row in rows} == {"Aqua", "Water"}


# --- Transaction isolation: one failing item doesn't sink the batch ------


async def test_one_failing_item_does_not_roll_back_the_others(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = import_service_module.ProductImportService._upsert_product

    async def patched(self, item):  # noqa: ANN001
        if item.name == "Boom":
            raise RuntimeError("simulated unexpected database failure")
        return await original(self, item)

    monkeypatch.setattr(import_service_module.ProductImportService, "_upsert_product", patched)

    payload = {
        "products": [
            {"name": "Good A"},
            {"name": "Boom"},
            {"name": "Good B"},
        ]
    }
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed_with_errors"
    assert body["succeeded_items"] == 2
    assert body["failed_items"] == 1

    by_name = {r["name"]: r for r in body["results"]}
    assert by_name["Good A"]["status"] == "created"
    assert by_name["Good B"]["status"] == "created"
    assert by_name["Boom"]["status"] == "failed"
    # Sanitized -- no stack trace / raw exception text leaked to the caller.
    assert "simulated unexpected database failure" not in by_name["Boom"]["error"]
    assert "Traceback" not in by_name["Boom"]["error"]

    count = (
        await db_session.execute(
            select(func.count()).select_from(Product).where(Product.name.in_(["Good A", "Good B"]))
        )
    ).scalar_one()
    assert count == 2


# --- GET import status ---------------------------------------------------


async def test_get_import_status_returns_stored_result(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await client.post(IMPORT_URL, json=_valid_payload(), headers=admin_headers)
    import_id = created.json()["import_id"]

    fetched = await client.get(f"/api/v1/admin/imports/{import_id}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["import_id"] == import_id
    assert fetched.json()["results"] == created.json()["results"]


async def test_get_import_status_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get(f"/api/v1/admin/imports/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


# --- File upload endpoint -------------------------------------------------


async def test_file_upload_endpoint_valid_json(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    raw = json.dumps(_valid_payload()).encode("utf-8")
    response = await client.post(
        IMPORT_FILE_URL,
        files={"file": ("products.json", raw, "application/json")},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["succeeded_items"] == 1


async def test_file_upload_endpoint_rejects_invalid_json(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post(
        IMPORT_FILE_URL,
        files={"file": ("products.json", b"{not valid json", "application/json")},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_source_record_requires_source_name(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _valid_payload()
    payload["products"][0]["source"] = {"source_name": ""}
    response = await client.post(IMPORT_URL, json=payload, headers=admin_headers)
    assert response.status_code == 422


# --- Rate limiter (unit-level, isolated from the shared app singleton) ---


async def test_rate_limiter_blocks_after_limit() -> None:
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60.0)
    await limiter.check("key")
    await limiter.check("key")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check("key")
    assert exc_info.value.status_code == 429


async def test_rate_limiter_tracks_keys_independently() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60.0)
    await limiter.check("key-a")
    await limiter.check("key-b")  # different key, should not be blocked
    with pytest.raises(HTTPException):
        await limiter.check("key-a")
