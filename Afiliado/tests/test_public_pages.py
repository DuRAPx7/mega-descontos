import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"


class PublicPagesTests(unittest.TestCase):
    def test_product_page_has_detail_script(self):
        page = (FRONTEND_DIR / "produto.html").read_text(encoding="utf-8")
        script = (FRONTEND_DIR / "produto.js").read_text(encoding="utf-8")
        self.assertIn('id="productDetail"', page)
        self.assertIn("produto.js", page)
        self.assertIn('id="productSearch"', page)
        self.assertIn('id="productSave"', page)
        self.assertIn("product-extra-grid", script)
        self.assertIn("offerCountdown", script)
        self.assertIn("days > 30", script)
        self.assertIn("Validade informada", script)
        self.assertIn("navigator.share", script)

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
            "admin-analytics.html": "Analytics",
            "admin-offers.html": "Ofertas publicadas",
            "admin-settings.html": "Configuracoes do bot",
        }
        for filename, heading in expected.items():
            page = (FRONTEND_DIR / filename).read_text(encoding="utf-8")
            self.assertIn(heading, page)
            self.assertIn("admin-dashboard.js", page)

    def test_settings_has_one_offer_target_for_every_store(self):
        page = (FRONTEND_DIR / "admin-settings.html").read_text(encoding="utf-8")
        script = (FRONTEND_DIR / "admin-dashboard.js").read_text(encoding="utf-8")
        self.assertIn('id="offersPerStore"', page)
        self.assertIn('value="50" readonly', page)
        self.assertIn("offersPerStore:", script)
        self.assertIn("/api/automation-sequence/status", script)
        self.assertIn("approved: published", script)
        self.assertNotIn("Promise.all(waits)", script)

    def test_admin_status_has_store_dashboard(self):
        page = (FRONTEND_DIR / "admin.html").read_text(encoding="utf-8")
        styles = (FRONTEND_DIR / "admin.css").read_text(encoding="utf-8")
        script = (FRONTEND_DIR / "admin-dashboard.js").read_text(encoding="utf-8")
        for element_id in (
            "mlApproved",
            "shopeeApproved",
            "amazonApproved",
            "magaluApproved",
            "automationAgentState",
            "magaluAgentState",
            "dashboardTotalOffers",
        ):
            self.assertIn(f'id="{element_id}"', page)
        self.assertIn(".store-status-grid", styles)
        self.assertIn("summarizeStore", script)
        self.assertNotIn('id="botStatusList"', page)
        self.assertNotIn('id="botStatusSummary"', page)

    def test_bot_shortcut_starts_site_and_opens_work_files(self):
        shortcut = (ROOT_DIR / "atalhos" / "rodar_bot.bat").read_text(encoding="utf-8")
        self.assertIn("run_bot_once", shortcut)
        self.assertIn("/admin.html", shortcut)
        self.assertIn("produtos_monitorados.json", shortcut)
        self.assertIn("status.json", shortcut)

    def test_analytics_tracks_real_public_events(self):
        analytics_page = (FRONTEND_DIR / "admin-analytics.html").read_text(encoding="utf-8")
        home_script = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
        product_script = (FRONTEND_DIR / "produto.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-page="analytics"', analytics_page)
        self.assertIn('id="analyticsTimeline"', analytics_page)
        self.assertIn("/api/analytics/events", home_script)
        self.assertIn('"outbound_click"', product_script)

    def test_complete_automation_installer_configures_all_agents(self):
        installer = (ROOT_DIR / "atalhos" / "instalar_automacao_completa.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("iniciar_agente_mercado_livre.bat", installer)
        self.assertIn("iniciar_agente_amazon.bat", installer)
        self.assertIn("iniciar_agente_magalu.bat", installer)
        self.assertIn("MegaDescontosMercadoLivre.cmd", installer)
        self.assertIn("MegaDescontosAmazon.cmd", installer)
        self.assertIn("MegaDescontosMagalu.cmd", installer)
        self.assertIn("%USERPROFILE%\\.cache\\codex-runtimes", installer)
        self.assertNotIn("where py", installer)

    def test_agents_load_bundled_windows_runtime_dlls(self):
        for filename in ("mercadolivre_automation_agent.py", "amazon_automation_agent.py", "magalu_automation_agent.py"):
            agent = (ROOT_DIR / "bot" / filename).read_text(encoding="utf-8")
            self.assertIn("os.add_dll_directory", agent)
            self.assertIn("libheif/bin", agent)
