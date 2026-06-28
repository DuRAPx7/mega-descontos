import unittest
from unittest.mock import patch

from backend import server


class ServerSettingsTests(unittest.TestCase):
    def test_normalizes_bot_settings(self):
        settings = server.normalize_bot_settings(
            {
                "minimumDiscount": 20,
                "minimumRating": 4.5,
                "minimumSales": 30,
                "minimumCommissionRate": 0.08,
                "maxPages": 3,
                "mercadoLivreMaxPages": 8,
                "autoPublishShopee": True,
                "autoPublishMercadoLivre": True,
            }
        )

        self.assertEqual(settings["minimumDiscount"], 20)
        self.assertEqual(settings["minimumRating"], 4.5)
        self.assertEqual(settings["minimumSales"], 30)
        self.assertEqual(settings["minimumCommissionRate"], 0.08)
        self.assertEqual(settings["maxPages"], 3)
        self.assertEqual(settings["mercadoLivreMaxPages"], 8)
        self.assertTrue(settings["autoPublishShopee"])
        self.assertTrue(settings["autoPublishMercadoLivre"])

    def test_clamps_bot_settings(self):
        settings = server.normalize_bot_settings(
            {
                "minimumDiscount": 200,
                "minimumRating": 9,
                "minimumSales": -1,
                "minimumCommissionRate": 5,
                "maxPages": 50,
                "mercadoLivreMaxPages": 100,
                "autoPublishShopee": "false",
                "autoPublishMercadoLivre": "false",
            }
        )

        self.assertEqual(settings["minimumDiscount"], 90)
        self.assertEqual(settings["minimumRating"], 5)
        self.assertEqual(settings["minimumSales"], 0)
        self.assertEqual(settings["minimumCommissionRate"], 1)
        self.assertEqual(settings["maxPages"], 50)
        self.assertEqual(settings["mercadoLivreMaxPages"], 20)
        self.assertFalse(settings["autoPublishShopee"])
        self.assertFalse(settings["autoPublishMercadoLivre"])

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

    def test_cleanup_preserves_local_agent_offer_when_source_is_not_a_snapshot(self):
        offer = {
            "id": "meli-1",
            "title": "Produto Mercado Livre",
            "store": "Mercado Livre",
            "category": "Ofertas",
            "oldPrice": 100,
            "currentPrice": 80,
            "image": "https://http2.mlstatic.com/produto.jpg",
            "affiliateUrl": "https://meli.la/affiliate",
            "source": "mercadolivre_affiliate_link",
        }
        written = []
        with (
            patch.object(server, "read_offers", return_value=[offer]),
            patch.object(server, "write_offers", side_effect=lambda offers: written.extend(offers)),
            patch.object(server, "read_review_offers", return_value=[]),
            patch.object(server, "write_review_offers"),
        ):
            result = server.cleanup_catalog({"mercadolivre_affiliate_link": set()})

        self.assertEqual(result["publishedRemoved"], 0)
        self.assertEqual(written, [])

    def test_automatic_publish_updates_by_id_and_clears_review(self):
        current = {
            "id": "shopee-10-20",
            "title": "Produto antigo",
            "store": "Shopee",
            "category": "Ofertas",
            "oldPrice": 120,
            "currentPrice": 100,
            "image": "https://cf.shopee.com.br/file/old.jpg",
            "affiliateUrl": "https://s.shopee.com.br/old",
            "source": "shopee_open_api",
        }
        updated = {
            **current,
            "title": "Produto atualizado",
            "currentPrice": 80,
            "image": "https://cf.shopee.com.br/file/new.jpg",
            "affiliateUrl": "https://s.shopee.com.br/new",
        }
        written_offers = []
        written_review = []

        with (
            patch.object(server, "read_offers", return_value=[current]),
            patch.object(server, "write_offers", side_effect=lambda offers: written_offers.extend(offers)),
            patch.object(server, "read_review_offers", return_value=[current]),
            patch.object(server, "write_review_offers", side_effect=lambda offers: written_review.extend(offers)),
        ):
            total = server.publish_automatic_offers([updated])

        self.assertEqual(total, 1)
        self.assertEqual(len(written_offers), 1)
        self.assertEqual(written_offers[0]["title"], "Produto atualizado")
        self.assertEqual(written_review, [])

    def test_completes_only_selected_deal_candidates(self):
        candidates = [
            {"id": "one", "candidateType": "", "store": "Mercado Livre"},
            {"id": "two", "candidateType": "", "store": "Mercado Livre"},
        ]
        written = []
        with (
            patch.object(server, "read_deal_candidates", return_value=candidates),
            patch.object(server, "write_candidates", side_effect=lambda values: written.extend(values)),
        ):
            removed = server.complete_deal_candidates(["one"])

        self.assertEqual(removed, 1)
        self.assertEqual([candidate["id"] for candidate in written], ["two"])

    def test_claims_manual_automation_job_only_once(self):
        job = {"id": "job-1", "state": "pending", "candidateIds": ["one"]}
        candidates = [{"id": "one", "store": "Mercado Livre", "productUrl": "https://produto"}]
        saved = []
        with (
            patch.object(server.offer_storage, "get_integration", return_value=job),
            patch.object(server.offer_storage, "set_integration", side_effect=lambda _provider, payload: saved.append(payload)),
            patch.object(server, "read_deal_candidates", return_value=candidates),
        ):
            claimed, work = server.claim_automation_job()

        self.assertEqual(claimed["state"], "processing")
        self.assertEqual(work, candidates)
        self.assertEqual(saved[-1]["state"], "processing")
