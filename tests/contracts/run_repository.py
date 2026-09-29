from datetime import UTC, datetime

import pytest

from gladys.domain.records import ProtocolRevision, Request, RunRecord, RunStatus
from gladys.ports import ConcurrencyConflict, RunAlreadyExists, RunRepository


def new_run(tenant_id: str = "tenant-a") -> RunRecord:
    return RunRecord(Request("x", "u", datetime.now(UTC)), tenant_id, "lab")


async def generating_run(repo: RunRepository) -> RunRecord:
    """A stored run that has moved to GENERATING (one history entry, version 1)."""
    run = new_run()
    await repo.add(run)
    run.transition(RunStatus.GENERATING, "worker")
    await repo.save(run, 0)
    return run


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

    async def test_save_without_a_transition(self, repo: RunRepository) -> None:
        run = await generating_run(repo)
        run.add_protocol_revision(ProtocolRevision.from_source("print(1)", "scientist", "human_edit"))
        await repo.save(run, 1)
        assert await repo.get("tenant-a", run.run_id) == run
        assert await repo.get_status_history("tenant-a", run.run_id) == list(run.history)

    async def test_two_saves_in_a_row(self, repo: RunRepository) -> None:
        run = await generating_run(repo)
        run.transition(RunStatus.DRAFT, "agent")
        await repo.save(run, 1)
        run.transition(RunStatus.ABORTED, "scientist")
        await repo.save(run, 2)
        assert run.version == 3
        assert await repo.get("tenant-a", run.run_id) == run

    async def test_status_rows_equal_domain_history_in_order(self, repo: RunRepository) -> None:
        run = new_run()
        run.transition(RunStatus.GENERATING, "worker")
        await repo.add(run)
        run.transition(RunStatus.GENERATION_FAILED, "agent")
        run.transition(RunStatus.GENERATING, "worker")
        await repo.save(run, 0)
        await repo.save(run, 1)  # nothing new to append
        run.transition(RunStatus.DRAFT, "agent")
        await repo.save(run, 2)
        assert await repo.get_status_history("tenant-a", run.run_id) == list(run.history)
        assert await repo.get_status_history("tenant-b", run.run_id) == []

    async def test_duplicate_add_raises_run_already_exists(self, repo: RunRepository) -> None:
        run = new_run()
        await repo.add(run)
        with pytest.raises(RunAlreadyExists):
            await repo.add(run)
        clash = new_run("tenant-b")
        clash.run_id = run.run_id
        with pytest.raises(RunAlreadyExists):
            await repo.add(clash)
        assert await repo.get("tenant-b", run.run_id) is None
