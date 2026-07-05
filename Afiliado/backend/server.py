import importlib.util
import json
import os
import secrets
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .offer_validation import partition_valid_offers
from .storage import offer_storage


APP_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = APP_DIR / "backend"
FRONTEND_DIR = APP_DIR / "frontend"
OFFERS_DB = APP_DIR / "data" / "offers_db.json"
DEFAULT_OFFERS_JS = APP_DIR / "data" / "offers.js"
ADMIN_CONFIG = APP_DIR / "config" / "admin.json"
BOT_PATH = APP_DIR / "bot" / "discount_bot.py"
BOT_STATUS = APP_DIR / "bot" / "status.json"
BOT_INTERVAL_SECONDS = 600
BOT_SETTINGS_PROVIDER = "bot_settings"
AUTOMATION_AGENT_PROVIDER = "mercadolivre_automation_agent"
AUTOMATION_JOB_PROVIDER = "mercadolivre_automation_job"
AMAZON_AGENT_PROVIDER = "amazon_automation_agent"
AMAZON_JOB_PROVIDER = "amazon_automation_job"
MAGALU_AGENT_PROVIDER = "magalu_automation_agent"
MAGALU_JOB_PROVIDER = "magalu_automation_job"
SNAPSHOT_CLEANUP_SOURCES = {"shopee_open_api"}
DEFAULT_BOT_SETTINGS = {
    "offersPerStore": 30,
    "minimumDiscount": 15,
    "minimumRating": 4.0,
    "minimumSales": 10,
    "minimumCommissionRate": 0.0,
    "maxPages": 2,
    "mercadoLivreMaxPages": 5,
    "autoPublishShopee": True,
    "autoPublishMercadoLivre": True,
}
SESSION_COOKIE = "mega_admin_session"
SESSIONS: set[str] = set()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
BOT_RUN_LOCK = threading.Lock()
CATALOG_WRITE_LOCK = threading.RLock()
ML_DEALS_CACHE: dict[str, object] = {"expiresAt": 0.0, "candidates": []}
ML_DEALS_LOCK = threading.Lock()
ANALYTICS_RATE_LIMIT: dict[str, tuple[int, int]] = {}
ANALYTICS_RATE_LOCK = threading.Lock()
APP_VERSION = "atomic-offer-upserts-2026-06-28"


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


def coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_bot_settings(payload: dict | None = None) -> dict:
    source = {**DEFAULT_BOT_SETTINGS, **(payload or {})}
    return {
        "offersPerStore": max(1, min(int(source["offersPerStore"]), 100)),
        "minimumDiscount": max(1, min(int(source["minimumDiscount"]), 90)),
        "minimumRating": max(0.0, min(float(source["minimumRating"]), 5.0)),
        "minimumSales": max(0, min(int(source["minimumSales"]), 1_000_000)),
        "minimumCommissionRate": max(0.0, min(float(source["minimumCommissionRate"]), 1.0)),
        "maxPages": max(1, min(int(source["maxPages"]), 50)),
        "mercadoLivreMaxPages": max(1, min(int(source["mercadoLivreMaxPages"]), 20)),
        "autoPublishShopee": coerce_bool(source["autoPublishShopee"]),
        "autoPublishMercadoLivre": coerce_bool(source["autoPublishMercadoLivre"]),
    }


def read_bot_settings() -> dict:
    ensure_offers_db()
    return normalize_bot_settings(offer_storage.get_integration(BOT_SETTINGS_PROVIDER))


def write_bot_settings(payload: dict) -> dict:
    settings = normalize_bot_settings(payload)
    offer_storage.set_integration(BOT_SETTINGS_PROVIDER, settings)
    return settings


def apply_bot_settings(settings: dict) -> None:
    os.environ["BOT_OFFERS_PER_STORE"] = str(settings["offersPerStore"])
    os.environ["SHOPEE_API_MAX_PAGES"] = str(settings["maxPages"])
    os.environ["MERCADOLIVRE_MAX_PAGES"] = str(settings["mercadoLivreMaxPages"])
    os.environ["BOT_MIN_RATING"] = str(settings["minimumRating"])
    os.environ["BOT_MIN_SALES"] = str(settings["minimumSales"])
    os.environ["BOT_MIN_COMMISSION_RATE"] = str(settings["minimumCommissionRate"])


def read_offers() -> list[dict]:
    ensure_offers_db()
    return offer_storage.read_all()


def write_offers(offers: list[dict]) -> None:
    offer_storage.replace_all(offers)


def analytics_device(user_agent: str) -> str:
    value = user_agent.casefold()
    if any(term in value for term in ("ipad", "tablet")):
        return "Tablet"
    if any(term in value for term in ("mobile", "android", "iphone")):
        return "Mobile"
    return "Desktop"


