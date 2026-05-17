"""pg_trgm search indexes for high-traffic LIKE/ILIKE lookups.

Revision ID: 083_pg_trgm_search_indexes
Revises: 082_multitenancy_fix_unregistered_models
Create Date: 2026-05-16
"""

from alembic import op


revision = "083_pg_trgm_search_indexes"
down_revision = "082_multitenancy_fix_unregistered_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_full_name_trgm "
        "ON users USING gin (full_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_username_trgm "
        "ON users USING gin (username gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_email_trgm "
        "ON users USING gin (email gin_trgm_ops)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_clients_name_trgm "
        "ON clients USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_clients_short_name_trgm "
        "ON clients USING gin (short_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_clients_contact_email_trgm "
        "ON clients USING gin (contact_email gin_trgm_ops)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_name_trgm "
        "ON projects USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_title_trgm "
        "ON tasks USING gin (title gin_trgm_ops)"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tickets_title_trgm "
        "ON tickets USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tickets_number_trgm "
        "ON tickets USING gin (number gin_trgm_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS idx_tickets_number_trgm")
    op.execute("DROP INDEX IF EXISTS idx_tickets_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_tasks_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_projects_name_trgm")

    op.execute("DROP INDEX IF EXISTS idx_clients_contact_email_trgm")
    op.execute("DROP INDEX IF EXISTS idx_clients_short_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_clients_name_trgm")

    op.execute("DROP INDEX IF EXISTS idx_users_email_trgm")
    op.execute("DROP INDEX IF EXISTS idx_users_username_trgm")
    op.execute("DROP INDEX IF EXISTS idx_users_full_name_trgm")
