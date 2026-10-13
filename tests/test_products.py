from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient


@pytest_asyncio.fixture
async def seeded_products(
    db_session: AsyncSession,
) -> AsyncGenerator[tuple[Product, Product], None]:
    """Synthetic fixture products -- not real SkinAI catalogue data."""

    cleanser = Product(
        name="Fixture Gentle Cleanser",
        brand="Fixture Labs",
        category="cleanser",
        description="Synthetic test fixture product, not a real product.",
    )
    serum = Product(
        name="Fixture Hydrating Serum",
        brand="Fixture Labs",
        category="serum",
        description="Synthetic test fixture product, not a real product.",
    )
    water = Ingredient(inci_name="Fixture Aqua", common_name="Water (fixture)")

    db_session.add_all([cleanser, serum, water])
    await db_session.flush()

    db_session.add(ProductIngredient(product_id=cleanser.id, ingredient_id=water.id, position=1))
    await db_session.commit()

    yield cleanser, serum


async def test_list_products_pagination(
    client: AsyncClient, seeded_products: tuple[Product, Product]
) -> None:
    response = await client.get("/api/v1/products", params={"limit": 1, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 0


async def test_list_products_filter_by_category(
    client: AsyncClient, seeded_products: tuple[Product, Product]
) -> None:
    response = await client.get("/api/v1/products", params={"category": "serum"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Fixture Hydrating Serum"


async def test_list_products_search_query(
    client: AsyncClient, seeded_products: tuple[Product, Product]
) -> None:
    response = await client.get("/api/v1/products", params={"q": "Gentle"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Fixture Gentle Cleanser"


async def test_get_product_by_id(
    client: AsyncClient, seeded_products: tuple[Product, Product]
) -> None:
    cleanser, _serum = seeded_products
    response = await client.get(f"/api/v1/products/{cleanser.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(cleanser.id)


async def test_get_product_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/products/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_products_invalid_limit(client: AsyncClient) -> None:
    response = await client.get("/api/v1/products", params={"limit": 0})
    assert response.status_code == 422
