"""Add client_user_projects M2M table for multi-project portal access.

Revision ID: 019
Revises: 018_drop_user_refresh_token_jti
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018_drop_user_refresh_token_jti'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'client_user_projects',
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('project_id',     sa.String(36), sa.ForeignKey('projects.id',      ondelete='CASCADE'), primary_key=True),
    )
    # Back-fill from existing legacy project_id column using portable Python approach
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, project_id FROM client_users WHERE project_id IS NOT NULL")
    ).fetchall()
    for row in rows:
        try:
            conn.execute(
                sa.text("INSERT INTO client_user_projects (client_user_id, project_id) VALUES (:cuid, :pid)"),
                {"cuid": row[0], "pid": row[1]},
            )
        except Exception:
            pass  # Skip duplicates gracefully (PK violation)


def downgrade() -> None:
    op.drop_table('client_user_projects')
