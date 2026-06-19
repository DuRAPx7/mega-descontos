import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT_DIR / "bot" / "produtos_monitorados.json"
DEFAULT_FEEDS = ROOT_DIR / "bot" / "source_feeds.json"
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "ofertas_geradas.json"
DEFAULT_DB = ROOT_DIR / "data" / "offers_db.json"


@dataclass
class StoreConfig:
    affiliate_param: str
    affiliate_code: str


STORE_CONFIGS = {
    "Amazon": StoreConfig("tag", "SEU-CODIGO-AQUI"),
    "Shopee": StoreConfig("af_siteid", "SEU-CODIGO-AQUI"),
    "Mercado Livre": StoreConfig("matt_tool", "SEU-CODIGO-AQUI"),
    "Magalu": StoreConfig("partner_id", "SEU-CODIGO-AQUI"),
}


def calculate_discount(old_price: float, current_price: float) -> int:
    if old_price <= 0 or current_price >= old_price:
        return 0
    return round(((old_price - current_price) / old_price) * 100)


def attach_affiliate_code(url: str, store: str) -> str:
    config = STORE_CONFIGS.get(store)
    if not config:
        return url

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


def read_field(item: dict, dotted_path: str | None):
    if not dotted_path:
        return None

    current = item
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def fetch_feed_items(feed: dict) -> list[dict]:
    if not feed.get("enabled"):
        return []

    request = Request(feed["url"], headers={"User-Agent": "MegaDescontosBot/1.0"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    field_map = feed.get("fieldMap", {})
    normalized = []
    for index, item in enumerate(items):
        normalized.append(
            {
                "id": item.get("id") or f"{feed.get('name', 'feed')}-{index}",
                "title": read_field(item, field_map.get("title")),
                "store": feed.get("store") or read_field(item, field_map.get("store")),
                "category": feed.get("category") or read_field(item, field_map.get("category")),
                "url": read_field(item, field_map.get("url")),
                "oldPrice": read_field(item, field_map.get("oldPrice")),
                "currentPrice": read_field(item, field_map.get("currentPrice")),
                "image": read_field(item, field_map.get("image")),
                "expiresAt": read_field(item, field_map.get("expiresAt")),
            }
        )

    return normalized


def load_feed_products(path: Path) -> list[dict]:
    products = []
    for feed in load_json_list(path):
        products.extend(fetch_feed_items(feed))
    return products


def normalize_product(product: dict, minimum_discount: int) -> dict | None:
    if product.get("active") is False or is_expired(product.get("expiresAt")):
        return None

    old_price = float(product["oldPrice"])
    current_price = float(product["currentPrice"])
    discount = calculate_discount(old_price, current_price)

    if discount < minimum_discount:
        return None

    raw_id = product.get("id") or product.get("url") or product["title"]
    try:
        offer_id = int(raw_id)
    except (TypeError, ValueError):
        offer_id = int(hashlib.sha1(str(raw_id).encode("utf-8")).hexdigest()[:12], 16)

    return {
        "id": offer_id,
        "title": str(product["title"]).strip(),
        "store": str(product["store"]).strip(),
        "category": str(product["category"]).strip(),
        "oldPrice": old_price,
        "currentPrice": current_price,
        "discount": discount,
        "image": str(product["image"]).strip(),
        "affiliateUrl": attach_affiliate_code(str(product["url"]).strip(), str(product["store"]).strip()),
        "expiresAt": product.get("expiresAt") or "",
        "foundAt": datetime.now(timezone.utc).isoformat(),
        "source": "discount_bot",
    }


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
) -> list[dict]:
    products = load_json_list(input_path) + load_feed_products(feeds_path)
    offers = []

    for product in products:
        try:
            offer = normalize_product(product, minimum_discount)
        except (KeyError, TypeError, ValueError):
            continue
        if offer:
            offers.append(offer)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(offers, file, ensure_ascii=False, indent=2)

    existing_offers = load_existing_offers(db_path)
    merged_offers = merge_offers(existing_offers, offers, purge_missing=purge_missing)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with db_path.open("w", encoding="utf-8") as file:
        json.dump(merged_offers, file, ensure_ascii=False, indent=2)

    return offers


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica ofertas no Mega Descontos.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Arquivo JSON com produtos monitorados.")
    parser.add_argument("--feeds", default=str(DEFAULT_FEEDS), help="Feeds JSON autorizados.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Arquivo JSON de saida com ofertas.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Arquivo de ofertas usado pelo site.")
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
    )
    print(f"{len(offers)} ofertas ativas geradas em {args.output}")
    print(f"Banco do site atualizado em {args.db}")


if __name__ == "__main__":
    main()
