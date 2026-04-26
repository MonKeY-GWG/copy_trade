"""Prevent duplicate active copy relationships."""

from alembic import op

revision = "20260426_0003"
down_revision = "20260426_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX uq_copy_relationships_active_route
        ON copy_relationships (
            source_exchange,
            source_account_id,
            COALESCE(source_symbol, ''),
            follower_account_id,
            target_exchange,
            target_symbol
        )
        WHERE active IS TRUE
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_copy_relationships_active_route")
