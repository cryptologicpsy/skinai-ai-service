# CI/CD

This document describes what is actually implemented in
`.github/workflows/ci.yml` and `.github/workflows/deploy.yml`, and what is
intentionally left as a documented future step. Anything not listed as
"implemented" below does not run automatically.

## CI workflow (`.github/workflows/ci.yml`)

**Triggers**: push to `main`, pull requests targeting `main`, and manual
`workflow_dispatch`. Superseded runs for the same branch/PR are cancelled
automatically (`concurrency`).

**Permissions**: `contents: read` only. The workflow never writes to the
repo, never publishes a package, and never touches the `production`
Environment or its secrets.

Two independent jobs:

### `lint`

Runs on a plain `ubuntu-latest` runner with `actions/setup-python@v5`
(Python 3.12, matching `pyproject.toml`'s `requires-python` and the
Dockerfile's base image) and `pip install -r requirements-dev.txt`:

- `ruff check .`
- `ruff format --check .`

No Docker, no database -- this is deliberately the fast path so a
formatting/lint mistake fails in seconds, independent of the slower
Docker/Postgres job below.

### `test`

Reuses the project's own `compose.yaml` rather than a separate,
hand-rolled GitHub Actions Postgres `services:` block. This is a
deliberate choice: `compose.yaml` already pins the exact Postgres+pgvector
image (`pgvector/pgvector:pg16`) used in local development, so CI can
never silently drift onto a different pgvector version than what the
migrations and models were written against. Concretely:

1. Checks out the repo.
2. Writes a throwaway `.env` file (required because `compose.yaml`'s `app`
   and `tests` services declare `env_file: - .env`). The values are fixed,
   non-secret, CI-only placeholders (`POSTGRES_PASSWORD=ci_test_password`
   etc.) -- nothing outside the job's own ephemeral runner VM ever uses
   them, so they are not treated as secrets and are not stored anywhere.
3. `docker compose build app tests` -- builds **both** Dockerfile targets
   (`runtime` and `test`), so a broken build in either stage fails CI.
4. `docker compose up -d --wait --wait-timeout 60 db` -- starts Postgres
   and blocks until its healthcheck (`pg_isready`) reports healthy, or
   fails the job after 60s.
5. Verifies the `vector` extension is installed and the dedicated
   `skinai_test` database (created by
   `docker/initdb/01-create-test-db.sh` the first time the `db` container
   initializes its data directory) is reachable.
6. `docker compose run --rm -T app alembic upgrade head` -- applies
   migrations to the main `skinai` database using the exact CLI command
   documented in the README for real deployments.
7. `docker compose run --rm -T tests pytest -v` -- runs the full pytest
   suite against the separate `skinai_test` database. The test suite
   migrates `skinai_test` itself (see "Test database lifecycle" below);
   that migration never runs concurrently with step 6 because they target
   different databases and the steps are sequential.
8. On failure, dumps `docker compose logs` before the job ends.
9. Always (success or failure) runs `docker compose down -v
   --remove-orphans` to remove the containers, network, and the ephemeral
   `db_data` volume for *this job's own* throwaway Postgres instance. This
   has no effect on any persistent database -- the GitHub-hosted runner VM
   itself is destroyed immediately after the job anyway.

## Test database lifecycle

- `skinai_test` is a separate database from the app's `skinai` database,
  created once per fresh `db_data` volume by
  `docker/initdb/01-create-test-db.sh`.
- `tests/conftest.py`'s session-scoped `apply_migrations` fixture runs
  `alembic upgrade head` (via Alembic's Python API) against `skinai_test`
  before any test runs, and `alembic downgrade base` after the session
  ends.
- A function-scoped `_clean_tables` fixture truncates every table after
  each test and disposes the SQLAlchemy engine's connection pool (required
  because `asyncpg` connections are bound to the event loop they were
  created on, and pytest-asyncio gives each test function its own loop).
- In CI, the `db_data` volume is created fresh for every run (new runner
  VM each time), so there is no cross-run state to clean up -- the
  database is recreated, not reused, for each CI run.
- Nothing in this pipeline ever points at a production database. The only
  `DATABASE_URL` values used in CI are the ones written into the
  job-local `.env` file, pointing at the job's own `db` service container.

## Required GitHub repository settings for CI

None beyond the defaults. `ci.yml` only needs `contents: read`, which the
default `GITHUB_TOKEN` already has. No repository Secrets or Variables are
required for CI to pass.

## Deployment workflow (`.github/workflows/deploy.yml`)

**Status: scaffold, not enabled.** Triggering this workflow today will
always fail at the "Check deployment configuration" step, by design,
because no deployment target is configured in this repository yet.

What it does today:

1. Only runs on manual `workflow_dispatch`, and requires typing `deploy`
   into a required text input -- a dispatch click alone is not enough.
2. A `preflight` job explicitly checks `github.ref == 'refs/heads/main'`
   and rejects anything else, even though `workflow_dispatch` can
   technically be run from any branch.
3. A `deploy` job runs under the `environment: production` GitHub
   Environment (see "Required GitHub settings" below) and checks for the
   presence of the secrets/variables listed under "Deployment
   prerequisites". If any are missing (today, all of them are), it fails
   loudly and lists exactly what's missing. If somehow all were present,
   it still fails deliberately, pointing at this document, because the
   actual remote deploy steps are commented out pending a reviewed
   server-side rollout script.
4. Writes a job summary (`$GITHUB_STEP_SUMMARY`) recording the branch,
   commit, and actor for every run, success or failure.

No step in this workflow makes a network connection to any server.

### Deployment prerequisites

Before any of the commented-out steps in `deploy.yml` can be enabled, all
of the following must exist and be reviewed:

**Repository Variables** (Settings -> Secrets and variables -> Actions ->
Variables), not secret but environment-specific:

| Variable | Purpose |
|---|---|
| `DEPLOY_SSH_HOST` | Hostname/IP of the VPS |
| `DEPLOY_SSH_USER` | SSH user used for deployment (should be a dedicated, non-root, limited-privilege user -- not the account used for the existing SkinAI/BeautyFlow containers) |
| `DEPLOY_PATH` | Absolute path on the VPS to this service's own deployment directory (must be separate from any existing SkinAI/BeautyFlow deployment directory) |
| `DEPLOY_REGISTRY` | Container registry hostname/namespace the image will be pulled from (private registry; not yet implemented -- see "Deployment strategy" below) |

**Repository Secrets** (Settings -> Secrets and variables -> Actions ->
Secrets):

| Secret | Purpose |
|---|---|
| `DEPLOY_SSH_PRIVATE_KEY` | Private key for a dedicated deploy-only SSH keypair (generate a new one; do not reuse a personal or existing-service key) |
| `DEPLOY_SSH_KNOWN_HOSTS` | Output of `ssh-keyscan <host>` captured once, out of band, and pinned here -- this repo will never disable host-key checking |

**Server-side prerequisites** (none of which this repository can create
for you):

- A dedicated, reviewed `deploy.sh` (or equivalent) on the VPS that: pulls
  the image tagged with the deploying commit SHA, runs `alembic upgrade
  head` as a one-off container against *this service's own* database only,
  recreates only this service's app container, and checks
  `/health/ready` before declaring success.
- A separate PostgreSQL database/user for this service on the VPS,
  distinct from the existing SkinAI (MongoDB) and BeautyFlow data stores --
  this workflow must never be pointed at those.
- A private container registry (e.g. GHCR with repository-scoped access)
  if images are to be published, configured separately -- not implemented
  yet. Until then, the only supported path is building the image directly
  on the VPS from a tagged commit.
- Confirmation that the existing reverse proxy, firewall, and other
  containers on the VPS are left untouched: this service's app port must
  stay off any publicly reachable address, and PostgreSQL must never be
  published.

### Required GitHub settings for deployment

1. **Settings -> Environments -> New environment -> `production`.**
2. Under that Environment, add **required reviewers** (at least yourself)
   so every deployment needs manual approval in the GitHub UI, in addition
   to the `preflight` branch/confirmation checks in the workflow.
3. Under that Environment's **Deployment branches and tags**, restrict to
   `main` only (belt-and-suspenders alongside the explicit `github.ref`
   check in `preflight`).
4. Add the Secrets and Variables listed above **scoped to the `production`
   Environment** (not repository-wide), so the job's `environment:
   production` is what grants access to them.

## Secret management

- No deployment secrets exist in this repository today. `ci.yml` needs
  none at all.
- If a credential (API key, DB password, private key) is ever accidentally
  committed: do not just delete it in a new commit -- git history retains
  it. Rotate/revoke the credential at its source immediately (e.g. regenerate
  the DB password, revoke and reissue the SSH keypair, rotate the API key
  with its provider), then remove it from history if required (e.g. via
  `git filter-repo` or GitHub's secret-scanning remediation guidance), and
  force-push only after coordinating with anyone else using the repo.

## Rollback approach (documented, not yet automated)

Once real deployment is enabled, the intended rollback is: re-run
`deploy.yml` with the previous known-good commit SHA's image (images are
tagged by commit SHA, so any previous build is addressable), after
confirming the database migration for the bad release was additive/
backward-compatible or has its own reviewed down-migration. There is no
one-click "rollback" button implemented -- this is intentionally a manual,
reviewed action, not an automatic one, since database migrations are not
always safely reversible.

## Troubleshooting common CI failures

- **`db` never becomes healthy / `--wait` times out**: check the dumped
  `docker compose logs` output in the failed run; usually a bad
  `POSTGRES_*` value in the job's generated `.env` (compare against
  `.env.example`) or a Docker Hub rate limit on
  `pgvector/pgvector:pg16`.
- **`alembic upgrade head` fails in the "Apply Alembic migrations" step**:
  this indicates a real migration bug (bad SQL, missing extension, FK
  ordering) against the `skinai` database -- it is not masked or retried.
  Fix the migration; do not skip this step to make CI pass.
- **pytest fails only in CI, not locally**: almost always an environment
  difference, not a flaky test. Compare the job's generated `.env` against
  your local `.env`, and check the "Verify pgvector extension and test
  database are ready" step's output.
- **`ruff format --check` fails**: run `ruff format .` locally and commit
  the result; CI never auto-formats for you.
- **Deploy workflow always fails at "Check deployment configuration"**:
  expected and by design until the prerequisites above are satisfied --
  see the error message for exactly which secret/variable is missing.
