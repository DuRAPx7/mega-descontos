import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from offer_validation import validate_offer

DEFAULT_INPUT = ROOT_DIR / "bot" / "produtos_monitorados.json"
DEFAULT_FEEDS = ROOT_DIR / "bot" / "source_feeds.json"
DEFAULT_REAL_SOURCES = ROOT_DIR / "bot" / "real_sources.json"
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "ofertas_geradas.json"
DEFAULT_DB = ROOT_DIR / "data" / "offers_db.json"
DEFAULT_STATUS = ROOT_DIR / "bot" / "status.json"
AFFILIATE_CONFIG = ROOT_DIR / "config" / "affiliate.json"
SOURCE_STATUS: list[dict] = []
LAST_CANDIDATES: list[dict] = []


class ProductMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        key = values.get("property") or values.get("name") or values.get("itemprop")
        content = values.get("content")
        if key and content:
            self.metadata[key.lower()] = content


def parse_mercadolivre_money_label(value: str | None) -> float | None:
    match = re.search(r"(\d[\d.]*) reais(?: com (\d{1,2}) centavos)?", value or "", re.IGNORECASE)
    if not match:
        return None
    reais = int(match.group(1).replace(".", ""))
    cents = int(match.group(2) or 0)
    return reais + cents / 100


class MercadoLivreDealsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict] = []
        self.current: dict | None = None

    def finish_current(self) -> None:
        item = self.current
        if not item:
            return
        if all(item.get(field) for field in ("title", "url", "image", "oldPrice", "currentPrice")):
            if float(item["currentPrice"]) < float(item["oldPrice"]):
                self.items.append(item)
        self.current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "div" and "poly-card--grid-card" in classes:
            self.finish_current()
            self.current = {"store": "Mercado Livre", "category": "Ofertas"}
            return
        if not self.current:
            return
        if tag == "img" and "poly-component__picture" in classes:
            self.current["image"] = normalize_image_url(values.get("src"))
            self.current["title"] = html.unescape(values.get("alt") or "").strip()
        elif tag == "a" and "poly-component__title" in classes:
            url = html.unescape(values.get("href") or "")
            if url.startswith("https://"):
                self.current["url"] = url
                product_match = re.search(r"/(?:p|up)/(?P<id>MLB\d+)", url)
                self.current["id"] = product_match.group("id") if product_match else url
        elif tag == "s" and "andes-money-amount--previous" in classes:
            self.current["oldPrice"] = parse_mercadolivre_money_label(values.get("aria-label"))
        elif tag == "span" and "andes-money-amount" in classes and not self.current.get("currentPrice"):
            label = values.get("aria-label") or ""
            if label.lower().startswith("agora:"):
                self.current["currentPrice"] = parse_mercadolivre_money_label(label)

    def close(self) -> None:
        super().close()
        self.finish_current()


def load_affiliate_config() -> dict:
    if not AFFILIATE_CONFIG.exists():
        return {}
    try:
        with AFFILIATE_CONFIG.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


AFFILIATE_VALUES = load_affiliate_config()


def credential(name: str, default: str = "") -> str:
    return os.environ.get(name) or str(AFFILIATE_VALUES.get(name, default))


