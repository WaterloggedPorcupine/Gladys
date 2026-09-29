from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    lab_profile_id: Mapped[str] = mapped_column(String, nullable=False)
    current_protocol_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class RunStatusChangeRow(Base):
    __tablename__ = "run_status_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # index of this change in the run's history
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_run_status_changes_run_id_seq"),
        Index("ix_run_status_changes_run_id_at", "run_id", "at"),
    )


class RunExternalRefRow(Base):
    __tablename__ = "run_external_refs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    system: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    ext_id: Mapped[str] = mapped_column(String, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "system", "kind", "ext_id", "run_id"),)


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"
    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxRow(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
