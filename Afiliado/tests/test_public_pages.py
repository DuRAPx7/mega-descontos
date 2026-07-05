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

    def test_home_has_discount_request_flow(self):
        page = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        script = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="discountRequestForm"', page)
        self.assertIn('id="discountRequestFeedback"', page)
        self.assertIn('"/api/discount-requests"', script)

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

    def test_admin_status_has_store_dashboard(self):
        page = (FRONTEND_DIR / "admin.html").read_text(encoding="utf-8")
        styles = (FRONTEND_DIR / "admin.css").read_text(encoding="utf-8")
        script = (FRONTEND_DIR / "admin-dashboard.js").read_text(encoding="utf-8")
        for element_id in (
            "mlApproved",
            "shopeeApproved",
            "amazonApproved",
            "automationAgentState",
            "dashboardTotalOffers",
        ):
            self.assertIn(f'id="{element_id}"', page)
        self.assertIn(".store-status-grid", styles)
        self.assertIn("summarizeStore", script)

    def test_bot_shortcut_starts_site_and_opens_work_files(self):
        shortcut = (ROOT_DIR / "atalhos" / "rodar_bot.bat").read_text(encoding="utf-8")
        self.assertIn("run_bot_once", shortcut)
        self.assertIn("/admin-review.html", shortcut)
        self.assertIn("produtos_monitorados.json", shortcut)
        self.assertIn("status.json", shortcut)

    def test_complete_automation_installer_configures_both_agents(self):
        installer = (ROOT_DIR / "atalhos" / "instalar_automacao_completa.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("iniciar_agente_mercado_livre.bat", installer)
        self.assertIn("iniciar_agente_amazon.bat", installer)
        self.assertIn("MegaDescontosMercadoLivre.cmd", installer)
        self.assertIn("MegaDescontosAmazon.cmd", installer)
        self.assertIn("%USERPROFILE%\\.cache\\codex-runtimes", installer)
        self.assertNotIn("where py", installer)

    def test_agents_load_bundled_windows_runtime_dlls(self):
        for filename in ("mercadolivre_automation_agent.py", "amazon_automation_agent.py"):
            agent = (ROOT_DIR / "bot" / filename).read_text(encoding="utf-8")
            self.assertIn("os.add_dll_directory", agent)
            self.assertIn("libheif/bin", agent)