def record_source_status(name: str, source_type: str, ok: bool, count: int = 0, error: str = "") -> None:
    SOURCE_STATUS.append(
        {
            "name": name,
            "type": source_type,
            "ok": ok,
            "count": count,
            "error": error,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


@dataclass
class StoreConfig:
    affiliate_param: str
    affiliate_code: str


STORE_CONFIGS = {
    "Amazon": StoreConfig("tag", credential("AMAZON_ASSOCIATE_TAG")),
}


def calculate_discount(old_price: float, current_price: float) -> int:
    if old_price <= 0 or current_price >= old_price:
        return 0
    return round(((old_price - current_price) / old_price) * 100)


def attach_affiliate_code(url: str, store: str) -> str:
    config = STORE_CONFIGS.get(store)
    if not config or not config.affiliate_code:
        return ""

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[config.affiliate_param] = config.affiliate_code
    return urlunparse(parsed._replace(query=urlencode(query)))


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def is_expired(value: str | None) -> bool:
    expires_at = parse_datetime(value)
    return bool(expires_at and expires_at <= datetime.now(timezone.utc))


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{path} deve conter uma lista.")
    return data


def parse_mercadolivre_affiliate_page(page: str, source: dict) -> dict:
    parser = ProductMetadataParser()
    parser.feed(page)
    title = parser.metadata.get("og:title") or parser.metadata.get("title") or ""
    image_url = parser.metadata.get("og:image") or parser.metadata.get("image") or ""

    price_pattern = re.compile(
        r'"previous_price":\{"value":(?P<old>\d+(?:\.\d+)?).*?'
        r'"current_price":\{"value":(?P<current>\d+(?:\.\d+)?)',
        re.DOTALL,
    )
    price_match = None
    for candidate in price_pattern.finditer(page):
        context = html.unescape(page[max(0, candidate.start() - 1200):candidate.end() + 400])
        if title and title.lower() in context.lower():
            price_match = candidate
            break

    if not title or not image_url or not price_match:
        raise ValueError("A pagina nao informou titulo, imagem e os dois precos do produto.")

    return {
        "id": source.get("id") or source.get("affiliateUrl"),
        "title": title,
        "store": "Mercado Livre",
        "category": source.get("category", "Ofertas"),
        "affiliateUrl": source["affiliateUrl"],
        "oldPrice": float(price_match.group("old")),
        "currentPrice": float(price_match.group("current")),
        "image": normalize_image_url(image_url),
        "expiresAt": source.get("expiresAt", ""),
    }


def is_mercadolivre_affiliate_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        hostname == "meli.la"
        or (hostname.endswith("mercadolivre.com.br") and parsed.path.startswith("/social/"))
    )


def fetch_mercadolivre_affiliate_product(affiliate_url: str, category: str = "Ofertas") -> dict:
    affiliate_url = affiliate_url.strip()
    if not is_mercadolivre_affiliate_url(affiliate_url):
        raise ValueError("Use um link de afiliado meli.la gerado no Mercado Livre.")

    request = Request(
        affiliate_url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
        },
    )
    with urlopen(request, timeout=25) as response:
        final_host = (urlparse(response.geturl()).hostname or "").lower()
        if final_host != "mercadolivre.com.br" and not final_host.endswith(".mercadolivre.com.br"):
            raise ValueError("O link nao direcionou para um produto do Mercado Livre.")
        page = response.read().decode("utf-8", errors="replace")

    source = {
        "id": affiliate_url,
        "affiliateUrl": affiliate_url,
        "category": category or "Ofertas",
    }
    return parse_mercadolivre_affiliate_page(page, source)


def fetch_mercadolivre_affiliate_link(source: dict) -> list[dict]:
    name = source.get("name") or source.get("affiliateUrl", "Link Mercado Livre")
    if source.get("enabled") is False:
        record_source_status(name, "mercadolivre_affiliate_link", True, 0, "Fonte desativada.")
        return []

    affiliate_url = str(source.get("affiliateUrl") or "").strip()
    if not affiliate_url:
        record_source_status(name, "mercadolivre_affiliate_link", False, 0, "Link de afiliado ausente.")
        return []

    try:
        product = fetch_mercadolivre_affiliate_product(
            affiliate_url,
            str(source.get("category") or "Ofertas"),
        )
        product["id"] = source.get("id") or product["id"]
    except Exception as error:
        record_source_status(name, "mercadolivre_affiliate_link", False, 0, str(error))
        return []

    record_source_status(product["title"], "mercadolivre_affiliate_link", True, 1)
    return [product]


def parse_mercadolivre_deals_page(page: str, limit: int = 24) -> list[dict]:
    parser = MercadoLivreDealsParser()
    parser.feed(page)
    parser.close()
    return parser.items[:max(1, min(limit, 48))]


def fetch_mercadolivre_deals(limit: int = 24) -> list[dict]:
    request = Request(
        "https://www.mercadolivre.com.br/ofertas",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36",
        },
    )
    with urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8", errors="replace")
    return parse_mercadolivre_deals_page(page, limit)


def load_monitored_products(path: Path) -> list[dict]:
    products = []
    for source in load_json_list(path):
        if source.get("type") == "mercadolivre_affiliate_link":
            products.extend(fetch_mercadolivre_affiliate_link(source))
        else:
            products.append(source)
    return products


def read_field(item: dict, dotted_path: str | None):
    if not dotted_path:
        return None

    current = item
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def xml_element_to_dict(element) -> dict:
    data = {f"@{key}": value for key, value in element.attrib.items()}
    for child in element:
        key = xml_local_name(child.tag)
        value = xml_element_to_dict(child) if list(child) else (child.text or "").strip()
        if key not in data:
            data[key] = value
    return data


