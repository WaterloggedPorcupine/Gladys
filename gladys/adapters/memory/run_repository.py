import copy

from gladys.domain.records import RunRecord, StatusChange
from gladys.ports import ConcurrencyConflict


class InMemoryRunRepository:
    """Test fake. Mirrors the Postgres layout: a document per run plus an append-only status log."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], dict[str, object]] = {}
        self._status_log: dict[tuple[str, str], list[StatusChange]] = {}

    async def add(self, run: RunRecord) -> None:
        key = (run.tenant_id, run.run_id)
        if key in self._documents:
            raise ConcurrencyConflict(f"run {run.run_id} already exists")
        self._documents[key] = copy.deepcopy(run.to_dict())
        self._status_log[key] = list(run.history)

    async def get(self, tenant_id: str, run_id: str) -> RunRecord | None:
        document = self._documents.get((tenant_id, run_id))
        return RunRecord.from_dict(copy.deepcopy(document)) if document else None

    async def save(self, run: RunRecord, expected_version: int) -> None:
        key = (run.tenant_id, run.run_id)
        current = self._documents.get(key)
        if current is None or current["version"] != expected_version:
            raise ConcurrencyConflict(f"run {run.run_id} was concurrently modified")
        run.version = expected_version + 1
        self._documents[key] = copy.deepcopy(run.to_dict())
        log = self._status_log[key]
        log.extend(run.history[len(log) :])

    async def get_status_history(self, tenant_id: str, run_id: str) -> list[StatusChange]:
        return list(self._status_log.get((tenant_id, run_id), []))
