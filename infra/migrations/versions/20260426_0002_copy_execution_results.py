"""Create copy execution results table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260426_0002"
down_revision = "20260426_0001"
branch_labels = None
depends_on = None


EXCHANGE_CHECK = "'hyperliquid', 'aster', 'blofin'"
RESULT_STATUS_CHECK = "'ACCEPTED', 'REJECTED', 'FILLED', 'FAILED'"


def upgrade() -> None:
    op.create_table(
        "copy_execution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_exchange", sa.Text(), nullable=False),
        sa.Column("source_account_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("exchange_order_id", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "raw_response",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["copy_execution_requests.id"],
            name="fk_copy_execution_results_request",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_copy_execution_results_idempotency_key",
        ),
        sa.CheckConstraint(
            f"source_exchange IN ({EXCHANGE_CHECK})",
            name="ck_copy_execution_results_source_exchange",
        ),
        sa.CheckConstraint(
            f"status IN ({RESULT_STATUS_CHECK})",
            name="ck_copy_execution_results_status",
        ),
    )
    op.create_index(
        "ix_copy_execution_results_request",
        "copy_execution_results",
        ["request_id"],
    )
    op.create_index(
        "ix_copy_execution_results_status_created",
        "copy_execution_results",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_copy_execution_results_status_created", table_name="copy_execution_results")
    op.drop_index("ix_copy_execution_results_request", table_name="copy_execution_results")
    op.drop_table("copy_execution_results")
