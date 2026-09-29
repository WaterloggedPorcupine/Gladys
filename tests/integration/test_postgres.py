import os
from collections.abc import AsyncIterator

import pytest
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from gladys.adapters.postgres.models import Base
from gladys.adapters.postgres.repository import PostgresRunRepository
from tests.test_repository import repository_contract

pytestmark = pytest.mark.integration


@pytest.fixture
async def postgres_repo() -> AsyncIterator[PostgresRunRepository]:
    if os.getenv("DOCKER_HOST") == "disabled":
        pytest.skip("Docker unavailable")
    try:
        postgres = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    except DockerException as error:
        pytest.skip(f"Docker unavailable: {error}")
    with postgres:
        engine = create_async_engine(postgres.get_connection_url())
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield PostgresRunRepository(async_sessionmaker(engine, expire_on_commit=False))
        await engine.dispose()


async def test_postgres_repository_contract(postgres_repo: PostgresRunRepository) -> None:
    await repository_contract(postgres_repo)