def decode_feed(raw_payload: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw_payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_payload.decode("utf-8", errors="replace")


def parse_feed_payload(raw_payload: bytes, feed: dict, content_type: str = "") -> tuple[list[dict], str]:
    configured_format = str(feed.get("format", "auto")).lower()
    text = decode_feed(raw_payload)
    stripped = text.lstrip()

    if configured_format == "auto":
        if "xml" in content_type or stripped.startswith("<"):
            configured_format = "xml"
        elif "json" in content_type or stripped.startswith(("{", "[")):
            configured_format = "json"
        else:
            configured_format = "csv"

    if configured_format == "json":
        payload = json.loads(text)
        items_path = feed.get("itemsPath", "items")
        items = read_field(payload, items_path) if isinstance(payload, dict) else payload
    elif configured_format in {"xml", "yml"}:
        root = ElementTree.fromstring(raw_payload)
        item_tag = str(feed.get("itemTag", "offer"))
        items = [xml_element_to_dict(element) for element in root.iter() if xml_local_name(element.tag) == item_tag]
        configured_format = "xml"
    elif configured_format == "csv":
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        except csv.Error:
            dialect = csv.excel
        items = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    else:
        raise ValueError(f"Formato de feed nao suportado: {configured_format}")

    if not isinstance(items, list):
        raise ValueError("O feed nao retornou uma lista de produtos.")
    return [item for item in items if isinstance(item, dict)], configured_format


def parse_price(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    normalized = re.sub(r"[^0-9,.-]", "", str(value or "").strip())
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    return float(normalized)


def fetch_feed_items(feed: dict) -> list[dict]:
    if not feed.get("enabled"):
        record_source_status(feed.get("name", "Feed afiliado"), "affiliate_feed", True, 0, "Fonte desativada.")
        return []

    feed_name = feed.get("name", "Feed afiliado")
    feed_url = credential(str(feed.get("urlEnv") or "")) or str(feed.get("url") or "").strip()
    if not feed_url:
        record_source_status(feed_name, "affiliate_feed", False, 0, f"Configure {feed.get('urlEnv', 'a URL do feed')}.")
        return []

    try:
        request = Request(feed_url, headers={"Accept": "*/*", "User-Agent": "MegaDescontosBot/1.0"})
        with urlopen(request, timeout=30) as response:
            raw_payload = response.read(50_000_001)
            content_type = response.headers.get("Content-Type", "")
        if len(raw_payload) > 50_000_000:
            raise ValueError("Feed maior que o limite de 50 MB.")
        items, feed_format = parse_feed_payload(raw_payload, feed, content_type)
    except Exception as error:
        record_source_status(feed_name, "affiliate_feed", False, 0, str(error))
        return []

    field_map = feed.get("fieldMap", {})
    normalized = []
    max_items = min(max(int(feed.get("maxItems", 2000)), 1), 10000)
    for index, item in enumerate(items[:max_items]):
        normalized.append(
            {
                "id": read_field(item, field_map.get("id")) or item.get("id") or item.get("@id") or f"{feed_name}-{index}",
                "title": read_field(item, field_map.get("title")),
                "store": feed.get("store") or read_field(item, field_map.get("store")),
                "category": feed.get("category") or read_field(item, field_map.get("category")),
                "url": read_field(item, field_map.get("url")),
                "affiliateUrl": read_field(item, field_map.get("affiliateUrl")),
                "oldPrice": read_field(item, field_map.get("oldPrice")),
                "currentPrice": read_field(item, field_map.get("currentPrice")),
                "image": read_field(item, field_map.get("image")),
                "expiresAt": read_field(item, field_map.get("expiresAt")),
            }
        )

    record_source_status(feed_name, f"affiliate_feed_{feed_format}", True, len(normalized))
    return normalized


def load_feed_products(path: Path) -> list[dict]:
    products = []
    for feed in load_json_list(path):
        products.extend(fetch_feed_items(feed))
    return products


def normalize_image_url(url: str | None) -> str:
    if not url:
        return ""
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    return url


def fetch_mercadolivre_search(source: dict) -> list[dict]:
    if not source.get("enabled"):
        record_source_status(source.get("query", "Mercado Livre"), "mercadolivre_search", True, 0, "Fonte desativada.")
        return []

    query = str(source.get("query", "")).strip()
    if not query:
        record_source_status("Mercado Livre", "mercadolivre_search", False, 0, "Query vazia.")
        return []

    access_token = credential("MERCADOLIVRE_ACCESS_TOKEN")
    if not access_token:
        record_source_status(query, "mercadolivre_search", False, 0, "Configure MERCADOLIVRE_ACCESS_TOKEN.")
        return []

    limit = min(max(int(source.get("limit", 10)), 1), 50)
    url = "https://api.mercadolibre.com/sites/MLB/search?" + urlencode({"q": query, "limit": limit})
    headers = {
        "Accept": "application/json",
        "User-Agent": "MegaDescontosBot/1.0 (+https://mega-descontos.onrender.com)",
    }
    headers["Authorization"] = f"Bearer {access_token}"

    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        record_source_status(query, "mercadolivre_search", False, 0, str(error))
        return []

    items = payload.get("results", [])
    products = []

    for item in items:
        old_price = item.get("original_price")
        current_price = item.get("price")
        if not old_price or not current_price:
            continue

        products.append(
            {
                "id": f"mlb-{item.get('id')}",
                "title": item.get("title"),
                "store": source.get("store", "Mercado Livre"),
                "category": source.get("category", "Ofertas"),
                "url": item.get("permalink"),
                "oldPrice": old_price,
                "currentPrice": current_price,
                "image": normalize_image_url(item.get("thumbnail")),
                "expiresAt": source.get("expiresAt", ""),
                "sourceType": "mercadolivre_search",
            }
        )

    record_source_status(query, "mercadolivre_search", True, len(products))
    return products


def load_real_source_products(path: Path) -> list[dict]:
    products = []

    for source in load_json_list(path):
        source_type = source.get("type")
        try:
            if source_type == "mercadolivre_search":
                products.extend(fetch_mercadolivre_search(source))
            elif source_type == "mercadolivre_deals":
                deals = fetch_mercadolivre_deals(int(source.get("limit") or 24))
                for deal in deals:
                    deal["category"] = source.get("category", "Ofertas")
                    deal["sourceType"] = "mercadolivre_deals"
                products.extend(deals)
                record_source_status("Melhores ofertas", "mercadolivre_deals", True, len(deals))
            elif source_type == "json_feed":
                products.extend(fetch_feed_items(source))
        except Exception as error:
            record_source_status(source.get("query", source.get("name", "Fonte real")), str(source_type), False, 0, str(error))

    return products


def normalize_product(product: dict, minimum_discount: int) -> dict | None:
    if product.get("active") is False or is_expired(product.get("expiresAt")):
        return None

    old_price = parse_price(product["oldPrice"])
    current_price = parse_price(product["currentPrice"])
    discount = calculate_discount(old_price, current_price)

    if discount < minimum_discount:
        return None

    raw_id = product.get("id") or product.get("url") or product["title"]
    try:
        offer_id = int(raw_id)
    except (TypeError, ValueError):
        offer_id = int(hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:12], 16)

    affiliate_url = str(product.get("affiliateUrl") or "").strip()
    if not affiliate_url:
        affiliate_url = attach_affiliate_code(str(product["url"]).strip(), str(product["store"]).strip())

    offer = {
        "id": offer_id,
        "title": str(product["title"]).strip(),
        "store": str(product["store"]).strip(),
        "category": str(product["category"]).strip(),
        "oldPrice": old_price,
        "currentPrice": current_price,
        "discount": discount,
        "image": str(product["image"]).strip(),
        "affiliateUrl": affiliate_url,
        "expiresAt": product.get("expiresAt") or "",
        "foundAt": datetime.now(timezone.utc).isoformat(),
        "source": "discount_bot",
    }
    return offer if not validate_offer(offer) else None


def normalize_candidate(product: dict, minimum_discount: int) -> dict | None:
    if product.get("active") is False or is_expired(product.get("expiresAt")):
        return None

    try:
        old_price = parse_price(product["oldPrice"])
        current_price = parse_price(product["currentPrice"])
    except (KeyError, TypeError, ValueError):
        return None

    discount = calculate_discount(old_price, current_price)
    product_url = str(product.get("url") or "").strip()
    image_url = normalize_image_url(str(product.get("image") or "").strip())
    if discount < minimum_discount or not product_url.startswith("https://") or not image_url.startswith("https://"):
        return None

    raw_id = product.get("id") or product_url or product.get("title")
    candidate_id = int(hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:12], 16)
    return {
        "id": candidate_id,
        "sourceProductId": str(raw_id),
        "title": str(product.get("title") or "").strip(),
        "store": str(product.get("store") or "").strip(),
        "category": str(product.get("category") or "Ofertas").strip(),
        "oldPrice": old_price,
        "currentPrice": current_price,
        "discount": discount,
        "image": image_url,
        "productUrl": product_url,
        "discoveredAt": datetime.now(timezone.utc).isoformat(),
        "source": str(product.get("sourceType") or "product_discovery"),
    }