def allow_analytics_event(client: str) -> bool:
    minute = int(time.time() // 60)
    with ANALYTICS_RATE_LOCK:
        current_minute, count = ANALYTICS_RATE_LIMIT.get(client, (minute, 0))
        if current_minute != minute:
            current_minute, count = minute, 0
        if count >= 120:
            return False
        ANALYTICS_RATE_LIMIT[client] = (current_minute, count + 1)
        return True


def analytics_percent_change(current: int, previous: int) -> float:
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def build_analytics_report(days: int) -> dict:
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    events = offer_storage.read_analytics_events(previous_start.isoformat())
    offers_by_id = {str(offer.get("id")): offer for offer in read_offers()}

    def parsed_at(event: dict) -> datetime | None:
        try:
            value = datetime.fromisoformat(str(event.get("occurredAt") or "").replace("Z", "+00:00"))
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    current_events = []
    previous_events = []
    for event in events:
        occurred_at = parsed_at(event)
        if not occurred_at:
            continue
        if occurred_at >= current_start:
            current_events.append(event)
        elif occurred_at >= previous_start:
            previous_events.append(event)

    def count_type(source: list[dict], *types: str) -> int:
        return sum(event.get("type") in types for event in source)

    clicks = count_type(current_events, "offer_click")
    views = count_type(current_events, "page_view", "product_view")
    conversions = count_type(current_events, "outbound_click")
    previous_clicks = count_type(previous_events, "offer_click")
    previous_views = count_type(previous_events, "page_view", "product_view")
    previous_conversions = count_type(previous_events, "outbound_click")

    click_events = [event for event in current_events if event.get("type") == "offer_click"]
    category_counts = Counter(str(event.get("category") or "Outros") for event in click_events)
    store_counts = Counter(str(event.get("store") or "Outras lojas") for event in click_events)
    device_counts = Counter(str(event.get("device") or "Desktop") for event in current_events)
    offer_counts = Counter(str(event.get("offerId") or "") for event in click_events if event.get("offerId"))

    daily_clicks: dict[str, int] = defaultdict(int)
    previous_daily_clicks: dict[str, int] = defaultdict(int)
    for event in click_events:
        occurred_at = parsed_at(event)
        if occurred_at:
            daily_clicks[occurred_at.date().isoformat()] += 1
    for event in previous_events:
        if event.get("type") != "offer_click":
            continue
        occurred_at = parsed_at(event)
        if occurred_at:
            shifted = occurred_at + timedelta(days=days)
            previous_daily_clicks[shifted.date().isoformat()] += 1

    timeline = []
    for offset in range(days):
        day = (current_start.date() + timedelta(days=offset + 1)).isoformat()
        timeline.append(
            {
                "date": day,
                "clicks": daily_clicks[day],
                "previousClicks": previous_daily_clicks[day],
            }
        )

    def ranked(counter: Counter, limit: int = 6) -> list[dict]:
        total = sum(counter.values())
        return [
            {
                "name": name,
                "count": count,
                "percent": round((count / total) * 100, 1) if total else 0,
            }
            for name, count in counter.most_common(limit)
        ]

    top_offers = []
    for offer_id, count in offer_counts.most_common(5):
        offer = offers_by_id.get(offer_id, {})
        sample = next((event for event in click_events if str(event.get("offerId")) == offer_id), {})
        top_offers.append(
            {
                "id": offer_id,
                "title": offer.get("title") or sample.get("title") or "Oferta removida",
                "category": offer.get("category") or sample.get("category") or "Outros",
                "image": offer.get("image") or "",
                "clicks": count,
            }
        )

    ctr = round((clicks / views) * 100, 2) if views else 0.0
    previous_ctr = round((previous_clicks / previous_views) * 100, 2) if previous_views else 0.0
    return {
        "periodDays": days,
        "generatedAt": now.isoformat(),
        "totals": {
            "clicks": clicks,
            "views": views,
            "ctr": ctr,
            "conversions": conversions,
        },
        "changes": {
            "clicks": analytics_percent_change(clicks, previous_clicks),
            "views": analytics_percent_change(views, previous_views),
            "ctr": round(ctr - previous_ctr, 1),
            "conversions": analytics_percent_change(conversions, previous_conversions),
        },
        "timeline": timeline,
        "categories": ranked(category_counts),
        "stores": ranked(store_counts),
        "devices": ranked(device_counts),
        "topOffers": top_offers,
    }


def upsert_offer(offer: dict) -> tuple[dict, bool]:
    with CATALOG_WRITE_LOCK:
        offers = read_offers()
        title_key = " ".join(str(offer.get("title") or "").casefold().split())
        store_key = str(offer.get("store") or "").casefold().strip()
        existing = next(
            (
                current
                for current in offers
                if str(current.get("id")) == str(offer.get("id"))
                or (
                    store_key
                    and title_key
                    and str(current.get("store") or "").casefold().strip() == store_key
                    and " ".join(str(current.get("title") or "").casefold().split()) == title_key
                )
            ),
            None,
        )
        created = existing is None
        persisted = {**(existing or {}), **offer}
        if existing:
            persisted["id"] = existing["id"]
        remaining = [
            current
            for current in offers
            if not existing or str(current.get("id")) != str(existing.get("id"))
        ]
        write_offers([persisted, *remaining])
        return persisted, created


def read_candidates() -> list[dict]:
    ensure_offers_db()
    return offer_storage.read_candidates()


def write_candidates(candidates: list[dict]) -> None:
    review_offers = read_review_offers()
    offer_storage.replace_candidates([*candidates, *review_offers])


def complete_deal_candidates(candidate_ids: list[object]) -> int:
    completed = {str(candidate_id) for candidate_id in candidate_ids if str(candidate_id).strip()}
    if not completed:
        return 0
    candidates = read_deal_candidates()
    remaining = [candidate for candidate in candidates if str(candidate.get("id")) not in completed]
    removed = len(candidates) - len(remaining)
    write_candidates(remaining)
    return removed


def read_automation_agent_status() -> dict:
    return offer_storage.get_integration(AUTOMATION_AGENT_PROVIDER) or {
        "state": "offline",
        "message": "O agente local ainda nao se conectou.",
        "updatedAt": "",
    }


def agent_updated_at(payload: dict) -> str:
    client_value = str(payload.get("clientUpdatedAt") or "").strip()
    if client_value:
        try:
            parsed = datetime.fromisoformat(client_value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def write_automation_agent_status(payload: dict) -> dict:
    status = {
        "state": str(payload.get("state") or "idle")[:32],
        "message": str(payload.get("message") or "")[:500],
        "processed": max(0, int(payload.get("processed") or 0)),
        "failed": max(0, int(payload.get("failed") or 0)),
        "updatedAt": agent_updated_at(payload),
    }
    offer_storage.set_integration(AUTOMATION_AGENT_PROVIDER, status)
    return status


def queue_automation_job(target: int = 30) -> dict:
    target = max(1, min(int(target), 100))
    candidates = [
        candidate
        for candidate in read_deal_candidates()
        if candidate.get("store") == "Mercado Livre" and candidate.get("productUrl")
    ][:target]
    job = {
        "id": secrets.token_hex(8),
        "state": "pending" if candidates else "empty",
        "candidateIds": [str(candidate["id"]) for candidate in candidates],
        "target": target,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(AUTOMATION_JOB_PROVIDER, job)
    return job


def claim_automation_job() -> tuple[dict, list[dict]]:
    job = offer_storage.get_integration(AUTOMATION_JOB_PROVIDER) or {}
    if job.get("state") != "pending":
        return job, []
    candidate_ids = {str(candidate_id) for candidate_id in job.get("candidateIds", [])}
    candidates = [
        candidate
        for candidate in read_deal_candidates()
        if str(candidate.get("id")) in candidate_ids
    ]
    job = {
        **job,
        "state": "processing",
        "claimedAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(AUTOMATION_JOB_PROVIDER, job)
    return job, candidates


def finish_automation_job(job_id: str, candidate_ids: list[object], state: str = "completed") -> dict:
    job = offer_storage.get_integration(AUTOMATION_JOB_PROVIDER) or {}
    if not job or str(job.get("id")) != str(job_id):
        raise ValueError("O lote de automacao nao existe mais.")
    removed = complete_deal_candidates(candidate_ids)
    job = {
        **job,
        "state": state if state in {"completed", "failed"} else "completed",
        "removedCandidates": removed,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(AUTOMATION_JOB_PROVIDER, job)
    return job


def read_amazon_agent_status() -> dict:
    return offer_storage.get_integration(AMAZON_AGENT_PROVIDER) or {
        "state": "offline",
        "message": "O agente Amazon ainda nao se conectou.",
        "updatedAt": "",
    }


def write_amazon_agent_status(payload: dict) -> dict:
    status = {
        "state": str(payload.get("state") or "idle")[:32],
        "message": str(payload.get("message") or "")[:500],
        "processed": max(0, int(payload.get("processed") or 0)),
        "failed": max(0, int(payload.get("failed") or 0)),
        "updatedAt": agent_updated_at(payload),
    }
    offer_storage.set_integration(AMAZON_AGENT_PROVIDER, status)
    return status


def queue_amazon_job(target: int = 30) -> dict:
    target = max(1, min(int(target), 100))
    job = {
        "id": secrets.token_hex(8),
        "state": "pending",
        "target": target,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(AMAZON_JOB_PROVIDER, job)
    return job


def claim_amazon_job() -> dict:
    job = offer_storage.get_integration(AMAZON_JOB_PROVIDER) or {}
    if job.get("state") != "pending":
        return job
    job = {
        **job,
        "state": "processing",
        "claimedAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(AMAZON_JOB_PROVIDER, job)
    return job


def finish_amazon_job(job_id: str, state: str = "completed") -> dict:
    job = offer_storage.get_integration(AMAZON_JOB_PROVIDER) or {}
    if not job or str(job.get("id")) != str(job_id):
        raise ValueError("O lote Amazon nao existe mais.")
    job = {
        **job,
        "state": state if state in {"completed", "failed"} else "completed",
        "finishedAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(AMAZON_JOB_PROVIDER, job)
    return job


def read_magalu_agent_status() -> dict:
    return offer_storage.get_integration(MAGALU_AGENT_PROVIDER) or {
        "state": "offline",
        "message": "O agente Magalu ainda nao se conectou.",
        "updatedAt": "",
    }


def write_magalu_agent_status(payload: dict) -> dict:
    status = {
        "state": str(payload.get("state") or "idle")[:32],
        "message": str(payload.get("message") or "")[:500],
        "processed": max(0, int(payload.get("processed") or 0)),
        "failed": max(0, int(payload.get("failed") or 0)),
        "updatedAt": agent_updated_at(payload),
    }
    offer_storage.set_integration(MAGALU_AGENT_PROVIDER, status)
    return status


def queue_magalu_job(target: int = 30) -> dict:
    target = max(1, min(int(target), 100))
    job = {
        "id": secrets.token_hex(8),
        "state": "pending",
        "target": target,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(MAGALU_JOB_PROVIDER, job)
    return job


def claim_magalu_job() -> dict:
    job = offer_storage.get_integration(MAGALU_JOB_PROVIDER) or {}
    if job.get("state") != "pending":
        return job
    job = {
        **job,
        "state": "processing",
        "claimedAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(MAGALU_JOB_PROVIDER, job)
    return job


def finish_magalu_job(job_id: str, state: str = "completed") -> dict:
    job = offer_storage.get_integration(MAGALU_JOB_PROVIDER) or {}
    if not job or str(job.get("id")) != str(job_id):
        raise ValueError("O lote Magalu nao existe mais.")
    job = {
        **job,
        "state": state if state in {"completed", "failed"} else "completed",
        "finishedAt": datetime.now(timezone.utc).isoformat(),
    }
    offer_storage.set_integration(MAGALU_JOB_PROVIDER, job)
    return job


def read_deal_candidates() -> list[dict]:
    return [
        candidate for candidate in read_candidates()
        if candidate.get("candidateType") != "review_offer"
    ]


def read_review_offers() -> list[dict]:
    return [
        candidate for candidate in read_candidates()
        if candidate.get("candidateType") == "review_offer"
    ]


def write_review_offers(review_offers: list[dict]) -> None:
    deal_candidates = read_deal_candidates()
    offer_storage.replace_candidates([*deal_candidates, *review_offers])


def upsert_review_offers(incoming_offers: list[dict]) -> int:
    published_ids = {str(offer.get("id")) for offer in read_offers()}
    review_by_id = {
        str(offer.get("id")): offer
        for offer in read_review_offers()
        if offer.get("id") is not None
    }
    added = 0
    for offer in incoming_offers:
        if not isinstance(offer, dict):
            continue
        offer_id = str(offer.get("id") or offer.get("sourceProductId") or offer.get("affiliateUrl") or offer.get("title") or "")
        if not offer_id or offer_id in published_ids:
            continue
        prepared = {
            **offer,
            "id": offer_id,
            "candidateType": "review_offer",
            "reviewStatus": "pending",
            "reviewAddedAt": datetime.now(timezone.utc).isoformat(),
        }
        review_by_id[offer_id] = prepared
        added += 1
    write_review_offers(list(review_by_id.values()))
    return added


def publish_automatic_offers(incoming_offers: list[dict]) -> int:
    valid_offers, rejected = partition_valid_offers(incoming_offers)
    if rejected:
        print(f"[Mega Descontos] {len(rejected)} ofertas automaticas rejeitadas pela validacao.")
    if not valid_offers:
        return 0

    merged = {str(offer.get("id")): offer for offer in read_offers() if offer.get("id") is not None}
    for offer in valid_offers:
        merged[str(offer["id"])] = offer
    write_offers(list(merged.values()))

    published_ids = {str(offer["id"]) for offer in valid_offers}
    remaining_review = [
        offer for offer in read_review_offers()
        if str(offer.get("id")) not in published_ids
    ]
    write_review_offers(remaining_review)
    return len(valid_offers)


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


def cleanup_catalog(active_ids_by_source: dict[str, set[str]] | None = None) -> dict:
    now = datetime.now(timezone.utc)
    active_ids_by_source = active_ids_by_source or {}

    def keep_offer(offer: dict) -> bool:
        expires_at = parse_datetime(str(offer.get("expiresAt") or ""))
        if expires_at and expires_at <= now:
            return False
        source = str(offer.get("source") or "")
        active_ids = active_ids_by_source.get(source) if source in SNAPSHOT_CLEANUP_SOURCES else None
        if active_ids is not None and str(offer.get("id")) not in active_ids:
            return False
        return not partition_valid_offers([offer])[1]

    offers = read_offers()
    active_offers = [offer for offer in offers if keep_offer(offer)]
    if len(active_offers) != len(offers):
        write_offers(active_offers)

    review_offers = read_review_offers()
    active_review = [offer for offer in review_offers if keep_offer(offer)]
    if len(active_review) != len(review_offers):
        write_review_offers(active_review)

    return {
        "publishedRemoved": len(offers) - len(active_offers),
        "reviewRemoved": len(review_offers) - len(active_review),
    }


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


def run_bot_once() -> dict:
    if not BOT_RUN_LOCK.acquire(blocking=False):
        print("[Mega Descontos] Uma execucao do bot ja esta em andamento.")
        return {"ok": False, "error": "Uma execucao do bot ja esta em andamento."}
    try:
        bot = load_discount_bot()
        settings = read_bot_settings()
        apply_bot_settings(settings)
        existing_offers = read_offers()
        offers = bot.generate_offers(
            bot.DEFAULT_INPUT,
            bot.DEFAULT_OUTPUT,
            bot.DEFAULT_DB,
            minimum_discount=settings["minimumDiscount"],
            purge_missing=True,
            real_sources_path=bot.DEFAULT_REAL_SOURCES,
            status_path=bot.DEFAULT_STATUS,
            existing_offers=existing_offers,
            persist_db=False,
        )
        automatic_sources = set()
        if settings["autoPublishShopee"]:
            automatic_sources.add("shopee_open_api")
        if settings["autoPublishMercadoLivre"]:
            automatic_sources.update({"mercadolivre_deals", "mercadolivre_search", "mercadolivre_affiliate_link"})

        automatic_offers = [
            offer for offer in offers
            if str(offer.get("source") or "") in automatic_sources
        ]
        review_offers = [
            offer for offer in offers
            if str(offer.get("source") or "") not in automatic_sources
        ]
        auto_published = 0
        auto_published = publish_automatic_offers(automatic_offers)
        added_to_review = upsert_review_offers(review_offers)
        write_candidates(bot.get_candidates())
        status = read_bot_status()
        shopee_status = next(
            (source for source in status.get("sources", []) if source.get("type") == "shopee_open_api"),
            None,
        )
        mercadolivre_statuses = [
            source for source in status.get("sources", [])
            if str(source.get("type") or "").startswith("mercadolivre_")
        ]
        candidates = bot.get_candidates()
        store_summary = {
            "shopee": {
                "found": int(shopee_status.get("count") or 0) if shopee_status else 0,
                "candidates": sum(1 for offer in candidates if offer.get("store") == "Shopee"),
                "ok": bool(shopee_status and shopee_status.get("ok")),
            },
            "mercadolivre": {
                "found": sum(int(source.get("count") or 0) for source in mercadolivre_statuses if source.get("ok")),
                "candidates": sum(1 for offer in candidates if offer.get("store") == "Mercado Livre"),
                "ok": any(source.get("ok") for source in mercadolivre_statuses),
            },
        }
        active_ids_by_source = {}
        for offer in offers:
            source = str(offer.get("source") or "")
            if source in SNAPSHOT_CLEANUP_SOURCES:
                active_ids_by_source.setdefault(source, set()).add(str(offer.get("id")))
        if shopee_status and shopee_status.get("ok"):
            active_ids_by_source.setdefault("shopee_open_api", set())
        cleanup = cleanup_catalog(active_ids_by_source)
        print(
            f"[Mega Descontos] Publicadas automaticamente: {auto_published}. "
            f"Enviadas para revisao: {added_to_review}. Limpeza: {cleanup}."
        )
        enabled_results = []
        if settings["autoPublishShopee"]:
            enabled_results.append(store_summary["shopee"]["ok"])
        if settings["autoPublishMercadoLivre"]:
            enabled_results.append(store_summary["mercadolivre"]["ok"])
        return {
            "ok": any(enabled_results) if enabled_results else True,
            "generatedOffers": len(offers),
            "autoPublished": auto_published,
            "addedToReview": added_to_review,
            "cleanup": cleanup,
            "reviewOffers": len(read_review_offers()),
            "shopee": shopee_status,
            "mercadolivre": mercadolivre_statuses,
            "storeSummary": store_summary,
            "automaticSources": sorted(automatic_sources),
            "status": status,
            "settings": settings,
        }
    except Exception as error:
        print(f"[Mega Descontos] Erro no bot: {error}")
        return {"ok": False, "error": str(error)}
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
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/offers":
            removed = remove_expired_offers()
            offers = read_offers()
            write_json(self, {"offers": offers, "removedExpired": removed})
            return

        if parsed.path == "/api/discount-requests":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"requests": offer_storage.read_discount_requests()})
            return

        if parsed.path == "/api/analytics":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                requested_days = int(parse_qs(parsed.query).get("days", ["30"])[0])
                days = requested_days if requested_days in {7, 30, 90} else 30
                write_json(self, build_analytics_report(days))
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/auth":
            write_json(self, {"authenticated": is_authenticated(self)})
            return

        if parsed.path == "/healthz":
            write_json(
                self,
                {
                    "ok": True,
                    "version": APP_VERSION,
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

        if parsed.path == "/api/bot-settings":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"settings": read_bot_settings()})
            return

        if parsed.path == "/api/candidates":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"candidates": read_deal_candidates()})
            return

        if parsed.path == "/api/automation-agent/status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"status": read_automation_agent_status()})
            return

        if parsed.path == "/api/automation-agent/work":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            job, candidates = claim_automation_job()
            write_json(self, {"job": job, "candidates": candidates})
            return

        if parsed.path == "/api/amazon-automation-agent/status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"status": read_amazon_agent_status()})
            return

        if parsed.path == "/api/amazon-automation-agent/work":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"job": claim_amazon_job()})
            return

        if parsed.path == "/api/magalu-automation-agent/status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"status": read_magalu_agent_status()})
            return

        if parsed.path == "/api/magalu-automation-agent/work":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"job": claim_magalu_job()})
            return

        if parsed.path == "/api/review-offers":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            write_json(self, {"reviewOffers": read_review_offers()})
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
                fallback = read_deal_candidates()
                write_json(self, {"error": str(error), "candidates": fallback}, 502 if not fallback else 200)
            return

        if parsed.path.startswith("/admin") and parsed.path.endswith(".html") and not is_authenticated(self):
            self.send_response(302)
            self.send_header("Location", "/login.html")
            self.end_headers()
            return

        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/analytics/events":
            forwarded = self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            client = forwarded or self.client_address[0]
            if not allow_analytics_event(client):
                write_json(self, {"error": "Muitos eventos enviados."}, 429)
                return
            try:
                payload = read_json_body(self) or {}
                if not isinstance(payload, dict):
                    raise ValueError("Evento invalido.")
                event_type = str(payload.get("type") or "").strip()
                if event_type not in {"page_view", "product_view", "offer_click", "outbound_click"}:
                    raise ValueError("Tipo de evento invalido.")
                client_time = str(payload.get("occurredAt") or "").strip()
                try:
                    occurred_at = datetime.fromisoformat(client_time.replace("Z", "+00:00"))
                    if occurred_at.tzinfo is None:
                        raise ValueError
                    occurred_at_value = occurred_at.astimezone(timezone.utc).isoformat()
                except ValueError:
                    occurred_at_value = datetime.now(timezone.utc).isoformat()
                event = {
                    "id": secrets.token_hex(12),
                    "type": event_type,
                    "offerId": str(payload.get("offerId") or "")[:120],
                    "title": str(payload.get("title") or "")[:240],
                    "category": str(payload.get("category") or "")[:100],
                    "store": str(payload.get("store") or "")[:100],
                    "path": str(payload.get("path") or "")[:240],
                    "device": analytics_device(self.headers.get("User-Agent", "")),
                    "occurredAt": occurred_at_value,
                }
                ensure_offers_db()
                offer_storage.create_analytics_event(event)
                write_json(self, {"ok": True}, 202)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/discount-requests":
            try:
                payload = read_json_body(self) or {}
                if not isinstance(payload, dict):
                    raise ValueError("Dados invalidos.")
                product = " ".join(str(payload.get("product") or "").split())
                contact = " ".join(str(payload.get("contact") or "").split())
                if len(product) < 3:
                    raise ValueError("Informe o produto ou cole o link da loja.")
                if len(product) > 500:
                    raise ValueError("A descricao do produto e muito longa.")
                if contact and len(contact) > 180:
                    raise ValueError("O contato informado e muito longo.")
                request = {
                    "id": secrets.token_hex(8),
                    "product": product,
                    "contact": contact,
                    "status": "pending",
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                }
                offer_storage.create_discount_request(request)
                write_json(
                    self,
                    {
                        "ok": True,
                        "requestId": request["id"],
                        "message": "Pedido recebido! Vamos buscar o melhor desconto para voce.",
                    },
                    201,
                )
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

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
            result = run_bot_once()
            if result.get("ok"):
                target = int(result.get("settings", {}).get("offersPerStore") or 30)
                job = queue_automation_job(target)
                amazon_job = queue_amazon_job(target)
                magalu_job = queue_magalu_job(target)
                result["automationJob"] = {
                    "id": job["id"],
                    "state": job["state"],
                    "total": len(job["candidateIds"]),
                }
                result["amazonAutomationJob"] = {
                    "id": amazon_job["id"],
                    "state": amazon_job["state"],
                }
                result["magaluAutomationJob"] = {
                    "id": magalu_job["id"],
                    "state": magalu_job["state"],
                }
                result["offersPerStore"] = target
            write_json(self, result, 200 if result.get("ok") else 502)
            return

        if parsed.path == "/api/candidates/complete":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                candidate_ids = payload.get("ids", [])
                if not isinstance(candidate_ids, list):
                    raise ValueError("Envie uma lista de identificadores.")
                removed = complete_deal_candidates(candidate_ids)
                write_json(self, {"ok": True, "removed": removed})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/automation-agent/status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                write_json(self, {"ok": True, "status": write_automation_agent_status(payload)})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/automation-agent/job/complete":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                candidate_ids = payload.get("ids", [])
                if not isinstance(candidate_ids, list):
                    raise ValueError("Envie uma lista de identificadores.")
                job = finish_automation_job(
                    str(payload.get("jobId") or ""),
                    candidate_ids,
                    str(payload.get("state") or "completed"),
                )
                write_json(self, {"ok": True, "job": job})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/amazon-automation-agent/status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                write_json(self, {"ok": True, "status": write_amazon_agent_status(payload)})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/amazon-automation-agent/job/complete":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                job = finish_amazon_job(
                    str(payload.get("jobId") or ""),
                    str(payload.get("state") or "completed"),
                )
                write_json(self, {"ok": True, "job": job})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/magalu-automation-agent/status":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                write_json(self, {"ok": True, "status": write_magalu_agent_status(payload)})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/magalu-automation-agent/job/complete":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                job = finish_magalu_job(
                    str(payload.get("jobId") or ""),
                    str(payload.get("state") or "completed"),
                )
                write_json(self, {"ok": True, "job": job})
            except (TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/cron/run":
            expected = os.environ.get("CRON_SECRET", "").strip()
            provided = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not expected or not secrets.compare_digest(provided, expected):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            result = run_bot_once()
            write_json(self, result, 200 if result.get("ok") else 502)
            return

        if parsed.path == "/api/review-offers":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                offers = payload.get("offers", payload if isinstance(payload, list) else [])
                if isinstance(offers, dict):
                    offers = [offers]
                if not isinstance(offers, list):
                    raise ValueError("Envie uma lista de ofertas para revisao.")
                added = upsert_review_offers(offers)
                write_json(self, {"ok": True, "total": added, "reviewOffers": read_review_offers()})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/review-offers/approve":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                target_id = str(payload.get("id") or "")
                if not target_id:
                    raise ValueError("Informe o id da oferta.")
                review_offers = read_review_offers()
                candidate = next((offer for offer in review_offers if str(offer.get("id")) == target_id), None)
                if not candidate:
                    raise ValueError("Oferta nao encontrada na fila.")
                offer = {
                    **candidate,
                    "candidateType": "",
                    "reviewStatus": "",
                    "source": candidate.get("source") or "review_admin",
                    "foundAt": candidate.get("foundAt") or datetime.now(timezone.utc).isoformat(),
                }
                offer.pop("candidateType", None)
                offer.pop("reviewStatus", None)
                offer.pop("reviewAddedAt", None)
                valid_offers, rejected = partition_valid_offers([offer])
                if rejected or not valid_offers:
                    details = "; ".join(rejected[0]["errors"]) if rejected else "Oferta invalida."
                    raise ValueError(details)
                current = read_offers()
                merged = [valid_offers[0], *[item for item in current if str(item.get("id")) != target_id]]
                write_offers(merged)
                remaining = [offer for offer in review_offers if str(offer.get("id")) != target_id]
                write_review_offers(remaining)
                write_json(self, {"ok": True, "offer": valid_offers[0], "reviewOffers": remaining})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/review-offers/reject":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                target_id = str(payload.get("id") or "")
                if not target_id:
                    raise ValueError("Informe o id da oferta.")
                remaining = [offer for offer in read_review_offers() if str(offer.get("id")) != target_id]
                write_review_offers(remaining)
                write_json(self, {"ok": True, "reviewOffers": remaining})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
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
                offer, created = upsert_offer(offer)
                write_json(self, {"offer": offer, "created": created})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/amazon/import-link":
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
                if all(payload.get(field) not in (None, "") for field in ("title", "image", "oldPrice", "currentPrice")):
                    if not bot.is_amazon_url(affiliate_url):
                        raise ValueError("Use um link da Amazon ou amzn.to.")
                    product = {
                        "id": str(payload.get("sourceProductId") or payload.get("productUrl") or affiliate_url),
                        "title": str(payload["title"]).strip(),
                        "store": "Amazon",
                        "category": category,
                        "affiliateUrl": affiliate_url,
                        "oldPrice": float(payload["oldPrice"]),
                        "currentPrice": float(payload["currentPrice"]),
                        "image": str(payload["image"]).strip(),
                        "expiresAt": str(payload.get("expiresAt") or ""),
                    }
                else:
                    product = bot.fetch_amazon_affiliate_product(affiliate_url, category)
                offer = bot.normalize_product(product, minimum_discount=1)
                if not offer:
                    raise ValueError("O link nao informou uma oferta ativa com preco anterior e atual.")
                offer["source"] = "amazon_affiliate_link"
                offer, created = upsert_offer(offer)
                write_json(self, {"offer": offer, "created": created})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/shopee/import-link":
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
                if all(payload.get(field) not in (None, "") for field in ("title", "image", "oldPrice", "currentPrice")):
                    if not bot.is_shopee_affiliate_url(affiliate_url):
                        raise ValueError("Use um link de afiliado da Shopee.")
                    product = {
                        "id": str(payload.get("productUrl") or affiliate_url),
                        "title": str(payload["title"]).strip(),
                        "store": "Shopee",
                        "category": category,
                        "affiliateUrl": affiliate_url,
                        "oldPrice": float(payload["oldPrice"]),
                        "currentPrice": float(payload["currentPrice"]),
                        "image": str(payload["image"]).strip(),
                        "expiresAt": str(payload.get("expiresAt") or ""),
                    }
                else:
                    product = bot.fetch_shopee_affiliate_product(affiliate_url, category)
                offer = bot.normalize_product(product, minimum_discount=1)
                if not offer:
                    raise ValueError("O link nao informou uma oferta ativa com preco anterior e atual.")
                offer["source"] = "shopee_affiliate_link"
                offer, created = upsert_offer(offer)
                write_json(self, {"offer": offer, "created": created})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        if parsed.path == "/api/magalu/import-link":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self) or {}
                if not isinstance(payload, dict):
                    raise ValueError("Dados invalidos.")
                affiliate_url = str(payload.get("affiliateUrl") or "").strip()
                category = str(payload.get("category") or "Ofertas").strip()
                from bot.magalu_discovery_bot import is_influencer_product_url

                if not is_influencer_product_url(affiliate_url):
                    raise ValueError("Use o link do produto dentro da sua loja do Influenciador Magalu.")
                if not all(payload.get(field) not in (None, "") for field in ("title", "image", "oldPrice", "currentPrice")):
                    raise ValueError("Os dados da oferta Magalu estao incompletos.")
                bot = load_discount_bot()
                product = {
                    "id": str(payload.get("sourceProductId") or payload.get("productUrl") or affiliate_url),
                    "title": str(payload["title"]).strip(),
                    "store": "Magalu",
                    "category": category,
                    "affiliateUrl": affiliate_url,
                    "oldPrice": float(payload["oldPrice"]),
                    "currentPrice": float(payload["currentPrice"]),
                    "image": str(payload["image"]).strip(),
                    "expiresAt": str(payload.get("expiresAt") or ""),
                }
                offer = bot.normalize_product(product, minimum_discount=1)
                if not offer:
                    raise ValueError("O link nao informou uma oferta ativa com preco anterior e atual.")
                offer["source"] = "magalu_affiliate_link"
                offer, created = upsert_offer(offer)
                write_json(self, {"offer": offer, "created": created})
            except Exception as error:
                write_json(self, {"error": str(error)}, 400)
            return

        write_json(self, {"error": "Rota nao encontrada."}, 404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/bot-settings":
            if not is_authenticated(self):
                write_json(self, {"error": "Nao autorizado."}, 401)
                return
            try:
                payload = read_json_body(self)
                if not isinstance(payload, dict):
                    raise ValueError("Configuracoes invalidas.")
                settings = write_bot_settings(payload)
                write_json(self, {"ok": True, "settings": settings})
            except (KeyError, TypeError, ValueError) as error:
                write_json(self, {"error": str(error)}, 400)
            return

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
    if os.environ.get("RUN_INTERNAL_SCHEDULER", "true").lower() == "true":
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
