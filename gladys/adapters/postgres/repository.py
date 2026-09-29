from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gladys.adapters.postgres.models import RunExternalRefRow, RunRow, RunStatusChangeRow
from gladys.domain.records import RunRecord, StatusChange
from gladys.ports import ConcurrencyConflict, RunAlreadyExists


def _status_rows(run: RunRecord, after_seq: int) -> list[dict[str, object]]:
    """Rows for history entries whose index (``seq``) is greater than ``after_seq``."""
    return [
        {"run_id": run.run_id, "tenant_id": run.tenant_id, "seq": seq, "at": change.at, "document": change.to_dict()}
        for seq, change in enumerate(run.history)
        if seq > after_seq
    ]


async def _index_external_refs(session: AsyncSession, run: RunRecord) -> None:
    """Project the run's external refs into run_external_refs; refs already indexed are skipped by the database."""
    if not run.external_refs:
        return
    await session.execute(
        pg_insert(RunExternalRefRow)
        .values(
            [
                {"run_id": run.run_id, "tenant_id": run.tenant_id, "system": r.system, "kind": r.kind, "ext_id": r.id}
                for r in run.external_refs
            ]
        )
        .on_conflict_do_nothing(constraint="uq_run_external_refs_lookup")
    )


class PostgresRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, run: RunRecord) -> None:
        async with self._sessions.begin() as session:
            # ON CONFLICT DO NOTHING + rowcount turns a duplicate into a typed error without parsing IntegrityError.
            result = await session.execute(
                pg_insert(RunRow)
                .values(
                    id=run.run_id,
                    tenant_id=run.tenant_id,
                    status=run.status.value,
                    requested_by=run.request.requested_by,
                    lab_profile_id=run.lab_profile_id,
                    current_protocol_sha256=run.protocol.source_sha256 if run.protocol else None,
                    created_at=run.request.submitted_at,
                    updated_at=datetime.now(UTC),
                    version=run.version,
                    document=run.to_dict(),
                )
                .on_conflict_do_nothing(index_elements=[RunRow.id])
            )
            if cast(CursorResult[tuple[object, ...]], result).rowcount != 1:
                raise RunAlreadyExists(f"run {run.run_id} already exists")
            if rows := _status_rows(run, after_seq=-1):
                await session.execute(insert(RunStatusChangeRow), rows)
            await _index_external_refs(session, run)

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
            stored_max_seq = await session.scalar(
                select(func.max(RunStatusChangeRow.seq)).where(
                    RunStatusChangeRow.tenant_id == run.tenant_id,
                    RunStatusChangeRow.run_id == run.run_id,
                )
            )
            # executemany with an empty list would insert one all-NULL row, so only insert when there is something new.
            if rows := _status_rows(run, after_seq=-1 if stored_max_seq is None else stored_max_seq):
                await session.execute(insert(RunStatusChangeRow), rows)
            await _index_external_refs(session, run)
        run.version = next_version

    async def get_status_history(self, tenant_id: str, run_id: str) -> list[StatusChange]:
        async with self._sessions() as session:
            documents: list[dict[str, object]] = list(
                await session.scalars(
                    select(RunStatusChangeRow.document)
                    .where(RunStatusChangeRow.tenant_id == tenant_id, RunStatusChangeRow.run_id == run_id)
                    .order_by(RunStatusChangeRow.seq)
                )
            )
            return [StatusChange.from_dict(d) for d in documents]

    async def find_by_external_ref(self, tenant_id: str, system: str, kind: str, ext_id: str) -> list[str]:
        async with self._sessions() as session:
            ids = await session.scalars(
                select(RunRow.id)
                .join(RunExternalRefRow, RunExternalRefRow.run_id == RunRow.id)
                .where(
                    RunExternalRefRow.tenant_id == tenant_id,
                    RunExternalRefRow.system == system,
                    RunExternalRefRow.kind == kind,
                    RunExternalRefRow.ext_id == ext_id,
                    RunRow.tenant_id == tenant_id,
                )
                .order_by(RunRow.created_at, RunRow.id)
            )
            return list(ids)
