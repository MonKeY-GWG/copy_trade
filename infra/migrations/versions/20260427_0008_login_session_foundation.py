"""Create login and browser session foundation tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_0008"
down_revision = "20260427_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_credentials",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_password_credentials_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "password_hash LIKE 'scrypt$%'",
            name="ck_password_credentials_hash_format",
        ),
        sa.UniqueConstraint("user_id", name="uq_password_credentials_user"),
    )
    op.create_index(
        "ix_password_credentials_user_active",
        "password_credentials",
        ["user_id", "active"],
    )

    op.create_table(
        "user_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "session_token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_user_sessions_session_token_hash_sha256_hex",
        ),
        sa.CheckConstraint(
            "csrf_token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_user_sessions_csrf_token_hash_sha256_hex",
        ),
        sa.UniqueConstraint("session_token_hash", name="uq_user_sessions_session_token_hash"),
    )
    op.create_index(
        "ix_user_sessions_user_active",
        "user_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )
    op.create_index(
        "ix_user_sessions_expires_at",
        "user_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_active", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_password_credentials_user_active", table_name="password_credentials")
    op.drop_table("password_credentials")
