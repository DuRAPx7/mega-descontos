import unittest
from unittest.mock import patch

import server


class ServerSettingsTests(unittest.TestCase):
    def test_normalizes_bot_settings(self):
        settings = server.normalize_bot_settings(
            {
                "minimumDiscount": 20,
                "minimumRating": 4.5,
                "minimumSales": 30,
                "minimumCommissionRate": 0.08,
                "maxPages": 3,
            }
        )

        self.assertEqual(settings["minimumDiscount"], 20)
        self.assertEqual(settings["minimumRating"], 4.5)
        self.assertEqual(settings["minimumSales"], 30)
        self.assertEqual(settings["minimumCommissionRate"], 0.08)
        self.assertEqual(settings["maxPages"], 3)

    def test_clamps_bot_settings(self):
        settings = server.normalize_bot_settings(
            {
                "minimumDiscount": 200,
                "minimumRating": 9,
                "minimumSales": -1,
                "minimumCommissionRate": 5,
                "maxPages": 50,
            }
        )

        self.assertEqual(settings["minimumDiscount"], 90)
        self.assertEqual(settings["minimumRating"], 5)
        self.assertEqual(settings["minimumSales"], 0)
        self.assertEqual(settings["minimumCommissionRate"], 1)
        self.assertEqual(settings["maxPages"], 10)

    def test_cleanup_removes_stale_api_offer(self):
        active = {
            "id": "active",
            "title": "Produto ativo",
            "store": "Shopee",
            "category": "Ofertas",
            "oldPrice": 100,
            "currentPrice": 80,
            "image": "https://cf.shopee.com.br/file/active.jpg",
            "affiliateUrl": "https://s.shopee.com.br/active",
            "source": "shopee_open_api",
        }
        stale = {**active, "id": "stale", "affiliateUrl": "https://s.shopee.com.br/stale"}
        written = []

        with (
            patch.object(server, "read_offers", return_value=[active, stale]),
            patch.object(server, "write_offers", side_effect=lambda offers: written.extend(offers)),
            patch.object(server, "read_review_offers", return_value=[]),
            patch.object(server, "write_review_offers"),
        ):
            result = server.cleanup_catalog({"shopee_open_api": {"active"}})

        self.assertEqual(result["publishedRemoved"], 1)
        self.assertEqual([offer["id"] for offer in written], ["active"])
