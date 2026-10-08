"""Catalogue operations: families organize; only variants own inventory."""
from sqlalchemy import select
from app.infrastructure import database as db
from app.ledger import RuleError, identifier, integer, normalized, now, required


def category(conn, data):
    parent = data.get("parent_id")
    if parent and not conn.execute(select(db.categories.c.id).where(db.categories.c.id == parent)).first():
        raise RuleError("Parent category not found", 404)
    name = required(data["name"], "Category")
    result = dict(id=identifier(), parent_id=parent, name=name, name_key=normalized(name),
                  threshold=integer(data.get("threshold", 0), "Threshold"))
    conn.execute(db.categories.insert().values(**result))
    return result


def prices(conn, data):
    old = conn.execute(select(db.variants).where(db.variants.c.id == data['id']).with_for_update()).mappings().first()
    if not old:
        raise RuleError('SKU not found', 404)
    if old['price_paise'] != data['expected_price_paise'] or old['purchase_price_paise'] != data['expected_purchase_price_paise']:
        raise RuleError('Prices changed; refresh before saving')
    selling = integer(data['price_paise'], 'Selling price')
    cost = None if data['purchase_price_paise'] is None else integer(data['purchase_price_paise'], 'Purchase price')
    conn.execute(db.variants.update().where(db.variants.c.id == old['id']).values(price_paise=selling, purchase_price_paise=cost))
    return {'id': old['id'], 'price_paise': selling, 'purchase_price_paise': cost,
            'before': {'price_paise': old['price_paise'], 'purchase_price_paise': old['purchase_price_paise']}}


def product(conn, data):
    if not conn.execute(select(db.categories.c.id).where(db.categories.c.id == data["category_id"])).first():
        raise RuleError("Category not found", 404)
    if data.get("kind", "goods") not in {"goods", "service"}:
        raise RuleError("Choose goods or service", 422)
    result = dict(id=identifier(), category_id=data["category_id"], name=required(data["name"], "Product"),
                  brand=data.get("brand", ""), kind=data.get("kind", "goods"))
    conn.execute(db.products.insert().values(**result))
    return result


def variant(conn, data, actor, variant_id=None):
    family = conn.execute(select(db.products).where(db.products.c.id == data["product_id"])).mappings().first()
    if not family:
        raise RuleError("Product family not found", 404)
    unit = data["unit"]
    if unit not in {"piece", "pair", "set", "kit", "box", "carton", "service"} or (unit == "service") != (family["kind"] == "service"):
        raise RuleError("Choose a goods unit, or service for fitting", 422)
    packs = data.get("conversions", {})
    for pack, factor in packs.items():
        if pack not in {"piece", "pair", "set", "kit", "box", "carton"} or pack == unit or family["kind"] == "service":
            raise RuleError("Choose a different confirmed pack unit", 422)
        integer(factor, "Conversion", 1)
    status = data.get("compatibility_status", "unknown")
    fitments = data.get("fitments", [])
    if status not in {"unknown", "specific", "universal"} or (status == "specific" and not fitments):
        raise RuleError("Specific compatibility requires fitments", 422)
    if status != "specific" and fitments:
        raise RuleError("Fitments require specific compatibility", 422)
    row = dict(id=variant_id or identifier(), product_id=family["id"], sku=required(data["sku"], "SKU").upper(),
               name=required(data.get("name", family["name"]), "Variant name"), unit=unit,
               model=data.get("model", ""), color=data.get("color", ""), compatibility=data.get("compatibility", ""),
               compatibility_status=status, specification=data.get("specification", ""),
               price_paise=integer(data.get("price_paise", 0), "Price"), created_at=data.get("created_at", now()))
    row['purchase_price_paise'] = None if data.get('purchase_price_paise') is None else integer(data['purchase_price_paise'], 'Purchase price')
    conn.execute(db.variants.insert().values(**row))
    for f in fitments:
        if f.get("year_from") is not None and f.get("year_to") is not None and f["year_from"] > f["year_to"]:
            raise RuleError("Fitment years are reversed", 422)
        conn.execute(db.fitments.insert().values(id=identifier(), variant_id=row["id"],
                     make=required(f["make"], "Vehicle make"), model=required(f["model"], "Vehicle model"),
                     generation=f.get("generation", ""), year_from=f.get("year_from"), year_to=f.get("year_to")))
    for pack, factor in packs.items():
        conn.execute(db.conversions.insert().values(variant_id=row["id"], from_unit=pack, factor=factor,
                     confirmed_by=actor, evidence=data.get("conversion_evidence", "Explicit catalogue entry")))
    if family["kind"] == "goods":
        for location_id in conn.execute(select(db.locations.c.id)).scalars():
            conn.execute(db.balances.insert().values(variant_id=row["id"], location_id=location_id,
                         available=0, damaged=0, quarantined=0))
            if data.get("threshold") is not None:
                conn.execute(db.policies.insert().values(variant_id=row["id"], location_id=location_id,
                             threshold=integer(data["threshold"], "Threshold")))
    return {"id": row["id"], "sku": row["sku"]}


def legacy_product(conn, data, actor, variant_id=None):
    name_key = normalized(required(data["category"], "Category"))
    c = conn.execute(select(db.categories).where(db.categories.c.parent_id.is_(None), db.categories.c.name_key == name_key)).mappings().first()
    if not c:
        c = category(conn, {"name": data["category"]})
    family_name = data.get('family_name')
    if family_name:
        # Explicit partner naming is the only grouping signal; serialize per category.
        conn.execute(select(db.categories.c.id).where(db.categories.c.id == c['id']).with_for_update())
        matches = [dict(r) for r in conn.execute(select(db.products).where(db.products.c.category_id == c['id'],
                   db.products.c.kind == data['kind'])).mappings() if normalized(r['name']) == normalized(family_name)]
        if len(matches) > 1:
            raise RuleError('Several families have this name; choose a specific family in the advanced catalogue', 422)
        family = matches[0] if matches else product(conn, {'name': family_name, 'category_id': c['id'],
                   'brand': data.get('brand', ''), 'kind': data['kind']})
    else:
        family = product(conn, {"name": data["name"], "category_id": c["id"], "brand": data.get("brand", ""), "kind": data["kind"]})
    return variant(conn, {**data, "product_id": family["id"]}, actor, variant_id)


def get_variant(conn, variant_id):
    q = select(db.variants, db.products.c.kind, db.products.c.brand, db.categories.c.name.label("category"),
               db.categories.c.threshold.label("category_threshold")).select_from(db.variants.join(db.products, db.variants.c.product_id == db.products.c.id).join(db.categories, db.products.c.category_id == db.categories.c.id))
    row = conn.execute(q.where(db.variants.c.id == variant_id)).mappings().first()
    if not row:
        raise RuleError("SKU not found", 404)
    result = dict(row)
    result["conversions"] = dict(conn.execute(select(db.conversions.c.from_unit, db.conversions.c.factor)
                                             .where(db.conversions.c.variant_id == variant_id)).all())
    return result
