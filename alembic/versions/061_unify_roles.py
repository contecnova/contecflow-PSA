"""unify user roles: change users.role from Enum to String

Revision ID: 061_unify_roles
Revises: b1f8d9c44a02
Create Date: 2026-05-05

"""
from alembic import op
import sqlalchemy as sa

revision = '061_unify_roles'
down_revision = 'b1f8d9c44a02'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'role',
            type_=sa.String(100),
            existing_type=sa.Enum(
                'admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor',
                name='userrole',
            ),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'role',
            type_=sa.Enum(
                'admin', 'pm', 'team_lead', 'hr', 'employee', 'subcontractor',
                name='userrole',
            ),
            existing_type=sa.String(100),
            existing_nullable=False,
        )
