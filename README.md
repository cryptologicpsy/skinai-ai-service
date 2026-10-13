# skinai-ai-service

[![CI](https://github.com/cryptologicpsy/skinai-ai-service/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cryptologicpsy/skinai-ai-service/actions/workflows/ci.yml)

An independent Python/FastAPI backend for SkinAI's AI-related functionality
(product/ingredient data, and future embeddings/RAG over skincare
knowledge).

## Status / limitations

This is an initial foundation, not a complete product:

- **No authentication is implemented.** Every endpoint is unauthenticated.
  Do not expose this service to the public internet or to untrusted
  networks until auth (and, if needed, rate limiting) is added.
- **No embedding provider or RAG pipeline is implemented.** `app/services/embedding.py`
  and `app/services/rag.py` define the interfaces future implementations
  will satisfy, and the database schema already has pgvector columns to
  store embeddings in, but nothing currently generates embeddings or calls
  any external AI API. In particular, **the app never calls an embedding
  provider at startup** -- only an explicit future call to
  `EmbeddingService.embed_text()`/`embed_batch()` would, and today that
  raises `NotImplementedError`.
- **No product/ingredient data is seeded.** There is no real or synthetic
  product catalogue in this repository. Test fixtures use clearly-labeled
  synthetic data (e.g. "Fixture Gentle Cleanser" / brand "Fixture Labs")
  that could never be mistaken for a real product.
- Write endpoints (create/update product or ingredient data) are not
  implemented yet -- only read (list/search/get) endpoints exist.

## Tech stack

- Python 3.12+, FastAPI
- PostgreSQL + the [pgvector](https://github.com/pgvector/pgvector) extension
- SQLAlchemy 2.x (async, `asyncpg` driver) + Alembic migrations
- Pydantic v2 / pydantic-settings
- pytest + HTTPX for testing
- Docker / Docker Compose
- Ruff for linting and formatting

## Project structure

```
app/
  main.py                   FastAPI app wiring (routers, middleware)
  api/
    health.py                /health, /health/ready (unversioned)
    deps.py                  shared FastAPI dependencies
    v1/
      router.py              aggregates /api/v1 routers
      endpoints/products.py  product list/search/get endpoints
  core/
    config.py                Settings (env vars / .env)
    logging.py                logging setup
  db/
    base.py                  SQLAlchemy declarative Base
    session.py                async engine/session, readiness check
  models/                    SQLAlchemy ORM models
  schemas/                   Pydantic request/response schemas
  services/                  business logic + embedding/RAG interfaces
  repositories/              database query layer
migrations/                 Alembic environment + versions
tests/                       pytest suite (health, db, product endpoints)
compose.yaml                 db + app + tests services
Dockerfile                   multi-stage build (base / test / runtime)
```

Layering: **api -> services -> repositories -> models**. Endpoints depend
on services (business logic), services depend on repositories (queries),
repositories depend on models. This keeps request validation, business
rules, and SQL concerns separable as the service grows.

## Data model

Defined in `app/models/` and created by `migrations/versions/0001_initial_schema.py`:

- **products** -- name, brand, category, description, plus
  `description_embedding vector(N)` for semantic search (nullable until an
  embedding provider is wired up).
- **ingredients** -- INCI name (unique), common name, description, plus
  its own `description_embedding vector(N)` for searching skincare
  knowledge.
- **product_ingredients** -- many-to-many join between products and
  ingredients, with `position` (order in the label) and optional
  `concentration_percent`.
- **source_records** -- where a product's or ingredient's data came from
  and its verification status (`unverified` / `verified` / `disputed`,
  free-form so new statuses don't need a migration). Each row references
  *either* a product *or* an ingredient (enforced by a CHECK constraint),
  not a loosely-typed polymorphic key.

### Embedding dimension

`EMBEDDING_DIMENSION` (default `1536`) configures the width of every
`vector(N)` column. 1536 is only a default because it matches a common
off-the-shelf model (OpenAI's `text-embedding-3-small`); no such model is
actually called anywhere in this codebase yet. If/when you adopt a
different embedding model, update `EMBEDDING_DIMENSION` **and** write a new
Alembic migration that alters the vector columns -- pgvector columns have a
fixed dimension, so just changing the env var does not resize existing
columns.

## Getting started (Docker Compose)

1. Copy the example environment file and set a real password:
   ```bash
   cp .env.example .env
   # edit .env and set POSTGRES_PASSWORD to something non-default
   ```
2. Start the database and app:
   ```bash
   docker compose up --build
   ```
   `app` waits for `db`'s healthcheck before starting. Postgres data
   persists in the `db_data` named volume; the database port is **not**
   published to the host by default (see `compose.yaml`) -- only the `app`
   service (port 8000) is reachable from outside the Docker network.
3. Apply database migrations (first run, and after pulling new migrations):
   ```bash
   docker compose run --rm app alembic upgrade head
   ```
4. Visit `http://localhost:8000/health`, `http://localhost:8000/health/ready`,
   and `http://localhost:8000/docs` (interactive API docs).

## Running tests

Tests run against a real Postgres + pgvector database (there is no SQLite
fallback, since pgvector types aren't supported there) using a dedicated
`skinai_test` database created automatically by `docker/initdb/01-create-test-db.sh`
the first time the `db` container initializes.

```bash
docker compose up -d db
docker compose run --rm tests
```

The `tests` service builds from the Dockerfile's `test` stage (adds
pytest/httpx/ruff on top of the runtime image) and is not started by a
plain `docker compose up`; it only runs when invoked explicitly or via
`--profile test`. Each test session applies Alembic migrations against
`skinai_test` (so tests exercise the real migration path, not just
`create_all()`), and tables are truncated between tests for isolation.

### Running tests locally without Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt

# point at any reachable Postgres+pgvector instance, e.g. the compose db
# service with its port temporarily published, or a local install:
export DATABASE_URL=postgresql+asyncpg://skinai:changeme@localhost:5432/skinai_test

pytest
```

## Linting

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format .
```

## CI/CD

Full details (test database lifecycle, required GitHub settings, secret
management, rollback, troubleshooting) live in
[`docs/CI_CD.md`](docs/CI_CD.md). Summary:

**CI** (`.github/workflows/ci.yml`, runs on every push/PR to `main` and via
manual dispatch):

- `ruff check .` and `ruff format --check .` (Python 3.12).
- Builds both Dockerfile targets (`runtime` and `test`).
- Starts the same `pgvector/pgvector:pg16` database defined in
  `compose.yaml`, waits for its healthcheck, and confirms the `vector`
  extension and the `skinai_test` database are ready.
- Applies Alembic migrations to the `skinai` database via
  `docker compose run --rm app alembic upgrade head` (the same command
  documented above), then runs the full pytest suite against the separate
  `skinai_test` database via `docker compose run --rm tests pytest -v`
  (reusing the `tests` Compose service -- see "Running tests").
- Always tears down containers/volumes for that job, success or failure.

CI does not touch any production database and requires no repository
secrets.

**CD** (`.github/workflows/deploy.yml`) is a **disabled-by-default
scaffold** -- see `docs/CI_CD.md` for the full prerequisite list. It never
deploys automatically:

- Trigger: manual `workflow_dispatch` only, requiring you to type `deploy`
  into a confirmation input.
- Guarded by an explicit `main`-branch check *and* a GitHub Environment
  named `production` (configure this in **Settings -> Environments**, with
  required reviewers and "Deployment branches" restricted to `main` -- see
  `docs/CI_CD.md`).
- Today, running it will always stop at a "Check deployment configuration"
  step and report exactly which secrets/variables
  (`DEPLOY_SSH_HOST`, `DEPLOY_SSH_USER`, `DEPLOY_PATH`,
  `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_SSH_KNOWN_HOSTS`, ...) are missing,
  because no VPS hostname, SSH credentials, or deployment path have been
  configured yet. No network connection is attempted.
- Once those prerequisites exist and have been reviewed, the (currently
  commented-out) deploy steps pull an image tagged by commit SHA over SSH
  to a pinned host key, run migrations against this service's own
  database only, restart only this service's container, and verify
  `/health/ready` -- never touching the existing SkinAI/BeautyFlow
  containers or databases on the VPS.
- Rollback is manual and deliberate (re-deploy a previous commit SHA's
  image), not a one-click action -- see `docs/CI_CD.md`.

**This service has no authentication.** CI validates it builds and
passes tests; it does not make the service safe to expose publicly. Keep
it internal-only (no public ports, no public reverse-proxy route) until
auth is implemented -- see "Security notes" below.

## Database migrations

Migrations live in `migrations/versions/`. The Alembic environment
(`migrations/env.py`) reads the connection string from application
settings (`DATABASE_URL`), not from `alembic.ini`, and supports the async
engine via `connection.run_sync(...)`.

Common commands (run inside the `app` container or a local venv with
`DATABASE_URL` set):

```bash
alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back one migration
alembic revision --autogenerate -m "describe change"   # generate a new migration
```

Always review autogenerated migrations before applying them -- Alembic's
diffing is a starting point, not a guarantee, especially around pgvector
columns and CHECK constraints.

## Configuration

All configuration is via environment variables (see `.env.example` for the
full list with explanations):

| Variable | Purpose |
|---|---|
| `APP_NAME`, `APP_ENV`, `LOG_LEVEL` | basic app/runtime metadata |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_TEST_DB` | consumed by the `db` compose service |
| `DATABASE_URL` | async SQLAlchemy connection string used by the app and Alembic |
| `EMBEDDING_DIMENSION` | pgvector column width (see above) |
| `CORS_ORIGINS` | JSON array of allowed origins; empty means no CORS middleware is installed |

No API keys, passwords, or secrets are hardcoded anywhere in the codebase;
`.env` is git-ignored and `.env.example` contains placeholders only.

## Security notes

- The database is only reachable from other containers on the internal
  Docker network -- its port is not published to the host by default.
- The application container runs as a non-root user (`runtime` stage in
  `Dockerfile`).
- No secrets are baked into the image; everything required at runtime is
  injected via environment variables / `.env`.
- This service currently has **no authentication or authorization** --
  treat it as internal-only until that's added, and do not route public
  traffic to it.
- Test fixtures use obviously-synthetic data (e.g. "Fixture Labs") so there
  is no risk of fixtures being mistaken for real product data, user data,
  or a production dump.

## Architectural choices worth knowing about

- **Async end-to-end**: FastAPI + SQLAlchemy 2.0 async + `asyncpg` +
  async-aware Alembic. Avoids mixing sync and async DB drivers.
- **Repository / service split**: repositories only build and run
  queries; services hold business logic and are what API endpoints depend
  on. Today the service layer is a thin pass-through for products, but the
  seam is there for validation/authorization/cross-entity logic without
  endpoints touching SQLAlchemy directly.
- **Client-generated UUID primary keys** (`uuid.uuid4()` in Python, not a
  Postgres server default) so the `pgcrypto`/`uuid-ossp` extensions aren't
  required and IDs are available before a row is flushed.
- **`source_records` as a single table** for both products and ingredients
  (distinguished by a CHECK constraint requiring exactly one FK set)
  rather than two near-duplicate tables or a loosely-typed polymorphic
  key -- keeps verification metadata queryable in one place.
- **Embedding/RAG interfaces without implementations**: `EmbeddingService`
  and `RAGService` are abstract contracts with a placeholder
  implementation that raises `NotImplementedError`. This lets the schema
  and API shape be designed now without pretending functionality exists or
  making network calls during startup/tests.
- **Multi-stage Dockerfile**: `base` (runtime deps only) -> `runtime`
  (non-root, minimal) and `base` -> `test` (adds pytest/ruff, not shipped
  to production). The `tests` compose service builds the `test` target and
  only runs when explicitly invoked.
