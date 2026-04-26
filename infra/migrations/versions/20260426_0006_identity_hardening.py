"""Harden identity token constraints."""

from alembic import op

revision = "20260426_0006"
down_revision = "20260426_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE roles ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.execute("ALTER TABLE api_credentials ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.create_check_constraint(
        "ck_api_credentials_token_hash_sha256_hex",
        "api_credentials",
        "token_hash ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_api_credentials_token_hash_sha256_hex",
        "api_credentials",
        type_="check",
    )
    op.execute("ALTER TABLE api_credentials ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE roles ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN id DROP DEFAULT")
