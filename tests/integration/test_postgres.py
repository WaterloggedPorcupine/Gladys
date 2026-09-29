import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from gladys.adapters.postgres.repository import PostgresRunRepository
from tests.contracts.run_repository import RunRepositoryContract

pytestmark = pytest.mark.integration


class TestPostgresRunRepository(RunRepositoryContract):
    @pytest.fixture
    def repo(self, engine: AsyncEngine) -> PostgresRunRepository:
        return PostgresRunRepository(async_sessionmaker(engine, expire_on_commit=False))
