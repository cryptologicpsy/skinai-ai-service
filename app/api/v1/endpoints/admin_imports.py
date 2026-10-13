"""Admin: bulk product import endpoints.

Every route here requires a valid X-Admin-Api-Key header and is rate
limited (see app/api/admin_deps.py). These are internal administrative
operations, not part of the public product API -- see README "Security
notes" before this service is reachable from anywhere beyond
127.0.0.1 on the VPS.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.admin_deps import rate_limit_admin_imports, require_admin_api_key
from app.api.deps import get_import_service
from app.core.config import get_settings
from app.schemas.imports import ProductImportRequest, ProductImportResponse
from app.services.import_service import ProductImportService

router = APIRouter(
    prefix="/admin/imports",
    tags=["admin"],
    dependencies=[Depends(require_admin_api_key)],
)


@router.post(
    "/products",
    response_model=ProductImportResponse,
    dependencies=[Depends(rate_limit_admin_imports)],
)
async def import_products(
    request: ProductImportRequest,
    service: ProductImportService = Depends(get_import_service),
) -> ProductImportResponse:
    """Bulk create/update products from a JSON body.

    Always returns 200 once the request itself is valid and processed --
    per-product outcomes (created/updated/failed) are in `results`. See
    docs/BULK_IMPORT.md for the full payload format.
    """

    return await service.run_import(request, source_label="json-body")


@router.post(
    "/products/file",
    response_model=ProductImportResponse,
    dependencies=[Depends(rate_limit_admin_imports)],
)
async def import_products_file(
    file: UploadFile,
    service: ProductImportService = Depends(get_import_service),
) -> ProductImportResponse:
    """Identical to POST /products, but the same JSON document is supplied
    as an uploaded file instead of the request body.
    """

    settings = get_settings()
    # Bounded read: never materialize more than limit+1 bytes in memory,
    # regardless of how large the uploaded file actually is.
    raw = await file.read(settings.import_max_json_body_bytes + 1)
    if len(raw) > settings.import_max_json_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Uploaded file exceeds the {settings.import_max_json_body_bytes}-byte "
                "limit for bulk imports."
            ),
        )

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Uploaded file is not valid JSON: {exc}",
        ) from exc

    try:
        import_request = ProductImportRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(include_url=False),
        ) from exc

    return await service.run_import(
        import_request, source_label=f"file:{file.filename or 'unnamed'}"
    )


@router.get("/{import_id}", response_model=ProductImportResponse)
async def get_import(
    import_id: uuid.UUID,
    service: ProductImportService = Depends(get_import_service),
) -> ProductImportResponse:
    result = await service.get_import(import_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found")
    return result
