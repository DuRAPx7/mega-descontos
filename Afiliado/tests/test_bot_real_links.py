import unittest

from bot.discount_bot import (
    normalize_product,
    parse_feed_payload,
    parse_mercadolivre_affiliate_page,
    parse_mercadolivre_deals_page,
    parse_price,
)


def product() -> dict:
    return {
        "id": "produto-123",
        "title": "Fone Bluetooth",
        "store": "Mercado Livre",
        "category": "Eletronicos",
        "url": "https://www.mercadolivre.com.br/fone-bluetooth/p/MLB123",
        "oldPrice": 299.9,
        "currentPrice": 199.9,
        "image": "https://http2.mlstatic.com/D_NQ_NP_produto.webp",
    }


class BotRealLinksTests(unittest.TestCase):
    def test_parses_xml_affiliate_feed(self) -> None:
        payload = b"""<?xml version="1.0" encoding="UTF-8"?>
        <yml_catalog><shop><offers><offer id="42">
          <name>Produto XML</name><url>https://afiliado.example/produto-42</url>
          <oldprice>199.90</oldprice><price>129.90</price>
          <picture>https://cdn.example/produto-42.jpg</picture>
        </offer></offers></shop></yml_catalog>"""
        items, feed_format = parse_feed_payload(payload, {"format": "auto", "itemTag": "offer"}, "application/xml")
        self.assertEqual(feed_format, "xml")
        self.assertEqual(items[0]["@id"], "42")
        self.assertEqual(items[0]["price"], "129.90")

    def test_parses_csv_affiliate_feed(self) -> None:
        payload = "id;name;price;oldprice\n1;Produto CSV;79,90;119,90\n".encode("utf-8")
        items, feed_format = parse_feed_payload(payload, {"format": "csv"})
        self.assertEqual(feed_format, "csv")
        self.assertEqual(items[0]["name"], "Produto CSV")

    def test_parses_json_affiliate_feed(self) -> None:
        payload = b'{"items":[{"id":3,"name":"Produto JSON"}]}'
        items, feed_format = parse_feed_payload(payload, {"format": "auto"}, "application/json")
        self.assertEqual(feed_format, "json")
        self.assertEqual(items[0]["id"], 3)

    def test_parses_brazilian_price(self) -> None:
        self.assertEqual(parse_price("R$ 1.299,90"), 1299.9)

    def test_parses_mercadolivre_affiliate_page(self) -> None:
        page = """
        <meta property="og:title" content="Moletom Canguru Liso Unissex">
        <meta property="og:image" content="https://http2.mlstatic.com/produto.webp">
        Moletom Canguru Liso Unissex
        {"previous_price":{"value":99.9,"currency":"BRL"},
        "current_price":{"value":64.9,"currency":"BRL"}}
        """
        source = {
            "id": "meli-1AU379s",
            "affiliateUrl": "https://meli.la/1AU379s",
            "category": "Moda",
        }
        parsed = parse_mercadolivre_affiliate_page(page, source)
        self.assertEqual(parsed["oldPrice"], 99.9)
        self.assertEqual(parsed["currentPrice"], 64.9)
        self.assertEqual(parsed["affiliateUrl"], source["affiliateUrl"])

    def test_parses_mercadolivre_public_deals(self) -> None:
        page = """
        <div class="andes-card poly-card poly-card--grid-card">
          <img class="poly-component__picture" src="https://http2.mlstatic.com/produto.webp" alt="Fone Bluetooth JBL">
          <a class="poly-component__title" href="https://www.mercadolivre.com.br/fone/p/MLB123">Fone Bluetooth JBL</a>
          <s class="andes-money-amount andes-money-amount--previous" aria-label="Antes: 299 reais com 90 centavos"></s>
          <span class="andes-money-amount" aria-label="Agora: 179 reais com 90 centavos"></span>
        </div>
        """
        deals = parse_mercadolivre_deals_page(page)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0]["id"], "MLB123")
        self.assertEqual(deals[0]["oldPrice"], 299.9)
        self.assertEqual(deals[0]["currentPrice"], 179.9)

    def test_accepts_affiliate_url_generated_by_platform(self) -> None:
        item = product()
        item["affiliateUrl"] = "https://www.mercadolivre.com.br/social/afiliado/produto-123"
        offer = normalize_product(item, minimum_discount=15)
        self.assertIsNotNone(offer)
        self.assertEqual(offer["affiliateUrl"], item["affiliateUrl"])

    def test_rejects_product_without_supported_affiliate_link(self) -> None:
        self.assertIsNone(normalize_product(product(), minimum_discount=15))

    def test_rejects_placeholder_link(self) -> None:
        item = product()
        item["affiliateUrl"] = "https://loja.com/produto-exemplo?ref=SEU-CODIGO"
        self.assertIsNone(normalize_product(item, minimum_discount=15))


if __name__ == "__main__":
    unittest.main()

