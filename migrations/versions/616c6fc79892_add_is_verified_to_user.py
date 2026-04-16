"""add is_verified to user

Revision ID: 616c6fc79892
Revises: 16ee3524efa8
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '616c6fc79892'
down_revision = '16ee3524efa8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_verified',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false')  # 🔥 FIX IMPORTANT
            )
        )
        batch_op.create_index(batch_op.f('ix_user_is_verified'), ['is_verified'], unique=False)

    # 🔥 enlever le default après création (propre)
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('is_verified', server_default=None)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_is_verified'))
        batch_op.drop_column('is_verified')