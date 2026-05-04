"""document_approval_workflow_integration

Revision ID: 050_doc_approval_wf
Revises: f19763b1c208
Create Date: 2026-05-03 00:00:00.000000

Links documents to the multi-level approval engine:
  - documents.approval_request_id FK → approval_requests.id
"""
from alembic import op
import sqlalchemy as sa

revision = '050_doc_approval_wf'
down_revision = 'f19763b1c208'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents') as batch_op:
        batch_op.add_column(
            sa.Column('approval_request_id', sa.String(36), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_documents_approval_request_id',
            'approval_requests',
            ['approval_request_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_documents_approval_request_id', ['approval_request_id'])


def downgrade():
    with op.batch_alter_table('documents') as batch_op:
        batch_op.drop_index('ix_documents_approval_request_id')
        batch_op.drop_constraint('fk_documents_approval_request_id', type_='foreignkey')
        batch_op.drop_column('approval_request_id')
