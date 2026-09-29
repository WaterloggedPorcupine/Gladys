from typing import Protocol

from gladys.domain.records import RunRecord, StatusChange


class ConcurrencyConflict(RuntimeError):
    pass


class RunRepository(Protocol):
    async def add(self, run: RunRecord) -> None: ...
    async def get(self, tenant_id: str, run_id: str) -> RunRecord | None: ...
    async def save(self, run: RunRecord, expected_version: int) -> None: ...

    async def get_status_history(self, tenant_id: str, run_id: str) -> list[StatusChange]:
        """The append-only audit rows, in order. Must always equal the stored run's ``history``."""
        ...
