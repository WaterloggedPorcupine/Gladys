from typing import Protocol

from gladys.domain.records import RunRecord, StatusChange


class ConcurrencyConflict(RuntimeError):
    pass


class RunAlreadyExists(RuntimeError):
    """``add`` was called with a ``run_id`` that is already stored (in any tenant: run IDs are global)."""


class RunRepository(Protocol):
    async def add(self, run: RunRecord) -> None: ...
    async def get(self, tenant_id: str, run_id: str) -> RunRecord | None: ...
    async def save(self, run: RunRecord, expected_version: int) -> None: ...

    async def get_status_history(self, tenant_id: str, run_id: str) -> list[StatusChange]:
        """The append-only audit rows, in order. Must always equal the stored run's ``history``."""
        ...

    async def find_by_external_ref(self, tenant_id: str, system: str, kind: str, ext_id: str) -> list[str]:
        """IDs of the tenant's runs linked to that external record (e.g. every run that tested idea X), oldest first."""
        ...
