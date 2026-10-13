"""Product listing and lookup endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_product_service
from app.schemas.common import PaginatedResponse
from app.schemas.product import ProductRead
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=PaginatedResponse[ProductRead])
async def list_products(
    q: str | None = Query(
        default=None,
        max_length=255,
        description="Free-text search across name, brand, and description",
    ),
    category: str | None = Query(default=None, max_length=100),
    brand: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: ProductService = Depends(get_product_service),
) -> PaginatedResponse[ProductRead]:
    items, total = await service.list_products(
        q=q, category=category, brand=brand, limit=limit, offset=offset
    )
    return PaginatedResponse(
        items=[ProductRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: uuid.UUID,
    service: ProductService = Depends(get_product_service),
) -> ProductRead:
    product = await service.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductRead.model_validate(product)
