"""044 - Merge Alembic heads for portal conversations and RCA wizard

Unifies branch heads so databases on either branch can upgrade to a single
canonical head and receive both portal and RCA wizard schema changes.

Revision ID: 044_merge_heads_rca_wizard_portal
Revises: 042_routing_feedback, d2a3b8e7f041
Create Date: 2026-04-28
"""

from __future__ import annotations


revision = "044_merge_heads_rca_wizard_portal"
down_revision = ("042_routing_feedback", "d2a3b8e7f041")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge-only revision: schema changes are in parent branches.
    pass


def downgrade() -> None:
    # No-op for merge revision.
    pass
