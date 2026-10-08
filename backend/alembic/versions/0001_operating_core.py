"""Initial reviewed operating core. Snapshot: no generated schema at app startup."""
from alembic import op
from sqlalchemy import text
from pathlib import Path
import importlib.util
_spec=importlib.util.spec_from_file_location("kcd_schema_v1",Path(__file__).resolve().parents[1]/"schema_v1.py")
_schema=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schema)
metadata,units,locations,LOCATION_ID=_schema.metadata,_schema.units,_schema.locations,_schema.LOCATION_ID

revision = "0001"
down_revision = None


def upgrade():
    connection = op.get_bind()
    metadata.create_all(connection)
    connection.execute(units.insert(), [{"code": x} for x in ("piece", "pair", "set", "kit", "box", "carton", "service")])
    connection.execute(locations.insert().values(id=LOCATION_ID, code="KAK-STORES", name="Kakinada store"))
    connection.execute(text("""
      CREATE FUNCTION protect_posted_history() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'posted history is immutable'; END $$;
    """))
    for name in ("transactions", "lines", "movements", "purchase_documents", "receipt_documents", "audit_events", "agent_steps"):
        connection.execute(text(f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION protect_posted_history()"))


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled. Restore a verified backup into a fresh database.")
