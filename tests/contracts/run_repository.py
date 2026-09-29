from datetime import UTC, datetime

import pytest

from gladys.domain.records import Request, RunRecord, RunStatus
from gladys.ports import ConcurrencyConflict, RunRepository


def new_run(tenant_id: str = "tenant-a") -> RunRecord:
    return RunRecord(Request("x", "u", datetime.now(UTC)), tenant_id, "lab")


class RunRepositoryContract:
    """Behavior every ``RunRepository`` adapter must share. Subclasses provide a ``repo`` fixture."""

    async def test_add_then_get_round_trips(self, repo: RunRepository) -> None:
        run = new_run()
        await repo.add(run)
        assert await repo.get("tenant-a", run.run_id) == run

    async def test_get_is_tenant_scoped(self, repo: RunRepository) -> None:
        run = new_run()
        await repo.add(run)
        assert await repo.get("tenant-b", run.run_id) is None

    async def test_save_bumps_version_and_rejects_stale_writes(self, repo: RunRepository) -> None:
        run = new_run()
        await repo.add(run)
        loaded = await repo.get("tenant-a", run.run_id)
        assert loaded is not None
        loaded.transition(RunStatus.GENERATING, "worker")
        await repo.save(loaded, 0)
        assert loaded.version == 1
        with pytest.raises(ConcurrencyConflict):
            await repo.save(run, 0)
