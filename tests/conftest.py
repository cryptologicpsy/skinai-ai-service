"""Shared pytest fixtures.

Tests need a real PostgreSQL instance with the pgvector extension
available (see compose.yaml's `tests` service / README "Running tests").
Environment variables are set here, before `app` is imported anywhere,
so Settings() picks up test values.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("EMBEDDING_DIMENSION", "1536")
os.environ.setdefault("CORS_ORIGINS", "[]")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://skinai:skinai@localhost:5432/skinai_test",
)

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine, get_db
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    """Run real Alembic migrations against the test database once per
    session, so tests exercise the same migration path used in
    production, not an ad-hoc `create_all()`.
    """

    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables() -> AsyncGenerator[None, None]:
    """Ensure each test starts with empty tables.

    Also disposes the engine's connection pool after every test. pytest-asyncio
    gives each test function its own event loop by default, but asyncpg
    connections are bound to the loop they were created on; without disposing,
    a pooled connection from a previous test's (now-closed) loop gets handed
    to the next test and asyncpg raises "attached to a different loop".
    """

    yield
    async with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            await connection.execute(table.delete())
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
