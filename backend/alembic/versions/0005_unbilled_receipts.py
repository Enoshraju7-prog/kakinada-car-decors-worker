"""Physical goods received without inventing a supplier invoice."""
from alembic import op
import sqlalchemy as sa
revision = '0005'
down_revision = '0004'

def upgrade():
    op.create_table('unbilled_receipts',
        sa.Column('id', sa.String(36), sa.ForeignKey('transactions.id'), primary_key=True),
        sa.Column('supplier_key', sa.Text(), nullable=False),
        sa.Column('reference_key', sa.Text(), nullable=False),
        sa.UniqueConstraint('supplier_key', 'reference_key'))

def downgrade():
    raise RuntimeError('Restore a verified backup instead of deleting receiving evidence')
