"""Add language column to user_settings.

Revision ID: 003
Create Date: 2026-02-21
"""

from alembic import op

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_settings
        ADD COLUMN language TEXT DEFAULT NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_settings
        DROP COLUMN IF EXISTS language
    """)
