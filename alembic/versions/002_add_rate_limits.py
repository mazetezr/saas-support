"""Add per-tenant rate limit settings.

Revision ID: 002
Create Date: 2026-02-20
"""

from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
        ADD COLUMN rate_limit_per_minute INT DEFAULT 5,
        ADD COLUMN rate_limit_per_day INT DEFAULT 50
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE tenants
        DROP COLUMN IF EXISTS rate_limit_per_minute,
        DROP COLUMN IF EXISTS rate_limit_per_day
    """)
