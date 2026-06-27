import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"


class PublicPagesTests(unittest.TestCase):
    def test_product_page_has_detail_script(self):
        page = (FRONTEND_DIR / "produto.html").read_text(encoding="utf-8")
        self.assertIn('id="productDetail"', page)
        self.assertIn("produto.js", page)

    def test_home_has_offer_pagination(self):
        page = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        script = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
        styles = (FRONTEND_DIR / "styles.css").read_text(encoding="utf-8")
        self.assertIn('id="offerPagination"', page)
        self.assertIn("const OFFERS_PER_PAGE = 25", script)
        self.assertIn("repeat(5, minmax(0, 1fr))", styles)

    def test_admin_is_split_into_four_pages(self):
        expected = {
            "admin.html": "Status das lojas",
            "admin-review.html": "Fila de revisao",
            "admin-offers.html": "Ofertas publicadas",
            "admin-settings.html": "Configuracoes do bot",
        }
        for filename, heading in expected.items():
            page = (FRONTEND_DIR / filename).read_text(encoding="utf-8")
            self.assertIn(heading, page)
            self.assertIn("admin-dashboard.js", page)
