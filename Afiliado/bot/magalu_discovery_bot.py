import csv
import json
import re
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, build_opener

try:
    from bot.amazon_discovery_bot import api_request, calculate_old_price, parse_brl_price
    from bot.mercadolivre_linkbuilder_bot import infer_category_from_text
except ImportError:
    from amazon_discovery_bot import api_request, calculate_old_price, parse_brl_price
    from mercadolivre_linkbuilder_bot import infer_category_from_text


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "links_magalu_afiliados_gerados.csv"
BRL_PRICE_PATTERN = r"R\$\s*[\d.]+,\d{2}"


def is_influencer_store_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    return parsed.scheme == "https" and host in {
        "magazinevoce.com.br",
        "www.magazinevoce.com.br",
    } and bool(path_parts)


def is_influencer_product_url(value: str) -> bool:
    if not is_influencer_store_url(value):
        return False
    return "/p/" in urlparse(value).path.lower()


def product_code(value: str) -> str:
    match = re.search(r"/p/([^/?#]+)", urlparse(value).path, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def extract_magalu_prices(text: str, discount: int | None = None) -> tuple[float | None, float | None]:
    normalized = re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()
    if not normalized:
        return None, None

    installment_pattern = (
        rf"\b\d{{1,2}}\s*(?:x|vez(?:es)?)\s*(?:de\s*)?{BRL_PRICE_PATTERN}"
    )
    without_installments = re.sub(
        installment_pattern,
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    pix_labels = re.findall(
        rf"({BRL_PRICE_PATTERN})\s*(?:no\s*)?pix\b",
        without_installments,
        flags=re.IGNORECASE,
    )
    pix_prices = [
        price for price in (parse_brl_price(label) for label in pix_labels)
        if price is not None
    ]
    cash_prices = [
        price
        for price in (
            parse_brl_price(label)
            for label in re.findall(BRL_PRICE_PATTERN, without_installments, flags=re.IGNORECASE)
        )
        if price is not None
    ]

    current_price = min(pix_prices) if pix_prices else (min(cash_prices) if cash_prices else None)
    if current_price is None:
        return None, None
    old_price = calculate_old_price(current_price, discount, sorted(cash_prices, reverse=True))
    return current_price, old_price


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
        raise RuntimeError("Nao consegui controlar o navegador do Magalu.") from error
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return playwright, context


def collect_offers_from_page(page, limit: int) -> list[dict]:
    raw_items = page.evaluate(
        r"""
        () => [...document.querySelectorAll('a[href*="/p/"]')].map((anchor) => {
          let card = anchor;
          for (let depth = 0; card && depth < 8; depth += 1, card = card.parentElement) {
            const text = card.innerText || "";
            if (/R\$\s*[\d.]+,\d{2}/.test(text)) break;
          }
          card = card || anchor;
          const image = card.querySelector("img") || anchor.querySelector("img");
          const titleNode = card.querySelector("h2, h3, [data-testid*='title'], [class*='title']");
          return {
            url: anchor.href,
            title: titleNode?.innerText || image?.alt || anchor.innerText || "",
            image: image?.currentSrc || image?.src || "",
            text: card.innerText || anchor.innerText || "",
            prices: [...new Set((card.innerText || "").match(/R\$\s*[\d.]+,\d{2}/g) || [])],
            discounts: [...new Set((card.innerText || "").match(/\d{1,2}%\s*(?:de\s*)?desconto/gi) || [])],
          };
        })
        """
    )

    offers = []
    seen = set()
    for raw in raw_items:
        affiliate_url = str(raw.get("url") or "").split("#", 1)[0]
        code = product_code(affiliate_url)
        if not code or code in seen or not is_influencer_product_url(affiliate_url):
            continue
        discount_match = re.search(r"\d+", " ".join(raw.get("discounts", [])))
        discount = int(discount_match.group()) if discount_match else None
        current_price, old_price = extract_magalu_prices(str(raw.get("text") or ""), discount)
        if current_price is None:
            continue
        title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip(" -")
        image = str(raw.get("image") or "").strip()
        if not old_price or old_price <= current_price or len(title) < 8 or not image.startswith("https://"):
            continue
        seen.add(code)
        offers.append(
            {
                "sourceProductId": code,
                "productUrl": affiliate_url,
                "affiliateUrl": affiliate_url,
                "title": title,
                "store": "Magalu",
                "category": infer_category_from_text(title, fallback="Ofertas"),
                "oldPrice": round(old_price, 2),
                "currentPrice": round(current_price, 2),
                "image": image,
            }
        )
        if len(offers) >= limit:
            break
    return offers


def discover_offers(store_url: str, cdp_url: str, limit: int, scrolls: int) -> list[dict]:
    if not is_influencer_store_url(store_url):
        raise ValueError("Informe o endereco da sua loja do Influenciador Magalu.")
    playwright, context = connect_browser(cdp_url)
    try:
        page = next((item for item in context.pages if "magazinevoce.com.br" in item.url.lower()), None)
        if page is None:
            page = context.new_page()
        page.goto(store_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        offers = []
        seen = set()
        for _ in range(max(1, scrolls)):
            for offer in collect_offers_from_page(page, limit - len(offers)):
                if offer["sourceProductId"] not in seen:
                    seen.add(offer["sourceProductId"])
                    offers.append(offer)
            if len(offers) >= limit:
                break
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1_000)
        return offers
    finally:
        playwright.stop()


def publish_to_site(site_url: str, username: str, password: str, offers: list[dict]) -> list[str]:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base_url = site_url.rstrip("/") + "/"
    api_request(opener, "POST", urljoin(base_url, "api/login"), {"username": username, "password": password})
    statuses = []
    for product in offers:
        try:
            payload = api_request(opener, "POST", urljoin(base_url, "api/magalu/import-link"), product)
            statuses.append("publicado" if payload.get("created") else "atualizado_existente")
        except Exception as error:
            statuses.append(f"erro_publicar: {error}")
    return statuses


def write_csv(output_path: Path, offers: list[dict], statuses: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["produto_url", "link_afiliado", "titulo", "preco_antigo", "preco_atual", "status"],
        )
        writer.writeheader()
        for index, offer in enumerate(offers):
            writer.writerow(
                {
                    "produto_url": offer["productUrl"],
                    "link_afiliado": offer["affiliateUrl"],
                    "titulo": offer["title"],
                    "preco_antigo": offer["oldPrice"],
                    "preco_atual": offer["currentPrice"],
                    "status": statuses[index] if index < len(statuses) else "gerado",
                }
            )
