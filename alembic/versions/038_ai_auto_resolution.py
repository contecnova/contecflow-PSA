"""Add AI auto-resolution fields to tickets.

Revision ID: 038_ai_auto_resolution
Revises: 037_sd_ai_governance_tables
Create Date: 2025-04-27 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = '038_ai_auto_resolution'
down_revision = '037_sd_ai_governance_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auto-resolution columns to sd_tickets
    op.add_column('sd_tickets', sa.Column('auto_resolved', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('sd_tickets', sa.Column('auto_resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sd_tickets', sa.Column('auto_resolved_by', sa.String(100), nullable=True))
    op.add_column('sd_tickets', sa.Column('auto_resolved_confidence', sa.Float(), nullable=True))
    op.add_column('sd_tickets', sa.Column('resolution_text', sa.Text(), nullable=True))
    op.add_column('sd_tickets', sa.Column('root_cause', sa.String(255), nullable=True))
    op.add_column('sd_tickets', sa.Column('resolution_kb_articles', sa.Text(), nullable=True))  # JSON
    
    # Create index for auto-resolved tickets
    op.create_index('ix_sd_tickets_auto_resolved', 'sd_tickets', ['auto_resolved'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_sd_tickets_auto_resolved', table_name='sd_tickets')
    
    # Drop columns
    op.drop_column('sd_tickets', 'auto_resolved')
    op.drop_column('sd_tickets', 'auto_resolved_at')
    op.drop_column('sd_tickets', 'auto_resolved_by')
    op.drop_column('sd_tickets', 'auto_resolved_confidence')
    op.drop_column('sd_tickets', 'resolution_text')
    op.drop_column('sd_tickets', 'root_cause')
    op.drop_column('sd_tickets', 'resolution_kb_articles')
