"""Editable AI proposals. Approval creates exact parts and an incoming bill atomically."""
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from app.infrastructure import database as db
from app.modules.catalog import service as catalog
from app.modules.purchasing.service import purchase
from app.ledger import RuleError, normalized


class IntakeLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=1, max_length=500, description='Original supplier description; do not replace source evidence')
    product_id: str | None = Field(default=None, description='Existing exact variant ID, only when the description matches unambiguously')
    name: str = Field(min_length=1, max_length=200, description='Proposed exact variant name, using only stated details; mixed assortments remain unresolved')
    family_name: str = Field(min_length=1, max_length=200, description='Suggested product family, e.g. Side mirrors')
    category: str = Field(min_length=1, max_length=200, description='Suggested category, e.g. Mirrors')
    unit: Literal['piece', 'pair', 'set', 'kit', 'box', 'carton'] | None = Field(default=None, description='Explicit source/partner unit; null when unknown. Never infer pack conversions')
    quantity: StrictInt | None = Field(default=None, ge=1, le=1000000000)
    cost_paise: StrictInt | None = Field(default=None, ge=0, le=1000000000, description='Buying rate per supplier unit in paise; null when unclear')
    amount_paise: StrictInt | None = Field(default=None, ge=0, le=1000000000000, description='Printed line amount in paise, excluding invoice tax')
    selling_price_paise: StrictInt | None = Field(default=None, ge=0, le=1000000000, description='Partner sets this during review; AI must leave null for new parts')
    issues: list[str] = Field(default_factory=list, max_length=20, description='Missing or conflicting facts; partner must resolve before saving')


class Intake(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supplier: str | None = Field(default=None, max_length=200)
    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_date: str | None = Field(default=None, max_length=10, description='YYYY-MM-DD; null if unclear, no assumed year')
    source_file_id: str | None = None
    source_note: str = Field(min_length=1, max_length=2000, description='Partner-entered text or source evidence summary; preserves manual fallback')
    lines: list[IntakeLine] = Field(min_length=1, max_length=100)


def ready(data):
    p = Intake.model_validate(data).model_dump()
    if not all((p['supplier'], p['invoice_number'], p['invoice_date'])):
        raise RuleError('Confirm supplier, bill number and printed date before recording this bill', 422)
    from datetime import date
    try:
        if date.fromisoformat(p['invoice_date']).isoformat() != p['invoice_date']:
            raise ValueError()
    except ValueError:
        raise RuleError('Confirm the printed bill date (YYYY-MM-DD)', 422)
    new_names = set()
    for line in p['lines']:
        if line['issues'] or any(line[k] is None for k in ('unit', 'quantity', 'cost_paise')):
            raise RuleError('Resolve each item, unit, quantity and buying rate before approval', 422)
        if line['amount_paise'] is not None and line['quantity'] * line['cost_paise'] != line['amount_paise']:
            raise RuleError('Quantity × buying rate must match the bill-line amount; correct or split the line', 422)
        if not line['product_id']:
            if line['selling_price_paise'] is None:
                raise RuleError('Set a selling price for every new part', 422)
            key = tuple(normalized(line[k]) for k in ('category', 'family_name', 'name', 'unit'))
            if key in new_names:
                raise RuleError('Repeated new part: combine its quantities or choose the same saved SKU', 422)
            new_names.add(key)
    return p


def post(store, conn, data, actor, key):
    p = ready(data)
    if p['source_file_id'] and not conn.execute(select(db.files.c.id).where(db.files.c.id == p['source_file_id'])).first():
        raise RuleError('Source file not found', 404)
    lines = []
    for index, line in enumerate(p['lines']):
        pid = line['product_id']
        if not pid:
            # Refuse to accidentally create an already-named variant. The partner can map it instead.
            matches = conn.execute(select(db.variants.c.id, db.variants.c.name)).all()
            if any(normalized(name) == normalized(line['name']) for _, name in matches):
                raise RuleError('A part with this exact name already exists; choose its saved SKU', 422)
            code = 'KCD-' + uuid.uuid5(uuid.NAMESPACE_URL, key + ':' + str(index)).hex[:12].upper()
            pid = catalog.legacy_product(conn, dict(sku=code, name=line['name'], family_name=line['family_name'],
                category=line['category'], kind='goods', unit=line['unit'], price_paise=line['selling_price_paise'],
                purchase_price_paise=line['cost_paise']), actor)['id']
        lines.append(dict(product_id=pid, quantity=line['quantity'], unit=line['unit'], cost_paise=line['cost_paise']))
    return purchase(store, conn, dict(supplier=p['supplier'], invoice_number=p['invoice_number'],
        invoice_date=p['invoice_date'], source_file_id=p['source_file_id'], lines=lines,
        intake_evidence=p), actor, key)
