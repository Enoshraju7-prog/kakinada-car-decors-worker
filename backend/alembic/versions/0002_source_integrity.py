"""Enforce file provenance and catalogue identity immutability after first use."""
from alembic import op
revision='0002'
down_revision='0001'

def upgrade():
    op.create_foreign_key('purchase_source_file','purchase_documents','source_files',['source_file_id'],['id'])
    op.execute("""
      CREATE FUNCTION protect_variant_identity() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (NEW.unit <> OLD.unit OR NEW.product_id <> OLD.product_id OR NEW.sku <> OLD.sku)
          AND EXISTS (SELECT 1 FROM lines WHERE product_id=OLD.id) THEN
          RAISE EXCEPTION 'posted SKU identity and base unit cannot be reinterpreted';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER protect_identity BEFORE UPDATE ON variants FOR EACH ROW EXECUTE FUNCTION protect_variant_identity();
      CREATE FUNCTION protect_conversion() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        RAISE EXCEPTION 'confirmed conversions are immutable; add a separately reviewed unit instead';
      END $$;
      CREATE TRIGGER protect_conversion BEFORE UPDATE OR DELETE ON unit_conversions FOR EACH ROW EXECUTE FUNCTION protect_conversion();
    """)

def downgrade():
    raise RuntimeError('Restore a verified backup into a fresh database instead of destructive downgrade')
