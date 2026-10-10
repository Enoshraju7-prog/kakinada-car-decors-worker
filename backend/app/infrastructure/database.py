"""PostgreSQL storage contract. Schema changes belong to Alembic."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (BigInteger, CheckConstraint, Column, ForeignKey, Identity,
                        Index, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine)
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
metadata = MetaData()


def table(name, *columns, **kwargs):
    return Table(name, metadata, *columns, **kwargs)


def uid(name="id", target=None, primary=False, nullable=False):
    args = [ForeignKey(target)] if target else []
    return Column(name, String(36), *args, primary_key=primary, nullable=nullable)


units = table("units", Column("code", String(20), primary_key=True))
categories = table("categories", uid(primary=True), uid("parent_id", "categories.id", nullable=True),
                   Column("name", Text, nullable=False), Column("name_key", Text, nullable=False),
                   Column("threshold", Integer, nullable=False, default=0),
                   CheckConstraint("threshold >= 0"))
Index("category_sibling", categories.c.parent_id, categories.c.name_key, unique=True,
      postgresql_nulls_not_distinct=True)
products = table("catalog_products", uid(primary=True), uid("category_id", "categories.id"),
                 Column("name", Text, nullable=False), Column("brand", Text, nullable=False, default=""),
                 Column("kind", String(20), nullable=False), CheckConstraint("kind IN ('goods','service')"))
variants = table("variants", uid(primary=True), uid("product_id", "catalog_products.id"),
                 Column("sku", Text, nullable=False, unique=True), Column("name", Text, nullable=False),
                 Column("unit", String(20), ForeignKey("units.code"), nullable=False),
                 Column("model", Text, nullable=False, default=""), Column("color", Text, nullable=False, default=""),
                 Column("compatibility", Text, nullable=False, default=""),
                 Column("compatibility_status", String(20), nullable=False, default="unknown"),
                 Column("specification", Text, nullable=False, default=""),
                 Column("price_paise", BigInteger, nullable=False, default=0),
                 Column("purchase_price_paise", BigInteger),
                 Column("created_at", Text, nullable=False),
                 CheckConstraint("price_paise >= 0"),
                 CheckConstraint("purchase_price_paise IS NULL OR purchase_price_paise >= 0"),
                 CheckConstraint("compatibility_status IN ('unknown','universal','specific')"))
fitments = table("variant_fitments", uid(primary=True), uid("variant_id", "variants.id"),
                 Column("make", Text, nullable=False), Column("model", Text, nullable=False),
                 Column("generation", Text, nullable=False, default=""), Column("year_from", Integer),
                 Column("year_to", Integer), CheckConstraint("year_to IS NULL OR year_from IS NULL OR year_to >= year_from"))
conversions = table("unit_conversions", uid("variant_id", "variants.id", primary=True),
                    Column("from_unit", String(20), ForeignKey("units.code"), primary_key=True),
                    Column("factor", Integer, nullable=False), Column("confirmed_by", Text, nullable=False),
                    Column("evidence", Text, nullable=False), CheckConstraint("factor > 0"))
locations = table("locations", uid(primary=True), Column("code", Text, nullable=False, unique=True),
                  Column("name", Text, nullable=False))
balances = table("inventory_balances", uid("variant_id", "variants.id", primary=True),
                 uid("location_id", "locations.id", primary=True),
                 Column("available", BigInteger, nullable=False, default=0),
                 Column("damaged", BigInteger, nullable=False, default=0),
                 Column("quarantined", BigInteger, nullable=False, default=0),
                 CheckConstraint("available >= 0 AND damaged >= 0 AND quarantined >= 0"))
policies = table("reorder_policies", uid("variant_id", "variants.id", primary=True),
                 uid("location_id", "locations.id", primary=True), Column("threshold", Integer, nullable=False),
                 CheckConstraint("threshold >= 0"))
suppliers = table("suppliers", uid(primary=True), Column("name", Text, nullable=False), Column("gstin", Text, unique=True))
aliases = table("supplier_aliases", uid("supplier_id", "suppliers.id", primary=True),
                Column("alias_key", Text, primary_key=True), Column("confirmed_by", Text, nullable=False))
customers = table("customers", uid(primary=True), Column("phone_key", Text, nullable=False, unique=True),
                  Column("encrypted_details", Text, nullable=False), Column("created_at", Text, nullable=False),
                  Column("updated_at", Text, nullable=False))
documents = table("transactions", uid(primary=True), Column("sequence", BigInteger, Identity(), unique=True),
                  Column("kind", String(20), nullable=False), uid("parent_id", "transactions.id", nullable=True),
                  Column("actor", Text, nullable=False), Column("created_at", Text, nullable=False),
                  Column("data", JSONB, nullable=False), Column("total_paise", BigInteger, nullable=False, default=0),
                  CheckConstraint("kind IN ('purchase','receipt','sale','return','adjustment','reversal')"))
customer_sales = table("customer_sales", uid("id", "transactions.id", primary=True), uid("customer_id", "customers.id"))
Index("customer_sales_customer", customer_sales.c.customer_id)
sale_receipts = table('sale_receipts', uid('id', 'transactions.id', primary=True),
                      Column('number', Text, nullable=False, unique=True),
                      Column('shop_header', JSONB, nullable=False),
                      Column('encrypted_customer', Text))
lines = table("lines", uid(primary=True), uid("transaction_id", "transactions.id"),
              Column("sequence", BigInteger, Identity(), unique=True), uid("product_id", "variants.id"),
              uid("parent_line_id", "lines.id", nullable=True), Column("quantity", BigInteger, nullable=False),
              Column("damaged", BigInteger, nullable=False, default=0), Column("quarantined", BigInteger, nullable=False, default=0),
              Column("price_paise", BigInteger, nullable=False, default=0), Column("snapshot", JSONB, nullable=False),
              CheckConstraint("quantity > 0 AND damaged >= 0 AND quarantined >= 0 AND damaged + quarantined <= quantity AND price_paise >= 0"))
movements = table("movements", uid(primary=True), Column("sequence", BigInteger, Identity(), unique=True),
                  uid("transaction_id", "transactions.id"), uid("line_id", "lines.id"), uid("product_id", "variants.id"),
                  uid("location_id", "locations.id"), Column("available_delta", BigInteger, nullable=False),
                  Column("damaged_delta", BigInteger, nullable=False), Column("quarantined_delta", BigInteger, nullable=False, default=0),
                  Column("actor", Text, nullable=False), Column("created_at", Text, nullable=False),
                  Column("operation_id", Text, nullable=False), uid("reversal_of", "movements.id", nullable=True),
                  UniqueConstraint("line_id", "location_id"), UniqueConstraint("reversal_of"),
                  CheckConstraint("available_delta <> 0 OR damaged_delta <> 0 OR quarantined_delta <> 0"))
purchase_headers = table("purchase_documents", uid("id", "transactions.id", primary=True), uid("supplier_id", "suppliers.id"),
                         Column("invoice_key", Text, nullable=False), Column("financial_year", Text, nullable=False),
                         Column("invoice_date", Text, nullable=False), Column("source_file_id", String(36), ForeignKey("source_files.id")),
                         UniqueConstraint("supplier_id", "financial_year", "invoice_key"))
receipt_headers = table("receipt_documents", uid("id", "transactions.id", primary=True), uid("purchase_id", "purchase_documents.id"),
                        uid("location_id", "locations.id"), Column("confirmed_by", Text, nullable=False))
unbilled_receipts = table('unbilled_receipts', uid('id', 'transactions.id', primary=True),
    Column('supplier_key', Text, nullable=False), Column('reference_key', Text, nullable=False),
    UniqueConstraint('supplier_key', 'reference_key'))
requests = table("requests", Column("key", Text, primary_key=True), Column("fingerprint", Text, nullable=False),
                 Column("actor", Text, nullable=False), Column("response", JSONB), Column("legacy", Integer, nullable=False, default=0))
drafts = table("drafts", uid(primary=True), Column("kind", Text, nullable=False), Column("payload", JSONB, nullable=False),
               Column("version", Integer, nullable=False, default=1), Column("status", Text, nullable=False, default="pending"),
               Column("actor", Text, nullable=False), Column("created_at", Text, nullable=False),
               Column("approved_by", Text), Column("approved_hash", Text), uid("posted_id", "transactions.id", nullable=True))
users = table("users", uid(primary=True), Column("username", Text, nullable=False, unique=True),
              Column("password_hash", Text, nullable=False), Column("role", Text, nullable=False),
              CheckConstraint("role IN ('partner','staff')"))
sessions = table("sessions", Column("token_hash", Text, primary_key=True), uid("user_id", "users.id"),
                 Column("csrf", Text, nullable=False), Column("expires_at", BigInteger, nullable=False))
audit = table("audit_events", uid(primary=True), Column("actor", Text, nullable=False), Column("event", Text, nullable=False),
              Column("source_id", Text, nullable=False), Column("created_at", Text, nullable=False), Column("data", JSONB, nullable=False))
outbox = table("outbox_events", uid(primary=True), Column("event", Text, nullable=False),
               Column("source_id", Text, nullable=False), Column("payload", JSONB, nullable=False),
               Column("status", Text, nullable=False, default="pending"), Column("attempts", Integer, nullable=False, default=0),
               Column("lease_until", BigInteger, nullable=False, default=0), Column("error", Text))
consumed = table("consumed_events", Column("event_id", String(36), ForeignKey("outbox_events.id"), primary_key=True),
                 Column("consumer", Text, primary_key=True), Column("created_at", Text, nullable=False))
files = table("source_files", uid(primary=True), Column("sha256", Text, nullable=False, unique=True),
              Column("name", Text, nullable=False), Column("media_type", Text, nullable=False),
              Column("path", Text, nullable=False), Column("actor", Text, nullable=False), Column("extraction", JSONB))
runs = table("agent_runs", uid(primary=True), Column("goal", Text, nullable=False), Column("actor", Text, nullable=False),
             Column("status", Text, nullable=False, default="pending"), Column("messages", JSONB, nullable=False, default=list),
             Column("evidence", JSONB), Column("error", Text), Column("lease_until", BigInteger, nullable=False, default=0),
             Column("requests_used", Integer, nullable=False, default=0), Column("tools_used", Integer, nullable=False, default=0),
             Column("created_at", Text, nullable=False), Column("attachments", JSONB, nullable=False, default=list))
steps = table("agent_steps", uid(primary=True), uid("run_id", "agent_runs.id"),
              Column("sequence", BigInteger, Identity(), unique=True), Column("tool", Text, nullable=False),
              Column("arguments", JSONB, nullable=False), Column("result", JSONB, nullable=False), Column("created_at", Text, nullable=False))
reports = table("reports", uid(primary=True), uid("run_id", "agent_runs.id"),
                Column("data", JSONB, nullable=False), Column("created_at", Text, nullable=False))
order_reviews = table('order_reviews', uid(primary=True), Column('payload', JSONB, nullable=False),
                      Column('actor', Text, nullable=False), Column('created_at', Text, nullable=False))
Index("movements_sku_location", movements.c.product_id, movements.c.location_id, movements.c.sequence)
Index("lines_source", lines.c.parent_line_id)
Index("lines_document", lines.c.transaction_id)

LOCATION_ID = "00000000-0000-4000-8000-000000000001"


def engine_for(url=None):
    url = url or os.getenv("KCD_DATABASE_URL", "")
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("Set KCD_DATABASE_URL to the dedicated PostgreSQL database; run scripts/setup_local.py first")
    return create_engine(url, pool_pre_ping=True, isolation_level="READ COMMITTED", connect_args={"connect_timeout":5})
