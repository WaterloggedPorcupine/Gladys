import asyncio

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from gladys.adapters.postgres.models import Base
from tests.integration.conftest import TABLES, MigratedDatabase

pytestmark = pytest.mark.integration


def _diff(connection: Connection) -> list[object]:
    return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))


async def test_migrations_match_models(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        assert await connection.run_sync(_diff) == []


async def _table_names(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
    finally:
        await engine.dispose()


def test_downgrade_to_base_then_upgrade_to_head(
    migrated_database: MigratedDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A plain (sync) test: env.py calls asyncio.run(), which cannot run inside pytest-asyncio's loop.
    monkeypatch.setenv("GLADYS_DATABASE__URL", migrated_database.url)
    command.downgrade(migrated_database.alembic, "base")
    assert asyncio.run(_table_names(migrated_database.url)) == {"alembic_version"}
    command.upgrade(migrated_database.alembic, "head")
    assert set(TABLES) <= asyncio.run(_table_names(migrated_database.url))
