"""Baseline migration — existing tables created via Base.metadata.create_all.

This migration marks the starting point of Alembic version tracking.
All tables that existed before Alembic was introduced are assumed to already
be present (they were created by SQLAlchemy create_all + the legacy migrate.py).
New deployments running from scratch will have all tables created by create_all
in main.py lifespan before Alembic runs; this migration is therefore a no-op.

Revision ID: 001_initial_tables
Revises: None
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_initial_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op — tables are created by SQLAlchemy create_all in main.py lifespan."""
    pass


def downgrade() -> None:
    """No-op — this is the baseline migration marking tables created by create_all.
    Downgrading below 001 would require dropping ALL application tables, which is
    intentionally not automated. Run 'alembic downgrade base' only if you intend
    to fully wipe the schema.
    """
    pass
