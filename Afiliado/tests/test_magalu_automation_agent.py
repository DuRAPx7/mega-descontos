import unittest
from unittest.mock import patch

from bot import magalu_automation_agent as agent
from bot.magalu_discovery_bot import collect_offers_from_page, is_influencer_product_url


class FakePage:
    def evaluate(self, _script):
        return [
            {
                "url": "https://www.magazinevoce.com.br/minhaloja/fone-bluetooth/p/abc123/ea/fone/",
                "title": "Fone Bluetooth sem fio com cancelamento de ruido",
                "image": "https://a-static.mlcdn.com.br/produto.jpg",
                "prices": ["R$ 199,90", "R$ 129,90"],
                "discounts": ["35% de desconto"],
            }
        ]


class MagaluAutomationAgentTests(unittest.TestCase):
    def test_accepts_only_product_from_influencer_store(self):
        self.assertTrue(
            is_influencer_product_url(
                "https://www.magazinevoce.com.br/minhaloja/fone/p/abc123/ea/fone/"
            )
        )
        self.assertFalse(
            is_influencer_product_url("https://www.magazineluiza.com.br/fone/p/abc123/")
        )

    def test_collects_discount_with_commissioned_store_link(self):
        offers = collect_offers_from_page(FakePage(), 10)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["store"], "Magalu")
        self.assertEqual(offers[0]["currentPrice"], 129.90)
        self.assertIn("/minhaloja/", offers[0]["affiliateUrl"])

    def test_processes_single_panel_job(self):
        config = {
            "siteUrl": "https://example.test",
            "adminUsername": "admin",
            "adminPassword": "secret",
            "storeUrl": "https://www.magazinevoce.com.br/minhaloja/",
            "limit": 10,
            "scrolls": 2,
        }
        offer = {
            "sourceProductId": "abc123",
            "productUrl": "https://www.magazinevoce.com.br/minhaloja/fone/p/abc123/ea/fone/",
            "affiliateUrl": "https://www.magazinevoce.com.br/minhaloja/fone/p/abc123/ea/fone/",
            "title": "Fone Bluetooth",
            "store": "Magalu",
            "category": "Eletronicos",
            "oldPrice": 200,
            "currentPrice": 130,
            "image": "https://a-static.mlcdn.com.br/produto.jpg",
        }
        calls = []

        def fake_api_request(_opener, method, url, payload=None):
            calls.append((method, url, payload))
            if url.endswith("/api/magalu-automation-agent/work"):
                return {"job": {"id": "magalu-job-1", "state": "processing"}}
            return {"ok": True}

        with (
            patch.object(agent, "authenticated_opener", return_value=object()),
            patch.object(agent, "api_request", side_effect=fake_api_request),
            patch.object(agent, "ensure_browser"),
            patch.object(agent, "discover_offers", return_value=[offer]),
            patch.object(agent, "publish_to_site", return_value=["publicado"]),
            patch.object(agent, "write_csv"),
        ):
            processed, failed = agent.process_job(config)

        self.assertEqual((processed, failed), (1, 0))
        completed = next(payload for _, url, payload in calls if url.endswith("/job/complete"))
        self.assertEqual(completed["jobId"], "magalu-job-1")


if __name__ == "__main__":
    unittest.main()