def get_candidates() -> list[dict]:
    return [dict(candidate) for candidate in LAST_CANDIDATES]


def load_existing_offers(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        return []
    return data


def remove_expired_offers(offers: list[dict]) -> list[dict]:
    return [offer for offer in offers if not is_expired(offer.get("expiresAt"))]


def merge_offers(existing: list[dict], generated: list[dict], purge_missing: bool = False) -> list[dict]:
    generated_by_id = {str(offer["id"]): offer for offer in generated if "id" in offer}

    if purge_missing:
        base = [
            offer for offer in existing
            if offer.get("source") != "discount_bot" or str(offer.get("id")) in generated_by_id
        ]
    else:
        base = existing

    merged = {str(offer["id"]): offer for offer in base if "id" in offer}
    merged.update(generated_by_id)
    return remove_expired_offers(list(merged.values()))


def generate_offers(
    input_path: Path,
    output_path: Path,
    db_path: Path,
    minimum_discount: int,
    purge_missing: bool = False,
    feeds_path: Path = DEFAULT_FEEDS,
    real_sources_path: Path = DEFAULT_REAL_SOURCES,
    status_path: Path = DEFAULT_STATUS,
    existing_offers: list[dict] | None = None,
    persist_db: bool = True,
) -> list[dict]:
    SOURCE_STATUS.clear()
    LAST_CANDIDATES.clear()
    products = (
        load_monitored_products(input_path)
        + load_feed_products(feeds_path)
        + load_real_source_products(real_sources_path)
    )
    offers = []

    for product in products:
        try:
            offer = normalize_product(product, minimum_discount)
        except (KeyError, TypeError, ValueError):
            continue
        if offer:
            offers.append(offer)
            continue

        candidate = normalize_candidate(product, minimum_discount)
        if candidate:
            LAST_CANDIDATES.append(candidate)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(offers, file, ensure_ascii=False, indent=2)

    current_offers = load_existing_offers(db_path) if existing_offers is None else existing_offers
    merged_offers = merge_offers(current_offers, offers, purge_missing=purge_missing)
    if persist_db:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with db_path.open("w", encoding="utf-8") as file:
            json.dump(merged_offers, file, ensure_ascii=False, indent=2)

    status_payload = {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "generatedOffers": len(offers),
        "candidateOffers": len(LAST_CANDIDATES),
        "rejectedOffers": max(len(products) - len(offers), 0),
        "totalPublished": len(merged_offers),
        "sources": SOURCE_STATUS,
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("w", encoding="utf-8") as file:
        json.dump(status_payload, file, ensure_ascii=False, indent=2)

    return offers


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica ofertas no Mega Descontos.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Arquivo JSON com produtos monitorados.")
    parser.add_argument("--feeds", default=str(DEFAULT_FEEDS), help="Feeds JSON autorizados.")
    parser.add_argument("--real-sources", default=str(DEFAULT_REAL_SOURCES), help="Fontes reais oficiais/autorizadas.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Arquivo JSON de saida com ofertas.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Arquivo de ofertas usado pelo site.")
    parser.add_argument("--status", default=str(DEFAULT_STATUS), help="Arquivo de status da ultima execucao.")
    parser.add_argument("--minimum-discount", type=int, default=15, help="Desconto minimo para publicar.")
    parser.add_argument("--purge-missing", action="store_true", help="Remove ofertas do bot que nao voltarem na rodada.")
    args = parser.parse_args()

    offers = generate_offers(
        Path(args.input),
        Path(args.output),
        Path(args.db),
        args.minimum_discount,
        purge_missing=args.purge_missing,
        feeds_path=Path(args.feeds),
        real_sources_path=Path(args.real_sources),
        status_path=Path(args.status),
    )
    print(f"{len(offers)} ofertas ativas geradas em {args.output}")
    print(f"Banco do site atualizado em {args.db}")


if __name__ == "__main__":
    main()
