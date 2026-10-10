"""Encrypted partner-only customer profiles and immutable purchase links."""
from alembic import op
import sqlalchemy as sa
revision = '0007'
down_revision = '0006'


def upgrade():
    op.create_table('customers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('phone_key', sa.Text(), nullable=False, unique=True),
        sa.Column('encrypted_details', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False))
    op.create_table('customer_sales',
        sa.Column('id', sa.String(36), sa.ForeignKey('transactions.id'), primary_key=True),
        sa.Column('customer_id', sa.String(36), sa.ForeignKey('customers.id'), nullable=False))
    op.create_index('customer_sales_customer', 'customer_sales', ['customer_id'])
    op.execute('CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON customer_sales FOR EACH ROW EXECUTE FUNCTION protect_posted_history()')


def downgrade():
    raise RuntimeError('Restore a verified backup instead of deleting customer purchase history')
