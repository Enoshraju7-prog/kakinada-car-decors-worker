"""Separate reference purchase cost from selling price and immutable invoice costs."""
from alembic import op
import sqlalchemy as sa
revision = '0003'
down_revision = '0002'

def upgrade():
    op.add_column('variants', sa.Column('purchase_price_paise', sa.BigInteger(), nullable=True))
    op.create_check_constraint('variant_purchase_price_nonnegative', 'variants', 'purchase_price_paise IS NULL OR purchase_price_paise >= 0')

def downgrade():
    raise RuntimeError('Restore a verified backup instead of dropping price history')
