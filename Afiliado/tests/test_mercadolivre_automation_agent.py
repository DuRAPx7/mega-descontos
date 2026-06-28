import unittest
from unittest.mock import patch

from bot import mercadolivre_automation_agent as agent


class MercadoLivreAutomationAgentTests(unittest.TestCase):
    def test_processes_candidates_and_marks_completed_ids(self):
        config = {
            "siteUrl": "https://example.test",
            "adminUsername": "admin",
            "adminPassword": "secret",
            "batchSize": 20,
        }
        calls = []

        def fake_api_request(_opener, method, url, payload=None):
            calls.append((method, url, payload))
            if url.endswith("/api/automation-agent/work"):
                return {
                    "job": {"id": "job-1", "state": "processing"},
                    "candidates": [
                        {
                            "id": "candidate-1",
                            "store": "Mercado Livre",
                            "productUrl": "https://www.mercadolivre.com.br/produto/p/MLB1",
                        }
                    ]
                }
            return {"ok": True}

        with (
            patch.object(agent, "authenticated_opener", return_value=object()),
            patch.object(agent, "api_request", side_effect=fake_api_request),
            patch.object(agent, "ensure_browser"),
            patch.object(agent, "generate_affiliate_links", return_value=["https://meli.la/abc"]),
            patch.object(agent, "publish_to_site", return_value=["publicado"]),
            patch.object(agent, "write_csv"),
        ):
            processed, failed = agent.process_candidates(config)

        self.assertEqual((processed, failed), (1, 0))
        completed = next(payload for method, url, payload in calls if url.endswith("/api/automation-agent/job/complete"))
        self.assertEqual(completed["jobId"], "job-1")
        self.assertEqual(completed["ids"], ["candidate-1"])


if __name__ == "__main__":
    unittest.main()
