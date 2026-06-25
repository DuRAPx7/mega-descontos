import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class PublicPagesTests(unittest.TestCase):
    def test_product_page_has_detail_script(self):
        page = (ROOT_DIR / "produto.html").read_text(encoding="utf-8")
        self.assertIn('id="productDetail"', page)
        self.assertIn("produto.js", page)

    def test_admin_is_split_into_four_pages(self):
        expected = {
            "admin.html": "Status das lojas",
            "admin-review.html": "Fila de revisao",
            "admin-offers.html": "Ofertas publicadas",
            "admin-settings.html": "Configuracoes do bot",
        }
        for filename, heading in expected.items():
            page = (ROOT_DIR / filename).read_text(encoding="utf-8")
            self.assertIn(heading, page)
            self.assertIn("admin-dashboard.js", page)
