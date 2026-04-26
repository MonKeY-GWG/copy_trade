"""Create copy execution foundation tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260426_0001"
down_revision = None
branch_labels = None
depends_on = None


EXCHANGE_CHECK = "'hyperliquid', 'aster', 'blofin'"
ORDER_TYPE_CHECK = "'MARKET', 'LIMIT', 'STOP', 'TAKE_PROFIT', 'TRAILING_STOP'"
ORDER_SIDE_CHECK = "'BUY', 'SELL'"
POSITION_SIDE_CHECK = "'LONG', 'SHORT', 'NET'"
REQUEST_STATUS_CHECK = "'REQUESTED', 'PUBLISHED', 'ACCEPTED', 'REJECTED', 'FILLED', 'FAILED'"


def upgrade() -> None:
    op.create_table(
        "copy_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_exchange", sa.Text(), nullable=False),
        sa.Column("source_account_id", sa.Text(), nullable=False),
        sa.Column("source_symbol", sa.Text(), nullable=True),
        sa.Column("follower_account_id", sa.Text(), nullable=False),
        sa.Column("target_exchange", sa.Text(), nullable=False),
        sa.Column("target_symbol", sa.Text(), nullable=False),
        sa.Column("max_slippage_bps", sa.Integer(), server_default="100", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"source_exchange IN ({EXCHANGE_CHECK})",
            name="ck_copy_relationships_source_exchange",
        ),
        sa.CheckConstraint(
            f"target_exchange IN ({EXCHANGE_CHECK})",
            name="ck_copy_relationships_target_exchange",
        ),
        sa.CheckConstraint(
            "max_slippage_bps >= 0",
            name="ck_copy_relationships_max_slippage_non_negative",
        ),
    )
    op.create_index(
        "ix_copy_relationships_active_source_event",
        "copy_relationships",
        ["active", "source_exchange", "source_account_id", "source_symbol", "effective_from"],
    )
    op.create_index(
        "ix_copy_relationships_follower_account",
        "copy_relationships",
        ["follower_account_id"],
    )

    op.create_table(
        "copy_execution_idempotency",
        sa.Column("idempotency_key", sa.Text(), primary_key=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "copy_execution_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_exchange", sa.Text(), nullable=False),
        sa.Column("source_account_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("copy_relationship_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("follower_account_id", sa.Text(), nullable=False),
        sa.Column("target_exchange", sa.Text(), nullable=False),
        sa.Column("target_symbol", sa.Text(), nullable=False),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("position_side", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 18), nullable=False),
        sa.Column("price", sa.Numeric(38, 18), nullable=True),
        sa.Column("trigger_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("reduce_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("post_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("max_slippage_bps", sa.Integer(), server_default="100", nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("request_status", sa.Text(), server_default="REQUESTED", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["copy_relationship_id"],
            ["copy_relationships.id"],
            name="fk_copy_execution_requests_relationship",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_copy_execution_requests_idempotency_key",
        ),
        sa.CheckConstraint(
            f"source_exchange IN ({EXCHANGE_CHECK})",
            name="ck_copy_execution_requests_source_exchange",
        ),
        sa.CheckConstraint(
            f"target_exchange IN ({EXCHANGE_CHECK})",
            name="ck_copy_execution_requests_target_exchange",
        ),
        sa.CheckConstraint(
            f"order_type IN ({ORDER_TYPE_CHECK})",
            name="ck_copy_execution_requests_order_type",
        ),
        sa.CheckConstraint(
            f"side IN ({ORDER_SIDE_CHECK})",
            name="ck_copy_execution_requests_side",
        ),
        sa.CheckConstraint(
            f"position_side IN ({POSITION_SIDE_CHECK})",
            name="ck_copy_execution_requests_position_side",
        ),
        sa.CheckConstraint(
            f"request_status IN ({REQUEST_STATUS_CHECK})",
            name="ck_copy_execution_requests_status",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_copy_execution_requests_quantity_positive",
        ),
        sa.CheckConstraint(
            "price IS NULL OR price > 0",
            name="ck_copy_execution_requests_price_positive",
        ),
        sa.CheckConstraint(
            "trigger_price IS NULL OR trigger_price > 0",
            name="ck_copy_execution_requests_trigger_price_positive",
        ),
        sa.CheckConstraint(
            "max_slippage_bps >= 0",
            name="ck_copy_execution_requests_max_slippage_non_negative",
        ),
    )
    op.create_index(
        "ix_copy_execution_requests_source_event",
        "copy_execution_requests",
        ["source_event_id"],
    )
    op.create_index(
        "ix_copy_execution_requests_relationship",
        "copy_execution_requests",
        ["copy_relationship_id"],
    )
    op.create_index(
        "ix_copy_execution_requests_status_created",
        "copy_execution_requests",
        ["request_status", "created_at"],
    )


def downgrade() -> None:
    for table_name, index_names in _indexes_by_table().items():
        for index_name in index_names:
            op.drop_index(index_name, table_name=table_name)
    op.drop_table("copy_execution_requests")
    op.drop_table("copy_execution_idempotency")
    op.drop_table("copy_relationships")


def _indexes_by_table() -> dict[str, Sequence[str]]:
    return {
        "copy_execution_requests": (
            "ix_copy_execution_requests_status_created",
            "ix_copy_execution_requests_relationship",
            "ix_copy_execution_requests_source_event",
        ),
        "copy_relationships": (
            "ix_copy_relationships_follower_account",
            "ix_copy_relationships_active_source_event",
        ),
    }
