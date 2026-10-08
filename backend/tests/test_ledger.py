import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.ledger import Ledger, RuleError


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Ledger(Path(self.temp.name) / "ledger.sqlite3")
        self.sequence = 0
        self.product = self.create_product()

    def post(self, operation, data, key=None):
        self.sequence += 1
        return self.ledger.post(operation, data, key or f"test-{self.sequence}", "test-partner")

    def create_product(self, **extra):
        return self.post("product", {"sku": "TEST-MAT", "name": "Synthetic mat", "category": "Mats",
            "unit": "set", "kind": "goods", "threshold": 3, "price_paise": 10001, **extra})["id"]

    def purchase(self, quantity=10, **extra):
        return self.post("purchase", {"supplier": "Synthetic supplier", "invoice_number": "A-001",
            "invoice_date": "2026-10-04", "lines": [{"product_id": self.product,
                "quantity": quantity, "unit": "set", "cost_paise": 12345}], **extra})

    def receive(self, purchase, accepted, damaged=0, key=None):
        return self.post("receipt", {"purchase_id": purchase["id"], "confirmed": True,
            "lines": [{"purchase_line_id": purchase["lines"][0]["id"], "accepted": accepted,
                       "damaged": damaged}]}, key)

    def sale(self, quantity=1, key=None, **extra):
        return self.post("sale", {"payment": "cash", "lines": [
            {"product_id": self.product, "quantity": quantity, "price_paise": 10001}], **extra}, key)

    def balance(self):
        return next(p for p in self.ledger.state()["products"] if p["id"] == self.product)

    def test_receive_ten_sell_three_traceable_and_persistent(self):
        purchase = self.purchase()
        self.assertEqual(self.balance()["available"], 0)
        receipt = self.receive(purchase, 10)
        sale = self.sale(3)
        self.assertEqual(self.balance()["available"], 7)
        self.assertEqual(sale["total_paise"], 30003)
        self.assertEqual(self.ledger.transaction(sale["id"]), sale)
        self.assertEqual(receipt["movements"][0]["actor"], "test-partner")
        reopened = Ledger(self.ledger.path)
        self.assertEqual(reopened.state(), self.ledger.state())

    def test_exact_sku_low_stock(self):
        self.receive(self.purchase(), 5)
        self.sale(3)
        self.assertTrue(self.balance()["low_stock"])
        self.assertEqual(self.balance()["available"], 2)

    def test_duplicate_business_identity_another_request(self):
        self.purchase()
        with self.assertRaises(RuleError):
            self.purchase(supplier=" SYNTHETIC   supplier ", invoice_number=" a-001 ")
        self.assertEqual(len(self.ledger.state()["transactions"]), 1)
        # Same number can recur next financial year.
        self.purchase(invoice_date="2027-05-01")
        self.assertEqual(len(self.ledger.state()["transactions"]), 2)

    def test_partial_receipt_incoming_and_damaged(self):
        purchase = self.purchase()
        self.receive(purchase, 7, 1)
        balance = self.balance()
        self.assertEqual((balance["available"], balance["damaged"], balance["incoming"]), (7, 1, 2))
        self.assertEqual(self.ledger.transaction(purchase["id"])["lines"][0]["outstanding"], 2)
        self.receive(purchase, 2)
        with self.assertRaises(RuleError):
            self.receive(purchase, 1)

    def test_receipt_requires_explicit_physical_confirmation(self):
        purchase = self.purchase()
        with self.assertRaises(RuleError):
            self.post("receipt", {"purchase_id": purchase["id"], "confirmed": False,
                "lines": [{"purchase_line_id": purchase["lines"][0]["id"], "accepted": 10}]})
        self.assertEqual(self.balance()["available"], 0)

    def test_unknown_unit_no_write(self):
        with self.assertRaises(RuleError):
            self.purchase(lines=[{"product_id": self.product, "quantity": 2, "unit": "carton"}])
        self.assertEqual(self.ledger.state()["transactions"], [])

    def test_confirmed_pair_to_piece_conversion(self):
        self.product = self.create_product(sku="TEST-BULB", unit="piece", conversions={"pair": 2})
        purchase = self.purchase(lines=[{"product_id": self.product, "quantity": 5, "unit": "pair", "cost_paise": 20000}])
        self.assertEqual(purchase["lines"][0]["quantity"], 10)
        self.assertEqual(purchase["lines"][0]["snapshot"]["ordered_unit"], "pair")
        self.receive(purchase, 10)
        self.assertEqual(self.balance()["available"], 10)

    def test_goods_and_service_sale_and_credit(self):
        service = self.create_product(sku="TEST-FIT", kind="service", unit="service")
        self.receive(self.purchase(), 2)
        sale = self.sale(payment="credit", lines=[
            {"product_id": self.product, "quantity": 1, "price_paise": 10001},
            {"product_id": service, "quantity": 1, "price_paise": 30000}])
        self.assertEqual(sale["total_paise"], 40001)
        self.assertEqual(sale["data"]["payment_status"], "unpaid")
        self.assertEqual(len(sale["movements"]), 1)
        self.assertEqual(self.balance()["available"], 1)

    def test_service_only_has_no_movement(self):
        service = self.create_product(sku="TEST-FIT", kind="service", unit="service")
        sale = self.sale(lines=[{"product_id": service, "quantity": 1, "price_paise": 1}])
        self.assertEqual(sale["movements"], [])

    def test_replayed_receipt_sale_and_return_are_once(self):
        purchase = self.purchase()
        receipt = self.receive(purchase, 10, key="retry-receipt")
        self.assertEqual(receipt, self.receive(purchase, 10, key="retry-receipt"))
        sale = self.sale(2, key="retry-sale")
        self.assertEqual(sale, self.sale(2, key="retry-sale"))
        payload = {"sale_id": sale["id"], "reason": "Synthetic return", "lines": [
            {"sale_line_id": sale["lines"][0]["id"], "quantity": 1, "damaged": 0}]}
        returned = self.post("return", payload, "retry-return")
        self.assertEqual(returned, self.post("return", payload, "retry-return"))
        self.assertEqual(self.balance()["available"], 9)
        self.assertEqual(len(self.ledger.state()["movements"]), 3)

    def test_same_key_different_payload_rejected(self):
        self.receive(self.purchase(), 5)
        self.sale(1, key="same-key")
        with self.assertRaises(RuleError):
            self.sale(2, key="same-key")
        self.assertEqual(self.balance()["available"], 4)

    def test_concurrent_final_item_sale(self):
        self.receive(self.purchase(quantity=1), 1)
        barrier = threading.Barrier(2)
        payload = {"payment": "cash", "lines": [{"product_id": self.product, "quantity": 1, "price_paise": 1}]}
        def attempt(index):
            barrier.wait()
            try:
                return self.ledger.post("sale", payload, f"concurrent-{index}", f"partner-{index}")["id"]
            except RuleError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [1, 2]))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(self.balance()["available"], 0)
        self.assertEqual(len([t for t in self.ledger.state()["transactions"] if t["kind"] == "sale"]), 1)

    def test_duplicate_rows_cannot_oversell_and_transaction_rolls_back(self):
        self.receive(self.purchase(quantity=1), 1)
        with self.assertRaises(RuleError):
            self.sale(lines=[{"product_id": self.product, "quantity": 1, "price_paise": 1}]*2)
        self.assertEqual(self.balance()["available"], 1)
        self.assertEqual(len(self.ledger.state()["movements"]), 1)

    def test_damaged_return_and_cumulative_limit(self):
        self.receive(self.purchase(), 10)
        sale = self.sale(2)
        payload = {"sale_id": sale["id"], "reason": "Damaged", "lines": [
            {"sale_line_id": sale["lines"][0]["id"], "quantity": 1, "damaged": 1}]}
        self.post("return", payload)
        self.assertEqual((self.balance()["available"], self.balance()["damaged"]), (8, 1))
        self.post("return", payload)
        with self.assertRaises(RuleError):
            self.post("return", payload)

    def test_wrong_source_line_no_effect(self):
        purchase = self.purchase()
        another = self.purchase(invoice_number="A-002")
        with self.assertRaises(RuleError):
            self.post("receipt", {"purchase_id": another["id"], "confirmed": True, "lines": [
                {"purchase_line_id": purchase["lines"][0]["id"], "accepted": 1}]})
        self.assertEqual(self.balance()["available"], 0)

    def test_no_model_needed_and_backup_restore_reconciles(self):
        self.receive(self.purchase(), 10)
        self.sale(3)
        backup = self.ledger.backup(Path(self.temp.name) / "backup.sqlite3")
        restored = Ledger(backup)
        self.assertEqual(restored.state(), self.ledger.state())
        snapshot = restored.state()
        for p in snapshot["products"]:
            self.assertEqual(p["available"], sum(m["available_delta"] for m in snapshot["movements"] if m["product_id"] == p["id"]))
        with self.assertRaises(RuleError):
            self.ledger.backup(backup)

    def test_movement_and_source_immutable(self):
        self.receive(self.purchase(), 1)
        with self.ledger.connection(write=True) as conn:
            for sql in ["UPDATE movements SET available_delta=100", "DELETE FROM movements",
                        "UPDATE transactions SET actor='changed'", "DELETE FROM lines"]:
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql)

    def test_fractional_and_boolean_quantity_rejected(self):
        for qty in [1.5, True, -1, 0]:
            with self.assertRaises(RuleError):
                self.purchase(quantity=qty)
        self.assertEqual(self.ledger.state()["transactions"], [])


if __name__ == "__main__":
    unittest.main()

