import unittest
from unittest.mock import patch

from bot import amazon_automation_agent as agent
from bot.amazon_discovery_bot import extract_amazon_prices


class AmazonAutomationAgentTests(unittest.TestCase):
    def test_ignores_unit_price_when_reading_amazon_offer(self):
        current, old = extract_amazon_prices(
            "-19% R$ 19,90 (R$ 0,04 / milimetro) De: R$ 24,79",
            19,
        )
        self.assertEqual(current, 19.90)
        self.assertEqual(old, 24.79)

    def test_ignores_installment_when_reading_amazon_offer(self):
        current, old = extract_amazon_prices(
            "R$ 1.999,00 10x de R$ 199,90 De: R$ 2.499,00",
            20,
        )
        self.assertEqual(current, 1999.00)
        self.assertEqual(old, 2499.00)

    def test_rejects_unit_price_outlier_when_only_old_price_remains(self):
        current, old = extract_amazon_prices(
            "Heinz Ketchup Tradicional 1,033KG R$ 0,02 De: R$ 7,99",
            100,
        )
        self.assertIsNone(current)
        self.assertIsNone(old)

    def test_processes_single_manual_job(self):
        config = {
            "siteUrl": "https://example.test",
            "adminUsername": "admin",
            "adminPassword": "secret",
            "associateTag": "minhatag-20",
            "limit": 10,
            "scrolls": 2,
        }
        offer = {
            "sourceProductId": "B012345678",
            "productUrl": "https://www.amazon.com.br/dp/B012345678",
            "affiliateUrl": "https://www.amazon.com.br/dp/B012345678?tag=minhatag-20",
            "title": "Produto Amazon",
            "store": "Amazon",
            "category": "Ofertas",
            "oldPrice": 100,
            "currentPrice": 80,
            "image": "https://m.media-amazon.com/images/I/produto.jpg",
        }
        calls = []

        def fake_api_request(_opener, method, url, payload=None):
            calls.append((method, url, payload))
            if url.endswith("/api/amazon-automation-agent/work"):
                return {"job": {"id": "amazon-job-1", "state": "processing", "target": 7}}
            return {"ok": True}

        with (
            patch.object(agent, "authenticated_opener", return_value=object()),
            patch.object(agent, "api_request", side_effect=fake_api_request),
            patch.object(agent, "ensure_browser"),
            patch.object(agent, "read_source_urls", return_value=["https://www.amazon.com.br/deals"]),
            patch.object(agent, "discover_offers", return_value=[offer]) as discover,
            patch.object(agent, "publish_to_site", return_value=["publicado"]),
            patch.object(agent, "write_csv"),
        ):
            processed, failed = agent.process_job(config)

        self.assertEqual((processed, failed), (1, 0))
        self.assertEqual(discover.call_args.args[2], "minhatag-20")
        self.assertEqual(discover.call_args.args[3], 7)
        completed = next(payload for method, url, payload in calls if url.endswith("/job/complete"))
        self.assertEqual(completed["jobId"], "amazon-job-1")


if __name__ == "__main__":
    unittest.main()
