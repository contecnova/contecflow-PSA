"""add_ml_prediction_tables

Revision ID: a3c1d8f92e05
Revises: f19763b1c208
Create Date: 2026-04-26 10:00:00.000000

Creates two tables for ML-powered project overrun prediction:
  ml_models          — serialized scikit-learn models (one active per org)
  ml_prediction_logs — per-project prediction history for drift monitoring
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'a3c1d8f92e05'
down_revision: Union[str, None] = 'f19763b1c208'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ml_models ──────────────────────────────────────────────────────────────
    op.create_table(
        'ml_models',
        sa.Column('id',              sa.String(36),  primary_key=True),
        sa.Column('organization_id', sa.String(36),  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('model_type',      sa.String(30),  nullable=False, server_default='overrun'),
        sa.Column('version',         sa.Integer(),   nullable=False, server_default='1'),
        sa.Column('trained_at',      sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('samples_used',    sa.Integer(),   nullable=False, server_default='0'),
        sa.Column('accuracy',        sa.Float(),     nullable=True),
        sa.Column('feature_names',   sa.Text(),      nullable=True),
        sa.Column('is_active',       sa.Boolean(),   nullable=False, server_default=sa.true()),
        sa.Column('model_bytes',     sa.LargeBinary(), nullable=True),
    )
    op.create_index('ix_ml_models_organization_id', 'ml_models', ['organization_id'])

    # ── ml_prediction_logs ─────────────────────────────────────────────────────
    op.create_table(
        'ml_prediction_logs',
        sa.Column('id',                    sa.String(36), primary_key=True),
        sa.Column('organization_id',       sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ml_model_id',           sa.String(36), sa.ForeignKey('ml_models.id',     ondelete='SET NULL'), nullable=True),
        sa.Column('project_id',            sa.String(36), sa.ForeignKey('projects.id',       ondelete='CASCADE'), nullable=False),
        sa.Column('features_json',         sa.Text(),     nullable=True),
        sa.Column('cost_overrun_prob',     sa.Float(),    nullable=True),
        sa.Column('schedule_overrun_prob', sa.Float(),    nullable=True),
        sa.Column('risk_level',            sa.String(20), nullable=True),
        sa.Column('used_heuristic',        sa.Boolean(),  nullable=False, server_default=sa.true()),
        sa.Column('did_cost_overrun',      sa.Boolean(),  nullable=True),
        sa.Column('did_schedule_overrun',  sa.Boolean(),  nullable=True),
        sa.Column('predicted_at',          sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ml_prediction_logs_organization_id', 'ml_prediction_logs', ['organization_id'])
    op.create_index('ix_ml_prediction_logs_project_id',      'ml_prediction_logs', ['project_id'])


def downgrade() -> None:
    op.drop_table('ml_prediction_logs')
    op.drop_table('ml_models')
