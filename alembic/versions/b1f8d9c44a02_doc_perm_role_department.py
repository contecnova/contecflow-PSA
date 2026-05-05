"""document_permissions: allow grants by role or department

Adds nullable `role` and `department` columns to `document_permissions` and
makes `user_id` nullable, so a single grant row can target either a user, a
role, or a department (the application enforces "exactly one of the three").

Revision ID: b1f8d9c44a02
Revises: a3f91c2e5d80
Create Date: 2026-05-05 00:00:00.000000
"""
from typing import Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b1f8d9c44a02'
down_revision: Union[str, None] = 'a3f91c2e5d80'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('document_permissions') as batch:
        batch.add_column(sa.Column('role', sa.String(length=40), nullable=True))
        batch.add_column(sa.Column('department', sa.String(length=100), nullable=True))
        batch.alter_column('user_id', existing_type=sa.String(length=36), nullable=True)
        batch.create_index('ix_doc_perm_document_role', ['document_id', 'role'])
        batch.create_index('ix_doc_perm_document_department', ['document_id', 'department'])


def downgrade() -> None:
    with op.batch_alter_table('document_permissions') as batch:
        batch.drop_index('ix_doc_perm_document_department')
        batch.drop_index('ix_doc_perm_document_role')
        batch.alter_column('user_id', existing_type=sa.String(length=36), nullable=False)
        batch.drop_column('department')
        batch.drop_column('role')
