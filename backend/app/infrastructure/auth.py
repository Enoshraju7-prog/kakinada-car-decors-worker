import hashlib
import secrets
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import select
from app.infrastructure import database as db
from app.ledger import RuleError, identifier

hasher = PasswordHasher()


def create_user(engine, username, password, role):
    if role not in {"partner", "staff"} or len(password) < 12:
        raise RuleError("Use partner/staff role and a password of at least 12 characters", 422)
    with engine.begin() as conn:
        conn.execute(db.users.insert().values(id=identifier(), username=username.strip().casefold(),
                     password_hash=hasher.hash(password), role=role))


def login(engine, username, password):
    with engine.begin() as conn:
        user = conn.execute(select(db.users).where(db.users.c.username == username.strip().casefold())).mappings().first()
        try:
            if not user or not hasher.verify(user["password_hash"], password):
                raise RuleError("Invalid username or password", 401)
        except (VerifyMismatchError, VerificationError):
            raise RuleError("Invalid username or password", 401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        conn.execute(db.sessions.insert().values(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     user_id=user["id"], csrf=csrf, expires_at=int(time.time()) + 8 * 3600))
        return token, {"id": user["id"], "username": user["username"], "role": user["role"], "csrf": csrf}


def principal(engine, token):
    if not token:
        raise RuleError("Sign in to the shop workspace", 401)
    with engine.connect() as conn:
        row = conn.execute(select(db.users.c.id, db.users.c.username, db.users.c.role, db.sessions.c.csrf)
            .select_from(db.users.join(db.sessions, db.users.c.id == db.sessions.c.user_id)).where(db.sessions.c.token_hash == hashlib.sha256(token.encode()).hexdigest(),
                                    db.sessions.c.expires_at > int(time.time()))).mappings().first()
        if not row:
            raise RuleError("Session expired; sign in again", 401)
        return dict(row)


def require_partner(user):
    if user["role"] != "partner":
        raise RuleError("A partner must approve this operation", 403)


def redact_catalogue(row, role):
    return dict(row) if role == 'partner' else {k: v for k, v in row.items() if k != 'purchase_price_paise'}


def redact_transaction(tx, role):
    private_cost = tx['kind'] == 'purchase' or tx['data'].get('source_type') == 'without_bill'
    if role == "partner" or not private_cost:
        return tx
    # Explicit allowlist; never serialize purchase snapshots or totals to staff.
    return {"id": tx["id"], "kind": tx['kind'], "parent_id": tx["parent_id"], "actor": tx["actor"],
            "created_at": tx["created_at"], "reversed": tx.get("reversed", False),
            "data": {k: tx["data"][k] for k in ("supplier", "invoice_number", "invoice_date", "source_type", "reference", "received_date") if k in tx["data"]},
            "lines": [{k: l[k] for k in ("id", "product_id", "quantity", "damaged", "quarantined", "received", "outstanding") if k in l}
                      | {"snapshot": {k: l["snapshot"][k] for k in ("sku", "name", "unit", "kind")}} for l in tx["lines"]],
            "movements": []}
