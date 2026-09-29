"""Integration fixtures: one PostgreSQL container per session, schema built by Alembic.

Set ``GLADYS_REQUIRE_INTEGRATION=1`` (CI and ``make test-integration`` do) to turn a missing Docker
daemon into a test failure instead of a skip, so the integration job can never pass vacuously.
"""

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TABLES = ("outbox", "idempotency_keys", "run_external_refs", "run_status_changes", "runs")


@dataclass(frozen=True)
class MigratedDatabase:
    url: str
    alembic: Config


def _docker_unavailable(reason: str) -> None:
    if os.environ.get("GLADYS_REQUIRE_INTEGRATION") == "1":
        pytest.fail(f"Docker is required (GLADYS_REQUIRE_INTEGRATION=1) but unavailable: {reason}", pytrace=False)
    pytest.skip(f"Docker unavailable: {reason}")


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    try:
        container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
        container.start()
    except DockerException as error:
        _docker_unavailable(str(error))
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
def migrated_database(postgres_url: str) -> Iterator[MigratedDatabase]:
    """Run ``alembic upgrade head`` once. ``migrations/env.py`` reads the URL from Settings, like production."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GLADYS_DATABASE__URL", postgres_url)
        alembic = Config(str(ALEMBIC_INI))
        command.upgrade(alembic, "head")
        yield MigratedDatabase(postgres_url, alembic)


@pytest.fixture
async def engine(migrated_database: MigratedDatabase) -> AsyncIterator[AsyncEngine]:
    """A fresh engine per test (asyncpg connections are bound to one event loop) over emptied tables."""
    engine = create_async_engine(migrated_database.url)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()
