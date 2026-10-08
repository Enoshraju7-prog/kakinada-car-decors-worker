"""Protect posted no-bill delivery identity from edits/deletion."""
from alembic import op
revision = '0006'
down_revision = '0005'

def upgrade():
    op.execute('CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON unbilled_receipts FOR EACH ROW EXECUTE FUNCTION protect_posted_history()')

def downgrade():
    raise RuntimeError('Restore a verified backup instead of removing history protection')
