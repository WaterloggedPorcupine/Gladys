from datetime import UTC, datetime

import pytest

from gladys.adapters.memory import InMemoryRunRepository
from gladys.domain.records import Request, RunRecord, RunStatus
from gladys.ports import ConcurrencyConflict, RunRepository


async def repository_contract(repo: RunRepository) -> None:
    run = RunRecord(Request("x", "u", datetime.now(UTC)), "tenant-a", "lab")
    await repo.add(run)
    assert await repo.get("tenant-b", run.run_id) is None
    loaded = await repo.get("tenant-a", run.run_id)
    assert loaded == run
    assert loaded is not None
    loaded.transition(RunStatus.GENERATING, "worker")
    await repo.save(loaded, 0)
    assert loaded.version == 1
    with pytest.raises(ConcurrencyConflict):
        await repo.save(run, 0)


async def test_memory_repository_contract() -> None:
    await repository_contract(InMemoryRunRepository())
