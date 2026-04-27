"""add scheduled_report BI fields

Revision ID: c4e5f2a83d17
Revises: b7e2c4a91f03
Create Date: 2026-04-26 12:00:00.000000
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4e5f2a83d17'
down_revision: Union[str, None] = 'b7e2c4a91f03'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scheduled_reports', sa.Column('report_type', sa.String(50), nullable=True, server_default='custom'))
    op.add_column('scheduled_reports', sa.Column('include_narrative', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('scheduled_reports', sa.Column('day_of_week', sa.Integer(), nullable=True))
    op.add_column('scheduled_reports', sa.Column('day_of_month', sa.Integer(), nullable=True))
    op.add_column('scheduled_reports', sa.Column('send_hour', sa.Integer(), nullable=True, server_default='8'))
    op.add_column('scheduled_reports', sa.Column('recipients_extra', sa.Text(), nullable=True, server_default='[]'))
    op.add_column('scheduled_reports', sa.Column('slack_webhook', sa.String(500), nullable=True))
    op.add_column('scheduled_reports', sa.Column('last_status', sa.String(20), nullable=True))
    op.add_column('scheduled_reports', sa.Column('last_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('scheduled_reports', 'last_error')
    op.drop_column('scheduled_reports', 'last_status')
    op.drop_column('scheduled_reports', 'slack_webhook')
    op.drop_column('scheduled_reports', 'recipients_extra')
    op.drop_column('scheduled_reports', 'send_hour')
    op.drop_column('scheduled_reports', 'day_of_month')
    op.drop_column('scheduled_reports', 'day_of_week')
    op.drop_column('scheduled_reports', 'include_narrative')
    op.drop_column('scheduled_reports', 'report_type')
