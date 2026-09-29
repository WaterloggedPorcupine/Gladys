from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gladys.adapters.postgres.models import RunExternalRefRow, RunRow, RunStatusChangeRow
from gladys.domain.records import RunRecord
from gladys.ports import ConcurrencyConflict


class PostgresRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, run: RunRecord) -> None:
        now = datetime.now(UTC)
        document = run.to_dict()
        async with self._sessions.begin() as session:
            session.add(
                RunRow(
                    id=run.run_id,
                    tenant_id=run.tenant_id,
                    status=run.status.value,
                    requested_by=run.request.requested_by,
                    lab_profile_id=run.lab_profile_id,
                    current_protocol_sha256=run.protocol.source_sha256 if run.protocol else None,
                    created_at=run.request.submitted_at,
                    updated_at=now,
                    version=run.version,
                    document=document,
                )
            )
            session.add_all(
                [
                    RunStatusChangeRow(run_id=run.run_id, tenant_id=run.tenant_id, at=h.at, document=h.to_dict())
                    for h in run.history
                ]
            )
            session.add_all(
                [
                    RunExternalRefRow(
                        run_id=run.run_id,
                        tenant_id=run.tenant_id,
                        system=r.system,
                        kind=r.kind,
                        ext_id=r.id,
                    )
                    for r in run.external_refs
                ]
            )

    async def get(self, tenant_id: str, run_id: str) -> RunRecord | None:
        async with self._sessions() as session:
            document = await session.scalar(
                select(RunRow.document).where(RunRow.tenant_id == tenant_id, RunRow.id == run_id)
            )
        return RunRecord.from_dict(document) if document is not None else None

    async def save(self, run: RunRecord, expected_version: int) -> None:
        next_version = expected_version + 1
        document = run.to_dict()
        document["version"] = next_version
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(RunRow)
                .where(
                    RunRow.tenant_id == run.tenant_id,
                    RunRow.id == run.run_id,
                    RunRow.version == expected_version,
                )
                .values(
                    status=run.status.value,
                    current_protocol_sha256=run.protocol.source_sha256 if run.protocol else None,
                    updated_at=datetime.now(UTC),
                    version=next_version,
                    document=document,
                )
            )
            if cast(CursorResult[tuple[object, ...]], result).rowcount != 1:
                raise ConcurrencyConflict(f"run {run.run_id} was concurrently modified")
            existing_count = await session.scalar(
                select(func.count())
                .select_from(RunStatusChangeRow)
                .where(
                    RunStatusChangeRow.tenant_id == run.tenant_id,
                    RunStatusChangeRow.run_id == run.run_id,
                )
            )
            offset = existing_count or 0
            await session.execute(
                insert(RunStatusChangeRow),
                [
                    {
                        "run_id": run.run_id,
                        "tenant_id": run.tenant_id,
                        "at": h.at,
                        "document": h.to_dict(),
                    }
                    for h in run.history[offset:]
                ],
            )
        run.version = next_version
