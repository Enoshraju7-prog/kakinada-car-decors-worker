"""Persist unconfirmed ordered goods without inventing stock or packaging units."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0004'
down_revision = '0003'

def upgrade():
    op.create_table('order_reviews', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payload', JSONB(), nullable=False), sa.Column('actor', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False))

def downgrade():
    raise RuntimeError('Restore a verified backup instead of deleting order evidence')
