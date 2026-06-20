import importlib.util
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from offer_validation import partition_valid_offers
from storage import offer_storage


ROOT_DIR = Path(__file__).resolve().parent
OFFERS_DB = ROOT_DIR / "data" / "offers_db.json"
DEFAULT_OFFERS_JS = ROOT_DIR / "data" / "offers.js"
ADMIN_CONFIG = ROOT_DIR / "config" / "admin.json"
BOT_PATH = ROOT_DIR / "bot" / "discount_bot.py"
BOT_STATUS = ROOT_DIR / "bot" / "status.json"
BOT_INTERVAL_SECONDS = 600
SESSION_COOKIE = "mega_admin_session"
SESSIONS: set[str] = set()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
BOT_RUN_LOCK = threading.Lock()
ML_DEALS_CACHE: dict[str, object] = {"expiresAt": 0.0, "candidates": []}
ML_DEALS_LOCK = threading.Lock()


def load_discount_bot():
    spec = importlib.util.spec_from_file_location("discount_bot", BOT_PATH)
    if not spec or not spec.loader:
        raise RuntimeError("Nao foi possivel carregar o bot.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["discount_bot"] = module
    spec.loader.exec_module(module)
    return module


def extract_default_offers() -> list[dict]:
    content = DEFAULT_OFFERS_JS.read_text(encoding="utf-8")
    marker = "window.DEFAULT_OFFERS = "
    start = content.index(marker) + len(marker)
    end = content.rindex("];") + 1
    return json.loads(content[start:end])


def load_seed_offers() -> list[dict]:
    if OFFERS_DB.exists():
        try:
            data = json.loads(OFFERS_DB.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return extract_default_offers()


def ensure_offers_db() -> None:
    imported = offer_storage.initialize(load_seed_offers())
    if imported:
        print(f"[Mega Descontos] {imported} ofertas migradas para {offer_storage.description}.")


def load_admin_config() -> dict:
    env_username = os.environ.get("ADMIN_USERNAME")
    env_password = os.environ.get("ADMIN_PASSWORD")
    if env_username and env_password:
        return {"username": env_username, "password": env_password}

    if not ADMIN_CONFIG.exists():
        ADMIN_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        ADMIN_CONFIG.write_text(
            json.dumps({"username": "admin", "password": "admin123"}, indent=2),
            encoding="utf-8",
        )
    return json.loads(ADMIN_CONFIG.read_text(encoding="utf-8"))


def read_offers() -> list[dict]:
    ensure_offers_db()
    return offer_storage.read_all()


def write_offers(offers: list[dict]) -> None:
    offer_storage.replace_all(offers)


def read_candidates() -> list[dict]:
    ensure_offers_db()
    return offer_storage.read_candidates()


def write_candidates(candidates: list[dict]) -> None:
    offer_storage.replace_candidates(candidates)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def remove_expired_offers() -> int:
    offers = read_offers()
    now = datetime.now(timezone.utc)
    active_offers = [
        offer for offer in offers
        if not parse_datetime(str(offer.get("expiresAt") or "")) or parse_datetime(str(offer.get("expiresAt") or "")) > now
    ]

    removed = len(offers) - len(active_offers)
    if removed:
        write_offers(active_offers)
    return removed


def remove_invalid_offers() -> int:
    offers = read_offers()
    valid_offers, rejected = partition_valid_offers(offers)
    if rejected:
        write_offers(valid_offers)
        print(f"[Mega Descontos] {len(rejected)} ofertas de exemplo ou invalidas removidas.")
    return len(rejected)


def read_json_body(handler: SimpleHTTPRequestHandler) -> object:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length)
    if not raw_body:
        return None
    return json.loads(raw_body.decode("utf-8"))


def write_json(handler: SimpleHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_bot_status() -> dict:
    if not BOT_STATUS.exists():
        return {"checkedAt": "", "generatedOffers": 0, "totalPublished": 0, "sources": []}
    try:
        return json.loads(BOT_STATUS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"checkedAt": "", "generatedOffers": 0, "totalPublished": 0, "sources": []}


def get_session_token(handler: SimpleHTTPRequestHandler) -> str | None:
    raw_cookie = handler.headers.get("Cookie")
    if not raw_cookie:
        return None
    cookie = cookies.SimpleCookie(raw_cookie)
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def is_authenticated(handler: SimpleHTTPRequestHandler) -> bool:
    token = get_session_token(handler)
    return bool(token and token in SESSIONS)


def set_session_cookie(handler: SimpleHTTPRequestHandler, token: str) -> None:
    secure = "; Secure" if handler.headers.get("X-Forwarded-Proto") == "https" else ""
    handler.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/{secure}")


def clear_session_cookie(handler: SimpleHTTPRequestHandler) -> None:
    handler.send_header("Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")


def run_bot_once() -> None:
    if not BOT_RUN_LOCK.acquire(blocking=False):
        print("[Mega Descontos] Uma execucao do bot ja esta em andamento.")
        return
    try:
        bot = load_discount_bot()
        existing_offers = read_offers()
        offers = bot.generate_offers(
            bot.DEFAULT_INPUT,
            bot.DEFAULT_OUTPUT,
            bot.DEFAULT_DB,
            minimum_discount=15,
            purge_missing=True,
            real_sources_path=bot.DEFAULT_REAL_SOURCES,
            status_path=bot.DEFAULT_STATUS,
            existing_offers=existing_offers,
            persist_db=False,
        )
        merged_offers = bot.merge_offers(existing_offers, offers, purge_missing=True)
        write_offers(merged_offers)
        write_candidates(bot.get_candidates())
        removed = remove_expired_offers()
        print(f"[Mega Descontos] Bot publicou {len(offers)} ofertas. Expiradas removidas: {removed}.")
    except Exception as error:
        print(f"[Mega Descontos] Erro no bot: {error}")
    finally:
        BOT_RUN_LOCK.release()


def start_bot_scheduler() -> None:
    def loop() -> None:
        while True:
            run_bot_once()
            time.sleep(BOT_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


class MegaDescontosHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/offers":
            removed = remove_expired_offers()
            offers = read_offers()
            write_json(self, {"offers": offers, "removedExpired": removed})
            return

        if parsed.path == "/api/auth":
            write_json(self, {"authenticated": is_authenticated(self)})
            return

        if parsed.path == "/healthz":
            write_json(
                self,
                {
                    "ok": True,
                    "storage": offer_storage.backend,
                    "persistent": offer_storage.backend == "postgresql",
                },
            )
            return

        if parsed.path == "/api/bot-status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, read_bot_status())
            return

        if parsed.path == "/api/candidates":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"candidates": read_candidates()})
            return

        if parsed.path == "/api/mercadolivre/deals":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                with ML_DEALS_LOCK:
                    now = time.time()
                    cached = list(ML_DEALS_CACHE.get("candidates") or [])
                    if float(ML_DEALS_CACHE.get("expiresAt") or 0) <= now or not cached:
                        bot = load_discount_bot()
                        products = bot.fetch_mercadolivre_deals(limit=24)
                        cached = [
                            candidate
                            for product in products
                            if (candidate := bot.normalize_candidate(product, minimum_discount=15))
                        ]
                        cached = bot.filter_unpublished_candidates(cached, read_offers())
                        if not cached:
                            raise ValueError("O Mercado Livre nao retornou novas ofertas com desconto agora.")
                        ML_DEALS_CACHE["candidates"] = cached
                        ML_DEALS_CACHE["expiresAt"] = now + 600
                        write_candidates(cached)
                write_json(
                    self,
                    {
                        "candidates": cached,
                        "checkedAt": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as error:
                fallback = read_candidates()
                write_json(self, {"error": str(error), "candidates": fallback}, 502 if not fallback else 200)
            return

        if parsed.path == "/admin.html" and not is_authenticated(self):
            self.send_response(302)
            self.send_header("Location", "/login.html")
            self.end_headers()
            return

        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/login":
            config = load_admin_config()
            payload = read_json_body(self) or {}
            if (
                payload.get("username") == config.get("username")
                and payload.get("password") == config.get("password")
            ):
                token = secrets.token_urlsafe(32)
                SESSIONS.add(token)
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                set_session_cookie(self, token)
                self.end_headers()
                self.wfile.write(body)
                return
            write_json(self, {"error": "Usuario ou senha invalidos."}, 401)
            return

        if parsed.path == "/api/logout":
            token = get_session_token(self)
            if token:
                SESSIONS.discard(token)
            body = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            clear_session_cookie(self)
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/run-bot":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            run_bot_once()
            write_json(self, {"ok": True})
            return

        if parsed.path == "/api/mercadolivre/import-link":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                if not isinstance(payload, dict):
                    raise ValueError("Dados invalidos.")
                affiliate_url = str(payload.get("affiliateUrl") or "").strip()
                category = str(payload.get("category") or "Ofertas").strip()
                bot = load_discount_bot()
                product = bot.fetch_mercadolivre_affiliate_product(affiliate_url, category)
                offer = bot.normalize_product(product, minimum_discount=1)
                if not offer:
                    raise ValueError("O link nao informou uma oferta ativa com preco anterior e atual.")
                offer["source"] = "mercadolivre_affiliate_link"
                write_json(self, {"offer": offer})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        write_json(self, {"error": "Rota nao encontrada."}, 404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/offers":
            write_json(self, {"error": "Rota nao encontrada."}, 404)
            return

        if not is_authenticated(self):
            write_json(self, {"error": "Nao autorizado."}, 401)
            return

        try:
            payload = read_json_body(self)
            if not isinstance(payload, list):
                raise ValueError("Payload deve ser uma lista de ofertas.")

            valid_offers, rejected = partition_valid_offers(payload)
            if rejected:
                first = rejected[0]
                details = "; ".join(first["errors"])
                raise ValueError(f"{first['title']}: {details}")

            write_offers(valid_offers)
            removed = remove_expired_offers()
            write_json(self, {"ok": True, "total": len(read_offers()), "removedExpired": removed})
        except Exception as error:
            write_json(self, {"error": str(error)}, 400)

    def log_message(self, format: str, *args) -> None:
        print(f"[Mega Descontos] {self.address_string()} - {format % args}")


def run() -> None:
    ensure_offers_db()
    remove_invalid_offers()
    remove_expired_offers()
    start_bot_scheduler()
    server = ThreadingHTTPServer((HOST, PORT), MegaDescontosHandler)
    public_host = "127.0.0.1" if HOST in {"0.0.0.0", ""} else HOST
    print(f"Mega Descontos rodando em http://{public_host}:{PORT}")
    print(f"Admin em http://{public_host}:{PORT}/admin.html")
    print(f"Banco de dados: {offer_storage.description}")
    if HOST == "0.0.0.0" and offer_storage.backend != "postgresql":
        print("ATENCAO: DATABASE_URL nao configurada. O SQLite pode ser apagado pela hospedagem.")
    if os.environ.get("ADMIN_USERNAME") and os.environ.get("ADMIN_PASSWORD"):
        print("Login admin carregado por variaveis de ambiente.")
    else:
        print("Login admin padrao local: admin / admin123")
        print("Em producao, configure ADMIN_USERNAME e ADMIN_PASSWORD.")
    server.serve_forever()


if __name__ == "__main__":
    run()
