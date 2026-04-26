"""Create identity foundation tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260426_0005"
down_revision = "20260426_0004"
branch_labels = None
depends_on = None

ADMIN_ROLE_ID = "00000000-0000-0000-0000-000000000001"
TRADER_ROLE_ID = "00000000-0000-0000-0000-000000000002"
FOLLOWER_ROLE_ID = "00000000-0000-0000-0000-000000000003"


def upgrade() -> None:
    op.drop_constraint("ck_audit_logs_actor_type", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_actor_type",
        "audit_logs",
        "actor_type IN ('admin_api', 'system', 'user')",
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
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
            "status IN ('active', 'disabled')",
            name="ck_users_status",
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.execute(
        f"""
        INSERT INTO roles (id, name)
        VALUES
            ('{ADMIN_ROLE_ID}', 'admin'),
            ('{TRADER_ROLE_ID}', 'trader'),
            ('{FOLLOWER_ROLE_ID}', 'follower')
        """
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_roles_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_user_roles_role",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
    )
    op.create_index("ix_user_roles_role", "user_roles", ["role_id"])

    op.create_table(
        "api_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_type", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("token_prefix", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_api_credentials_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "credential_type IN ('admin_api_token')",
            name="ck_api_credentials_type",
        ),
        sa.UniqueConstraint("token_hash", name="uq_api_credentials_token_hash"),
    )
    op.create_index(
        "ix_api_credentials_user_active",
        "api_credentials",
        ["user_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_credentials_user_active", table_name="api_credentials")
    op.drop_table("api_credentials")
    op.drop_index("ix_user_roles_role", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")

    op.drop_constraint("ck_audit_logs_actor_type", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_actor_type",
        "audit_logs",
        "actor_type IN ('admin_api', 'system')",
    )
