import pytest

from gladys.adapters.memory import InMemoryRunRepository
from tests.contracts.run_repository import RunRepositoryContract


class TestInMemoryRunRepository(RunRepositoryContract):
    @pytest.fixture
    def repo(self) -> InMemoryRunRepository:
        return InMemoryRunRepository()
