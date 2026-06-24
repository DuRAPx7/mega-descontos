import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from bot import shopee_api_client


class ShopeeApiClientTests(unittest.TestCase):
    def test_signature_uses_exact_payload_bytes(self):
        payload = b'{"query":"query { test }"}'
        timestamp = 1577836800
        expected = hashlib.sha256(b"1234561577836800" + payload + b"demo").hexdigest()

        authorization = shopee_api_client._authorization("123456", "demo", timestamp, payload)

        self.assertEqual(
            authorization,
            f"SHA256 Credential=123456, Timestamp=1577836800, Signature={expected}",
        )

    def test_payload_is_valid_compact_json(self):
        payload = shopee_api_client._payload(2, 100)
        decoded = json.loads(payload.decode("utf-8"))

        self.assertEqual(decoded["operationName"], "ProductOffers")
        self.assertEqual(decoded["variables"], {"page": 2, "limit": 100})
        self.assertIn(b'"variables":{"page":2,"limit":100}', payload)

    def test_normalizes_discounted_product(self):
        product = shopee_api_client.normalize_product(
            {
                "itemId": 20,
                "shopId": 10,
                "productName": "Fone Bluetooth",
                "priceMin": "80",
                "priceDiscountRate": 20,
                "imageUrl": "https://cf.shopee.com.br/file/product.jpg",
                "productLink": "https://shopee.com.br/product/10/20",
                "offerLink": "https://s.shopee.com.br/affiliate",
                "periodEndTime": 4102444800,
            }
        )

        self.assertIsNotNone(product)
        self.assertEqual(product["id"], "shopee-10-20")
        self.assertEqual(product["category"], "Eletronicos")
        self.assertEqual(product["oldPrice"], 100.0)
        self.assertEqual(product["currentPrice"], 80.0)
        self.assertEqual(product["affiliateUrl"], "https://s.shopee.com.br/affiliate")
