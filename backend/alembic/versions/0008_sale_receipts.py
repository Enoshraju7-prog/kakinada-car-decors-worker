"""Private immutable sales receipt metadata; legacy sales stay readable."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0008'
down_revision = '0007'


def upgrade():
    op.create_table('sale_receipts',
        sa.Column('id', sa.String(36), sa.ForeignKey('transactions.id'), primary_key=True),
        sa.Column('number', sa.Text(), nullable=False, unique=True),
        sa.Column('shop_header', JSONB(), nullable=False),
        sa.Column('encrypted_customer', sa.Text()))
    op.execute('CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON sale_receipts FOR EACH ROW EXECUTE FUNCTION protect_posted_history()')


def downgrade():
    raise RuntimeError('Restore a verified backup instead of deleting issued receipt history')
