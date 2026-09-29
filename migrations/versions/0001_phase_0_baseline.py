"""Phase 0 persistence baseline."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_phase_0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("lab_profile_id", sa.String(), nullable=False),
        sa.Column("current_protocol_sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_runs_tenant_id", "runs", ["tenant_id"])
    op.create_table(
        "run_status_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_run_status_changes_run_id_at", "run_status_changes", ["run_id", "at"])
    op.create_table(
        "run_external_refs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("system", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("ext_id", sa.String(), nullable=False),
        sa.UniqueConstraint("tenant_id", "system", "kind", "ext_id", "run_id"),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("tenant_id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_outbox_tenant_id", "outbox", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("idempotency_keys")
    op.drop_table("run_external_refs")
    op.drop_table("run_status_changes")
    op.drop_table("runs")
