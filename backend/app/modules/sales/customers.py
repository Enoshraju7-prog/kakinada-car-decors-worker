"""PII stays encrypted here, outside transaction/agent/audit payloads."""
import hashlib
import hmac
import json
import os
import re
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.infrastructure import database as db
from app.legacy_main import Input
from app.ledger import RuleError, identifier, now


class CustomerDetails(Input):
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=1, max_length=30)
    address: str = Field(default='', max_length=500)


class CustomerPhone(Input):
    phone: str = Field(min_length=1, max_length=30)


def phone_number(value):
    # Pilot supports Indian mobile numbers only; do not guess international codes.
    if not isinstance(value, str) or not re.fullmatch(r'[+\d\s().-]+', value):
        raise RuleError('Enter a valid 10-digit Indian mobile number', 422)
    digits = re.sub(r'\D', '', value)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    if not re.fullmatch(r'[6-9]\d{9}', digits):
        raise RuleError('Enter a valid 10-digit Indian mobile number', 422)
    return '+91' + digits


def cipher():
    try:
        keys = os.environ['KCD_CUSTOMER_ENCRYPTION_KEYS'].split(',')
        return MultiFernet([Fernet(k.strip().encode()) for k in keys])
    except (KeyError, ValueError, TypeError):
        raise RuleError('Customer storage is not configured. Contact a partner; no sale was saved.', 503) from None


def phone_key(phone):
    key = os.getenv('KCD_CUSTOMER_LOOKUP_KEY', '')
    if len(key) < 64:
        raise RuleError('Customer storage is not configured. Contact a partner; no sale was saved.', 503)
    return hmac.new(key.encode(), phone.encode(), hashlib.sha256).hexdigest()


def details(row):
    try:
        return {'id': row['id'], **json.loads(cipher().decrypt(row['encrypted_details'].encode()))}
    except (InvalidToken, json.JSONDecodeError):
        raise RuleError('Customer details could not be opened. Contact a partner.', 503) from None


def save_customer(conn, payload, actor):
    role = conn.execute(select(db.users.c.role).where(db.users.c.username == actor)).scalar()
    if role != 'partner':
        raise RuleError('Only partners can access customer details', 403)
    value = CustomerDetails.model_validate(payload)
    profile = {'name': value.name.strip(), 'phone': phone_number(value.phone), 'address': value.address.strip()}
    if not profile['name']:
        raise RuleError('Enter the customer name', 422)
    encrypted = cipher().encrypt(json.dumps(profile).encode()).decode()
    lookup = phone_key(profile['phone'])
    if value.id:
        saved = conn.execute(select(db.customers).where(db.customers.c.id == value.id).with_for_update()).mappings().first()
        if not saved or saved['phone_key'] != lookup:
            raise RuleError('Phone changed. Find the customer again before saving.', 409)
    else:
        conn.execute(insert(db.customers).values(id=identifier(), phone_key=lookup, encrypted_details=encrypted,
            created_at=now(), updated_at=now()).on_conflict_do_nothing(index_elements=['phone_key']))
        saved = conn.execute(select(db.customers).where(db.customers.c.phone_key == lookup).with_for_update()).mappings().one()
        if {k: v for k, v in details(saved).items() if k != 'id'} != profile:
            raise RuleError('This phone has a saved customer. Choose Find customer to review their details.', 409)
    conn.execute(db.customers.update().where(db.customers.c.id == saved['id']).values(encrypted_details=encrypted, updated_at=now()))
    return saved['id']


def lookup_customer(conn, phone):
    row = conn.execute(select(db.customers).where(db.customers.c.phone_key == phone_key(phone_number(phone)))).mappings().first()
    return details(row) if row else None


def customer_history(conn, customer_id, limit=20, offset=0):
    row = conn.execute(select(db.customers).where(db.customers.c.id == customer_id)).mappings().first()
    if not row:
        raise RuleError('Customer not found', 404)
    sales = conn.execute(select(db.documents.c.id, db.documents.c.created_at, db.documents.c.total_paise,
        db.documents.c.data).join(db.customer_sales, db.customer_sales.c.id == db.documents.c.id)
        .where(db.customer_sales.c.customer_id == customer_id)
        .order_by(db.documents.c.sequence.desc()).offset(offset).limit(limit + 1)).mappings().all()
    items = {s['id']: [] for s in sales[:limit]}
    if items:
        for line in conn.execute(select(db.lines).where(db.lines.c.transaction_id.in_(items))
                                 .order_by(db.lines.c.sequence)).mappings():
            items[line['transaction_id']].append({'name': line['snapshot']['name'],
                'sku': line['snapshot']['sku'], 'quantity': line['quantity'], 'unit': line['snapshot']['unit']})
    return {'customer': details(row), 'has_more': len(sales) > limit, 'purchases': [
        {'id': s['id'], 'created_at': s['created_at'], 'total_paise': s['total_paise'],
         'payment': s['data']['payment'], 'items': items[s['id']]} for s in sales[:limit]]}
