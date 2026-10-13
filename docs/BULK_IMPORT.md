# Bulk product import

**These endpoints are internal administrative tooling, not part of the
public product API.** They require a shared-secret `X-Admin-Api-Key`
header (see "Authentication" below) and are disabled by default. Do not
call them from a browser frontend. See the README's "Security notes"
before relying on this for anything beyond local/internal use.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/admin/imports/products` | Bulk create/update products from a JSON request body |
| `POST` | `/api/v1/admin/imports/products/file` | Identical, but the JSON is an uploaded file (`multipart/form-data`, field name `file`) |
| `GET` | `/api/v1/admin/imports/{import_id}` | Fetch the stored result of a previous import |

All three require the `X-Admin-Api-Key` header. If `ADMIN_API_KEY` is not
set in the service's environment, every one of these returns `503` --
there is no default key.

## Request format

```json
{
  "idempotency_key": "catalog-sync-2026-10-14-001",
  "products": [
    {
      "external_id": "SUPPLIER-SKU-10234",
      "name": "Gentle Hydrating Cleanser",
      "brand": "Example Skincare Co",
      "category": "cleanser",
      "description": "A fragrance-free gel cleanser for sensitive skin.",
      "ingredients": [
        { "inci_name": "Aqua", "position": 1 },
        { "inci_name": "Glycerin", "common_name": "Glycerin", "position": 2, "concentration_percent": "5.00" },
        { "inci_name": "Sodium Cocoyl Isethionate", "position": 3 },
        { "inci_name": "Panthenol", "common_name": "Pro-Vitamin B5", "position": 4, "concentration_percent": "0.50" }
      ],
      "source": {
        "source_name": "Supplier technical data sheet",
        "source_url": "https://supplier.example.com/tds/10234",
        "verification_status": "verified",
        "notes": "TDS dated 2026-09-01, provided directly by supplier."
      }
    }
  ]
}
```

### Field reference

**Top level**

| Field | Required | Notes |
|---|---|---|
| `products` | yes | 1 to `IMPORT_MAX_PRODUCTS` (default 500) items |
| `idempotency_key` | no | Re-submitting the same key returns the original stored result instead of reprocessing. Recommended for anything run by a script/cron, since it makes retries after a timeout safe. The key defines the operation -- if you reuse a key with different `products`, you get back the *first* run's result, not an error. |

**Each entry in `products`**

| Field | Required | Notes |
|---|---|---|
| `name` | yes | 1-255 chars |
| `brand` | no | max 255 chars |
| `category` | no | max 100 chars |
| `description` | no | max 20,000 chars |
| `external_id` | no, but recommended | max 255 chars. Stable ID from your source catalogue. When given, re-importing the same `external_id` **updates** that product instead of creating a duplicate. Without it, a best-effort case-insensitive match on `(name, brand)` is used instead -- real idempotency requires `external_id`. |
| `ingredients` | no | 0 to `IMPORT_MAX_INGREDIENTS_PER_PRODUCT` (default 100) items |
| `source` | no | provenance/verification metadata; creates one `SourceRecord` row per product **per import run** (an append-only audit log, not an upsert -- re-importing the same product with source info adds another source record each time) |

**Each entry in `ingredients`**

| Field | Required | Notes |
|---|---|---|
| `inci_name` | yes | 1-255 chars. Matched to existing ingredients case-insensitively after trimming/collapsing whitespace (`"  Aqua "` and `"AQUA"` resolve to the same ingredient) -- but never fuzzy/synonym-matched (`"Aqua"` and `"Water"` always stay distinct ingredients). |
| `common_name` | no | max 255 chars. Only used when *creating* a new ingredient; re-importing a known INCI name does not overwrite an existing `common_name`. |
| `position` | no | non-negative integer; order in the INCI list |
| `concentration_percent` | no | decimal 0-100, max 2 decimal places (matches the database column) |

**`source` object**

| Field | Required | Notes |
|---|---|---|
| `source_name` | yes | 1-255 chars |
| `source_url` | no | max 2048 chars |
| `verification_status` | no | free text, default `"unverified"` (also commonly `"verified"` / `"disputed"`) |
| `notes` | no | max 10,000 chars |

## Response format

```json
{
  "import_id": "b3b2c6b0-4f1a-4e9e-9c7a-2f6b2a9d9e10",
  "status": "completed",
  "total_items": 1,
  "succeeded_items": 1,
  "failed_items": 0,
  "idempotent_replay": false,
  "results": [
    {
      "index": 0,
      "name": "Gentle Hydrating Cleanser",
      "external_id": "SUPPLIER-SKU-10234",
      "status": "created",
      "product_id": "0b9e3a2a-6c3e-4e4a-9f36-9d6a6a5b7a11",
      "error": null
    }
  ],
  "created_at": "2026-10-14T12:00:00Z"
}
```

`status` is one of `completed` (everything succeeded), `completed_with_errors`
(some products failed), or `failed` (all products failed). **The HTTP
status code is 200 in all three cases** as long as the request itself was
structurally valid -- check the `status` and per-item `results` fields,
not just the HTTP status code, to know what actually happened. A 4xx/5xx
means the request itself was rejected (bad shape, auth failure, payload
too large) before any product was processed.

Each entry in `results` has `status` of `created`, `updated`, or `failed`.
A `failed` entry's `error` is always a short, sanitized message -- never a
raw SQL error or stack trace.

## What gets rejected before any database write (HTTP 422)

Structural problems reject the *entire* request, with no partial
processing:

- Missing/blank required fields (`name`, `inci_name`, `source_name` when
  `source` is present).
- More than `IMPORT_MAX_PRODUCTS` products, or more than
  `IMPORT_MAX_INGREDIENTS_PER_PRODUCT` ingredients on one product.
- Two products in the same request with the same (non-null) `external_id`.
- `concentration_percent` outside 0-100 or with more than 2 decimal places.

## What gets reported as a per-item failure instead (HTTP 200)

An unexpected error saving one specific, structurally-valid product (for
example, a database-level problem) fails only that item -- its own
database work is rolled back via a savepoint, but every other product in
the same request is unaffected and still gets committed.

## Limits

Configured via environment variables (see `.env.example`):

| Setting | Default |
|---|---|
| `IMPORT_MAX_PRODUCTS` | 500 |
| `IMPORT_MAX_INGREDIENTS_PER_PRODUCT` | 100 |
| `IMPORT_MAX_JSON_BODY_BYTES` | 2,000,000 (~2 MB) |
| `ADMIN_IMPORT_RATE_LIMIT_PER_MINUTE` | 10 requests/minute per API key |

Requests whose `Content-Length` exceeds `IMPORT_MAX_JSON_BODY_BYTES` are
rejected with `413` before any JSON parsing happens.

## Authentication

Every admin endpoint requires:

```
X-Admin-Api-Key: <value of ADMIN_API_KEY>
```

- If `ADMIN_API_KEY` is unset in the environment: every request gets
  `503` ("Admin API is not configured"), regardless of what header is
  sent. This is the default -- admin endpoints are closed until an
  operator deliberately sets a key.
- If set, the header must match exactly (compared in constant time); a
  missing or wrong key gets `401`.
- This is a single shared secret, not per-user authorization. Treat it
  like any other production credential: generate it with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`, store it
  only in `.env` / GitHub Environment secrets, and never put it in
  frontend JavaScript, a mobile app bundle, or any other client-visible
  code.

## Embeddings

Bulk import never generates embeddings. `description_embedding` is left
`NULL` for every created/updated product and ingredient. Populating it is
a separate, explicitly-triggered, not-yet-implemented process (see
`app/services/embedding.py`).

## Example: curl

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/imports/products \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @products.json
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/imports/products/file \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY" \
  -F "file=@products.json;type=application/json"
```

```bash
curl http://127.0.0.1:8000/api/v1/admin/imports/<import_id> \
  -H "X-Admin-Api-Key: $ADMIN_API_KEY"
```
