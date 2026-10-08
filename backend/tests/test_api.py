import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from app.legacy_main import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = self.enterContext(TestClient(create_app(Path(self.temp.name) / "test.sqlite3", "demo")))

    def test_http_post_readback_replay_and_strict_validation(self):
        headers = {"Idempotency-Key": "api-product"}
        product = {"sku": "SYNTHETIC", "name": "Synthetic mat", "category": "Mats", "unit": "set", "kind": "goods"}
        first = self.client.post("/api/products", json=product, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), self.client.post("/api/products", json=product, headers=headers).json())
        bad = self.client.post("/api/sales", headers={"Idempotency-Key":"bad-sale"}, json={"lines":[
            {"product_id":first.json()["id"],"quantity":True,"price_paise":1}]})
        self.assertEqual(bad.status_code, 422)
        state = self.client.get("/api/state").json()
        self.assertEqual(state["products"][0]["available"], 0)
        self.assertFalse(state["tax_invoicing_enabled"])
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertTrue(self.client.get("/").headers["content-type"].startswith("text/html"))

    def test_cross_origin_write_rejected(self):
        response = self.client.post("/api/products", json={}, headers={"Origin":"https://unknown.example"})
        self.assertEqual(response.status_code, 403)

    def test_http_purchase_receipt_sale_readback(self):
        def post(path, body, key):
            response = self.client.post(path,json=body,headers={"Idempotency-Key":key})
            self.assertEqual(response.status_code,200,response.text)
            return response.json()
        product = post("/api/products",{"sku":"DEMO","name":"Demo","category":"Demo","unit":"piece","kind":"goods"},"p")
        purchase = post("/api/purchases",{"supplier":"Synthetic","invoice_number":"DEMO-1","invoice_date":"2026-10-04","lines":[
            {"product_id":product["id"],"quantity":10,"unit":"piece"}]},"b")
        receipt = {"purchase_id":purchase["id"],"confirmed":True,"lines":[{"purchase_line_id":purchase["lines"][0]["id"],"accepted":8,"damaged":1}]}
        post("/api/receipts",receipt,"r")
        post("/api/receipts",receipt,"r")
        sale = post("/api/sales",{"payment":"upi","lines":[{"product_id":product["id"],"quantity":3,"price_paise":10001}]},"s")
        self.assertEqual(self.client.get(f"/api/transactions/{sale['id']}").json(),sale)
        state = self.client.get("/api/state").json()
        self.assertEqual((state["products"][0]["available"],state["products"][0]["damaged"],state["products"][0]["incoming"]),(5,1,1))


if __name__ == "__main__":
    unittest.main()
