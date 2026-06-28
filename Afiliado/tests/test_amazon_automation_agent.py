import unittest
from unittest.mock import patch

from bot import amazon_automation_agent as agent


class AmazonAutomationAgentTests(unittest.TestCase):
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
                return {"job": {"id": "amazon-job-1", "state": "processing"}}
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
        completed = next(payload for method, url, payload in calls if url.endswith("/job/complete"))
        self.assertEqual(completed["jobId"], "amazon-job-1")


if __name__ == "__main__":
    unittest.main()
