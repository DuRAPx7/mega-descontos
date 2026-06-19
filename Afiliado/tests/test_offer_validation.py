import unittest

from offer_validation import partition_valid_offers, validate_offer


def valid_offer() -> dict:
    return {
        "id": 1,
        "title": "Fone Bluetooth",
        "store": "Amazon",
        "category": "Eletronicos",
        "oldPrice": 299.9,
        "currentPrice": 199.9,
        "image": "https://m.media-amazon.com/images/I/produto.jpg",
        "affiliateUrl": "https://www.amazon.com.br/dp/B012345678?tag=minhatag-20",
    }


class OfferValidationTests(unittest.TestCase):
    def test_accepts_real_product_offer(self) -> None:
        self.assertEqual(validate_offer(valid_offer()), [])

    def test_rejects_placeholder_affiliate_link(self) -> None:
        offer = valid_offer()
        offer["affiliateUrl"] = "https://www.amazon.com.br/dp/EXEMPLO-FONE?tag=SEU-CODIGO-AQUI"
        self.assertTrue(any("exemplo" in error for error in validate_offer(offer)))

    def test_rejects_store_homepage(self) -> None:
        offer = valid_offer()
        offer["affiliateUrl"] = "https://www.amazon.com.br/"
        self.assertTrue(any("pagina inicial" in error for error in validate_offer(offer)))

    def test_rejects_stock_image(self) -> None:
        offer = valid_offer()
        offer["image"] = "https://images.unsplash.com/photo-123"
        self.assertTrue(any("foto generica" in error for error in validate_offer(offer)))

    def test_partitions_valid_and_invalid_offers(self) -> None:
        invalid = valid_offer()
        invalid["id"] = 2
        invalid["currentPrice"] = 399.9
        valid, rejected = partition_valid_offers([valid_offer(), invalid])
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(rejected), 1)


if __name__ == "__main__":
    unittest.main()
