"""Create access, risk, exchange account and operations foundation tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_0007"
down_revision = "20260426_0006"
branch_labels = None
depends_on = None

EXCHANGE_CHECK = "'hyperliquid', 'aster', 'blofin'"
EXCHANGE_ACCOUNT_STATUS_CHECK = "'pending', 'active', 'disabled', 'revoked', 'error'"
SUBSCRIPTION_STATUS_CHECK = "'trialing', 'active', 'past_due', 'canceled', 'disabled'"
DLQ_STATUS_CHECK = "'open', 'acknowledged', 'reprocessed', 'ignored'"


def upgrade() -> None:
    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "copy_trading_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_subscriptions_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"status IN ({SUBSCRIPTION_STATUS_CHECK})",
            name="ck_user_subscriptions_status",
        ),
    )
    op.create_index(
        "ix_user_subscriptions_status",
        "user_subscriptions",
        ["status", "copy_trading_enabled"],
    )

    op.create_table(
        "exchange_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("secret_reference", sa.Text(), nullable=True),
        sa.Column("secret_fingerprint", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_exchange_accounts_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"exchange IN ({EXCHANGE_CHECK})",
            name="ck_exchange_accounts_exchange",
        ),
        sa.CheckConstraint(
            f"status IN ({EXCHANGE_ACCOUNT_STATUS_CHECK})",
            name="ck_exchange_accounts_status",
        ),
        sa.CheckConstraint(
            "secret_fingerprint IS NULL OR secret_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_exchange_accounts_secret_fingerprint_sha256_hex",
        ),
        sa.UniqueConstraint("exchange", "account_id", name="uq_exchange_accounts_exchange_account"),
    )
    op.create_index(
        "ix_exchange_accounts_user_status",
        "exchange_accounts",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_exchange_accounts_exchange_account",
        "exchange_accounts",
        ["exchange", "account_id"],
    )

    op.create_table(
        "copy_relationship_risk_settings",
        sa.Column("copy_relationship_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("max_order_quantity", sa.Numeric(38, 18), nullable=True),
        sa.Column("max_slippage_bps", sa.Integer(), server_default="100", nullable=False),
        sa.Column("max_leverage", sa.Numeric(38, 18), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["copy_relationship_id"],
            ["copy_relationships.id"],
            name="fk_copy_relationship_risk_settings_relationship",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "max_order_quantity IS NULL OR max_order_quantity > 0",
            name="ck_copy_relationship_risk_settings_order_quantity_positive",
        ),
        sa.CheckConstraint(
            "max_slippage_bps >= 0",
            name="ck_copy_relationship_risk_settings_slippage_non_negative",
        ),
        sa.CheckConstraint(
            "max_leverage IS NULL OR max_leverage > 0",
            name="ck_copy_relationship_risk_settings_leverage_positive",
        ),
    )

    op.create_table(
        "dead_letter_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("failed_subject", sa.Text(), nullable=False),
        sa.Column("delivery_attempt", sa.Integer(), nullable=False),
        sa.Column("max_delivery_attempts", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
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
        sa.UniqueConstraint("idempotency_key", name="uq_dead_letter_events_idempotency_key"),
        sa.CheckConstraint(
            f"status IN ({DLQ_STATUS_CHECK})",
            name="ck_dead_letter_events_status",
        ),
        sa.CheckConstraint(
            "delivery_attempt > 0",
            name="ck_dead_letter_events_delivery_attempt_positive",
        ),
        sa.CheckConstraint(
            "max_delivery_attempts > 0",
            name="ck_dead_letter_events_max_delivery_attempts_positive",
        ),
    )
    op.create_index(
        "ix_dead_letter_events_status_created",
        "dead_letter_events",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dead_letter_events_status_created", table_name="dead_letter_events")
    op.drop_table("dead_letter_events")
    op.drop_table("copy_relationship_risk_settings")
    op.drop_index("ix_exchange_accounts_exchange_account", table_name="exchange_accounts")
    op.drop_index("ix_exchange_accounts_user_status", table_name="exchange_accounts")
    op.drop_table("exchange_accounts")
    op.drop_index("ix_user_subscriptions_status", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
