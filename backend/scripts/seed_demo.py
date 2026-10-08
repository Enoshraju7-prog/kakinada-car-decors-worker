"""Explicit synthetic seed. Never seeds a private shop database."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ledger import Ledger

ROOT = Path(__file__).resolve().parents[2]


def seed(ledger):
    products = [
        {"sku": "DEMO-MAT-7D", "name": "Demo 7D mats · Swift 2018–2023 · black", "category": "Floor mats",
         "brand": "Synthetic", "model": "7D", "compatibility": "Swift 2018–2023 (illustrative)",
         "specification": "Black", "unit": "set", "kind": "goods", "threshold": 3, "price_paise": 350000},
        {"sku": "DEMO-MAT-5D", "name": "Demo 5D mats · Swift 2018–2023 · black", "category": "Floor mats",
         "brand": "Synthetic", "model": "5D", "compatibility": "Swift 2018–2023 (illustrative)",
         "specification": "Black", "unit": "set", "kind": "goods", "threshold": 2, "price_paise": 220000},
        {"sku": "DEMO-CLOTH", "name": "Demo cleaning cloth · blue · 40 cm", "category": "Cleaning",
         "brand": "Synthetic", "model": "CL-40", "specification": "Blue / 40 cm", "unit": "piece",
         "kind": "goods", "threshold": 5, "price_paise": 15000, "conversions": {"carton": 10}},
        {"sku": "DEMO-FITTING", "name": "Demo fitting charge", "category": "Services", "unit": "service",
         "kind": "service", "threshold": 0, "price_paise": 30000},
    ]
    ids = [ledger.post("product", p, f"demo-product-{p['sku']}")["id"] for p in products]
    purchase = ledger.post("purchase", {"supplier": "Synthetic Delhi Supplier (Demo)",
        "invoice_number": "DEMO-001", "invoice_date": "2026-10-04", "lines": [
            {"product_id": ids[0], "quantity": 10, "unit": "set", "cost_paise": 200000},
            {"product_id": ids[1], "quantity": 4, "unit": "set", "cost_paise": 120000},
            {"product_id": ids[2], "quantity": 2, "unit": "carton", "cost_paise": 80000},
        ]}, "demo-purchase-001")
    ledger.post("receipt", {"purchase_id": purchase["id"], "confirmed": True, "lines": [
        {"purchase_line_id": purchase["lines"][0]["id"], "accepted": 8, "damaged": 0},
        {"purchase_line_id": purchase["lines"][1]["id"], "accepted": 1, "damaged": 1},
        {"purchase_line_id": purchase["lines"][2]["id"], "accepted": 10, "damaged": 0},
    ]}, "demo-receipt-001")
    return ids


if __name__ == "__main__":
    seed(Ledger(ROOT / "data" / "demo" / "ledger.sqlite3"))
    print("Synthetic demo catalogue and partial receipt seeded; no private shop data touched.")
