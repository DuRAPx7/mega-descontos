import argparse
import csv
import json
import os
import re
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from mercadolivre_linkbuilder_bot import (
    find_existing_similar_offer,
    infer_category_from_text,
    merge_duplicate_offer,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT_DIR / "bot" / "amazon_discovery_sources.txt"
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "links_amazon_afiliados_gerados.csv"
DEFAULT_SOURCE_URLS = [
    "https://www.amazon.com.br/deals",
    "https://www.amazon.com.br/gp/goldbox",
    "https://www.amazon.com.br/s?k=ofertas",
]


def read_source_urls(path: Path) -> list[str]:
    if not path.exists():
        path.write_text(
            "\n".join(["# Paginas onde o bot vai procurar ofertas da Amazon.", *DEFAULT_SOURCE_URLS]) + "\n",
            encoding="utf-8",
        )
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#") and value.startswith("https://"):
            urls.append(value)
    return urls or DEFAULT_SOURCE_URLS


def parse_brl_price(value: str) -> float | None:
    match = re.search(r"R\$\s*([\d.]+,\d{2})", value or "")
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def calculate_old_price(current_price: float, discount: int | None, prices: list[float]) -> float | None:
    for price in prices:
        if price > current_price:
            return price
    if discount and 0 < discount < 95:
        return round(current_price / (1 - discount / 100), 2)
    return None


def extract_asin(url: str) -> str:
    parsed = urlparse(url)
    for pattern in (r"/(?:dp|gp/product|product)/([A-Z0-9]{10})", r"/([A-Z0-9]{10})(?:[/?]|$)"):
        match = re.search(pattern, parsed.path, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() == "asin" and re.fullmatch(r"[A-Z0-9]{10}", value, re.IGNORECASE):
            return value.upper()
    return ""


def normalize_product_url(url: str, base_url: str) -> str:
    product_url = urljoin(base_url, url)
    parsed = urlparse(product_url)
    asin = extract_asin(product_url)
    if asin:
        return f"https://www.amazon.com.br/dp/{asin}"
    return urlunparse(parsed._replace(fragment=""))


def attach_amazon_tag(url: str, associate_tag: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if associate_tag:
        query["tag"] = associate_tag
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def is_probable_product_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return "amazon." in host and bool(extract_asin(url))


def connect_browser(cdp_url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("Instale as dependencias com: pip install -r requirements.txt") from error

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as error:
        playwright.stop()
        raise RuntimeError("Nao consegui controlar o navegador da Amazon. Abra pelo .bat e tente novamente.") from error
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return playwright, context


def collect_offers_from_page(page, source_url: str, associate_tag: str, limit: int) -> list[dict]:
    raw_items = page.evaluate(
        r"""
        () => {
          const visible = (node) => {
            const style = getComputedStyle(node);
            const box = node.getBoundingClientRect();
            return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
          };
          const anchors = [...document.querySelectorAll("a[href]")].filter((anchor) => {
            const href = anchor.href || "";
            return /\/(dp|gp\/product)\//i.test(href) && visible(anchor);
          });
          return anchors.map((anchor) => {
            let card = anchor;
            for (let depth = 0; card && depth < 8; depth += 1, card = card.parentElement) {
              const text = card.innerText || "";
              if ((text.match(/R\$\s*[\d.]+,\d{2}/g) || []).length || /-\d{1,2}%/.test(text)) break;
            }
            card = card || anchor;
            const image = card.querySelector("img") || anchor.querySelector("img");
            const titleCandidates = [
              anchor.getAttribute("aria-label"),
              image?.getAttribute("alt"),
              card.querySelector("h2")?.innerText,
              card.querySelector("[data-cy='title-recipe']")?.innerText,
              anchor.innerText,
            ].filter(Boolean);
            const text = card.innerText || anchor.innerText || "";
            return {
              url: anchor.href,
              title: titleCandidates[0] || "",
              image: image?.currentSrc || image?.src || "",
              text,
              prices: [...new Set(text.match(/R\$\s*[\d.]+,\d{2}/g) || [])],
              discounts: [...new Set(text.match(/-\d{1,2}%/g) || [])],
            };
          });
        }
        """
    )

    offers = []
    seen = set()
    for raw in raw_items:
        product_url = normalize_product_url(str(raw.get("url") or ""), source_url)
        asin = extract_asin(product_url)
        if not asin or product_url in seen:
            continue

        prices = [
            price
            for price in (parse_brl_price(price_text) for price_text in raw.get("prices", []))
            if price is not None
        ]
        if not prices:
            continue
        current_price = min(prices)
        discount_match = re.search(r"\d+", str(raw.get("discounts", [""])[0] if raw.get("discounts") else ""))
        discount = int(discount_match.group()) if discount_match else None
        old_price = calculate_old_price(current_price, discount, sorted(prices, reverse=True))
        if not old_price or old_price <= current_price:
            continue

        title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip(" -")
        image = str(raw.get("image") or "").strip()
        if not title or not image.startswith("https://"):
            continue

        seen.add(product_url)
        offers.append(
            {
                "productUrl": product_url,
                "affiliateUrl": attach_amazon_tag(product_url, associate_tag),
                "title": title,
                "store": "Amazon",
                "category": infer_category_from_text(title, fallback="Ofertas"),
                "oldPrice": round(old_price, 2),
                "currentPrice": round(current_price, 2),
                "image": image,
                "sourceProductId": asin,
            }
        )
        if len(offers) >= limit:
            break
    return offers


def discover_offers(source_urls: list[str], cdp_url: str, associate_tag: str, limit: int, scrolls: int) -> list[dict]:
    playwright, context = connect_browser(cdp_url)
    try:
        page = next((item for item in context.pages if "amazon." in item.url.lower()), None)
        if page is None:
            page = context.new_page()

        offers = []
        seen = set()
        for source_url in source_urls:
            print(f"Buscando ofertas em {source_url}...")
            page.goto(source_url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_load_state("networkidle", timeout=12_000)
            except Exception:
                pass
            page.wait_for_timeout(2_000)
            for _ in range(max(scrolls, 1)):
                for offer in collect_offers_from_page(page, source_url, associate_tag, limit - len(offers)):
                    key = offer["sourceProductId"]
                    if key not in seen:
                        seen.add(key)
                        offers.append(offer)
                        print(f"  {len(offers)}. {offer['title'][:70]} - R$ {offer['currentPrice']:.2f}")
                        if len(offers) >= limit:
                            return offers
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(1_200)
        return offers
    finally:
        playwright.stop()


def api_request(opener, method: str, url: str, payload: object | None = None) -> object:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=35) as response:
            text = response.read().decode("utf-8")
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(response_text).get("error") or response_text
        except json.JSONDecodeError:
            message = response_text
        raise RuntimeError(f"HTTP {error.code}: {message}") from error
    return json.loads(text) if text else {}


def publish_to_site(site_url: str, username: str, password: str, offers: list[dict]) -> list[str]:
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    base_url = site_url.rstrip("/") + "/"
    api_request(opener, "POST", urljoin(base_url, "api/login"), {"username": username, "password": password})
    offers_payload = api_request(opener, "GET", urljoin(base_url, "api/offers"))
    current_offers = offers_payload.get("offers", offers_payload if isinstance(offers_payload, list) else [])
    if not isinstance(current_offers, list):
        current_offers = []

    statuses = []
    offers_by_id = {str(offer.get("id")): offer for offer in current_offers if isinstance(offer, dict)}
    for index, product in enumerate(offers):
        try:
            print(f"Publicando Amazon {index + 1}/{len(offers)}...")
            payload = api_request(opener, "POST", urljoin(base_url, "api/amazon/import-link"), product)
            offer = payload.get("offer")
            if not isinstance(offer, dict):
                raise ValueError("Resposta sem oferta.")
            duplicate = find_existing_similar_offer(offer, list(offers_by_id.values()))
            if duplicate:
                merged_offer = merge_duplicate_offer(duplicate, offer)
                offers_by_id[str(merged_offer.get("id"))] = merged_offer
                if str(duplicate.get("id")) != str(merged_offer.get("id")):
                    offers_by_id.pop(str(duplicate.get("id")), None)
                statuses.append("atualizado_existente")
            else:
                offers_by_id[str(offer.get("id"))] = offer
                statuses.append("publicado")
        except Exception as error:
            statuses.append(f"erro_publicar: {error}")

    api_request(opener, "PUT", urljoin(base_url, "api/offers"), list(offers_by_id.values()))
    return statuses


def send_to_review(site_url: str, username: str, password: str, offers: list[dict]) -> list[str]:
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    base_url = site_url.rstrip("/") + "/"
    api_request(opener, "POST", urljoin(base_url, "api/login"), {"username": username, "password": password})
    api_request(opener, "POST", urljoin(base_url, "api/review-offers"), {"offers": offers})
    return ["em_revisao" for _ in offers]


def write_csv(output_path: Path, offers: list[dict], statuses: list[str] | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    statuses = statuses or []
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        fieldnames = ["produto_url", "link_afiliado", "titulo", "categoria", "preco_antigo", "preco_atual", "status"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for index, offer in enumerate(offers):
            writer.writerow(
                {
                    "produto_url": offer.get("productUrl", ""),
                    "link_afiliado": offer.get("affiliateUrl", ""),
                    "titulo": offer.get("title", ""),
                    "categoria": offer.get("category", ""),
                    "preco_antigo": offer.get("oldPrice", ""),
                    "preco_atual": offer.get("currentPrice", ""),
                    "status": statuses[index] if index < len(statuses) else "gerado",
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca ofertas da Amazon e publica no Mega Descontos.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES), help="TXT com paginas Amazon onde procurar ofertas.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV de saida com ofertas coletadas.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="URL CDP do navegador controlavel.")
    parser.add_argument("--limit", type=int, default=24, help="Quantidade maxima de ofertas.")
    parser.add_argument("--scrolls", type=int, default=6, help="Quantidade de rolagens por pagina.")
    parser.add_argument("--associate-tag", default=os.environ.get("AMAZON_ASSOCIATE_TAG", ""), help="Tag Amazon Associados.")
    parser.add_argument("--publish-site", action="store_true", help="Publica no Mega Descontos.")
    parser.add_argument("--review-site", action="store_true", help="Envia para a fila de revisao do Mega Descontos.")
    parser.add_argument("--site-url", default=os.environ.get("SITE_URL", "http://127.0.0.1:8000"), help="URL do Mega Descontos.")
    parser.add_argument("--admin-user", default=os.environ.get("ADMIN_USERNAME", "admin"), help="Usuario admin.")
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD", "admin123"), help="Senha admin.")
    args = parser.parse_args()

    if not args.associate_tag:
        raise SystemExit("Configure AMAZON_ASSOCIATE_TAG ou informe --associate-tag.")

    source_urls = read_source_urls(Path(args.sources))
    offers = discover_offers(source_urls, args.cdp_url, args.associate_tag, max(args.limit, 1), max(args.scrolls, 1))
    statuses = None
    if args.review_site:
        statuses = send_to_review(args.site_url, args.admin_user, args.admin_password, offers)
    elif args.publish_site:
        statuses = publish_to_site(args.site_url, args.admin_user, args.admin_password, offers)
    write_csv(Path(args.output), offers, statuses)
    print(f"{len(offers)} ofertas Amazon salvas em {args.output}")
    if args.review_site:
        print("Ofertas enviadas para a fila de revisao.")
    if args.publish_site:
        failed = [status for status in statuses or [] if status.startswith("erro_")]
        if failed:
            print(f"Publicacao incompleta: {len(failed)} produto(s) rejeitado(s).")
            for status in failed:
                print(f"  {status}")
            raise SystemExit(1)
        print("Publicacao no Mega Descontos concluida.")


if __name__ == "__main__":
    main()
