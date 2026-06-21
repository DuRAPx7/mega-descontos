import argparse
import csv
import json
import os
import re
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from mercadolivre_linkbuilder_bot import (
    find_existing_similar_offer,
    infer_category_from_url,
    merge_duplicate_offer,
    read_source_links,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT_DIR / "bot" / "links_shopee_promocoes_potenciais.txt"
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "links_shopee_afiliados_gerados.csv"
DEFAULT_LINKBUILDER_URL = "https://affiliate.shopee.com.br/offer/custom_link"


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def is_shopee_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "shopee.com.br"
        or host.endswith(".shopee.com.br")
        or host == "shope.ee"
    )


def is_probable_product_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    text = f"{parsed.path}?{parsed.query}".lower()
    return bool(re.search(r"i\.\d+\.\d+|sp_atk=|itemid=|shopid=|-i\.", text))


def is_ready_affiliate_url(value: str) -> bool:
    if not is_shopee_url(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host == "shope.ee" or host == "s.shopee.com.br"


def is_generated_affiliate_url(value: str, source_links: set[str]) -> bool:
    if not is_shopee_url(value):
        return False
    normalized = normalize_url(value)
    return normalized not in source_links or is_ready_affiliate_url(value)


def collect_urls_from_page(page, source_links: set[str]) -> list[str]:
    url_pattern = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
    raw_values = page.evaluate(
        """
        () => {
          const values = [];
          document.querySelectorAll("a[href]").forEach((node) => values.push(node.href));
          document.querySelectorAll("input, textarea").forEach((node) => values.push(node.value || ""));
          document.querySelectorAll("[data-testid], [class], p, span, div").forEach((node) => {
            const text = node.innerText || node.textContent || "";
            if (text.includes("http")) values.push(text);
          });
          return values;
        }
        """
    )

    urls = []
    seen = set()
    for value in raw_values:
        for match in url_pattern.findall(str(value)):
            cleaned = match.strip().rstrip(".,;)")
            if is_generated_affiliate_url(cleaned, source_links) and cleaned not in seen:
                urls.append(cleaned)
                seen.add(cleaned)
    return urls


def connect_to_linkbuilder(cdp_url: str, linkbuilder_url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("Instale as dependencias com: pip install -r requirements.txt") from error

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as error:
        playwright.stop()
        raise RuntimeError(
            "Nao consegui controlar o navegador. Abra a Shopee usando "
            "abrir_gerador_shopee.bat e tente novamente."
        ) from error

    pages = [page for context in browser.contexts for page in context.pages]
    page = next((item for item in pages if "custom_link" in item.url.lower()), None)
    if page is None:
        page = next((item for item in pages if "shopee" in item.url.lower() and "affiliate" in item.url.lower()), None)
    if page is None:
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
    if "custom_link" not in page.url.lower():
        page.goto(linkbuilder_url, wait_until="domcontentloaded")
    return playwright, page


def fill_source_links(page, source_links: list[str]) -> None:
    joined_links = "\n".join(source_links)
    selectors = [
        "textarea",
        "input[placeholder*='URL' i]",
        "input[placeholder*='link' i]",
        "input[type='url']",
        "input[type='text']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count():
            locator.first.fill(joined_links)
            return
    raise RuntimeError("Nao encontrei o campo para colar os links na pagina da Shopee.")


def click_generate(page) -> None:
    button_names = ["Gerar", "Converter", "Criar", "Generate", "Convert", "Create"]
    for name in button_names:
        button = page.get_by_role("button", name=re.compile(name, re.IGNORECASE))
        if button.count():
            button.first.click(timeout=15_000)
            return
    clicked = page.evaluate(
        """
        () => {
          const words = ["gerar", "converter", "criar", "generate", "convert", "create"];
          const buttons = [...document.querySelectorAll("button, [role='button']")];
          const target = buttons.find((button) => {
            const text = (button.innerText || button.textContent || "").toLowerCase();
            return words.some((word) => text.includes(word));
          });
          if (!target) return false;
          target.click();
          return true;
        }
        """
    )
    if not clicked:
        raise RuntimeError("Nao encontrei o botao de gerar/converter links na Shopee.")


def generate_affiliate_links(source_links: list[str], cdp_url: str, linkbuilder_url: str, wait_seconds: int, batch_size: int) -> list[str]:
    playwright, page = connect_to_linkbuilder(cdp_url, linkbuilder_url)
    try:
        page.bring_to_front()
        all_generated = []
        for start in range(0, len(source_links), batch_size):
            batch = source_links[start:start + batch_size]
            fill_source_links(page, batch)
            click_generate(page)

            source_set = {normalize_url(link) for link in batch}
            deadline = time.time() + wait_seconds
            generated = []
            while time.time() < deadline:
                generated = collect_urls_from_page(page, source_set)
                if len(generated) >= len(batch):
                    break
                time.sleep(1)
            all_generated.extend(generated[:len(batch)])
        return all_generated
    finally:
        playwright.stop()


def write_csv(output_path: Path, source_links: list[str], generated_links: list[str], statuses: list[str] | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    statuses = statuses or []
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["produto_url", "link_afiliado", "status"])
        writer.writeheader()
        for index, product_url in enumerate(source_links):
            affiliate_url = generated_links[index] if index < len(generated_links) else ""
            status = statuses[index] if index < len(statuses) else ("gerado" if affiliate_url else "nao_gerado")
            writer.writerow({"produto_url": product_url, "link_afiliado": affiliate_url, "status": status})


def api_request(opener, method: str, url: str, payload: object | None = None) -> object:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with opener.open(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    return json.loads(text) if text else {}


def publish_to_site(site_url: str, username: str, password: str, source_links: list[str], affiliate_links: list[str]) -> list[str]:
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
    for index, affiliate_link in enumerate(affiliate_links):
        if not affiliate_link:
            statuses.append("nao_gerado")
            continue
        try:
            source_link = source_links[index] if index < len(source_links) else ""
            payload = api_request(
                opener,
                "POST",
                urljoin(base_url, "api/shopee/import-link"),
                {"affiliateUrl": affiliate_link, "category": infer_category_from_url(source_link)},
            )
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera links afiliados no painel da Shopee.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="TXT ou CSV com links de produtos Shopee.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV de saida com links afiliados.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="URL CDP do navegador controlavel.")
    parser.add_argument("--linkbuilder-url", default=os.environ.get("SHOPEE_LINKBUILDER_URL", DEFAULT_LINKBUILDER_URL))
    parser.add_argument("--wait-seconds", type=int, default=90, help="Tempo maximo aguardando os links gerados.")
    parser.add_argument("--batch-size", type=int, default=5, help="Quantidade de links por envio. A Shopee aceita ate 5.")
    parser.add_argument("--publish-site", action="store_true", help="Publica no Mega Descontos depois de gerar.")
    parser.add_argument("--site-url", default=os.environ.get("SITE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--admin-user", default=os.environ.get("ADMIN_USERNAME", "admin"))
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD", "admin123"))
    args = parser.parse_args()

    discovered_links = [
        link
        for link in read_source_links(Path(args.input))
        if not link.lstrip().startswith("#") and is_shopee_url(link)
    ]
    ready_links = [link for link in discovered_links if is_ready_affiliate_url(link)]
    product_links = [
        link
        for link in discovered_links
        if not is_ready_affiliate_url(link) and is_probable_product_url(link)
    ]
    if not ready_links and not product_links:
        raise SystemExit(f"Nenhum link da Shopee encontrado em {args.input}")

    batch_size = max(1, min(args.batch_size, 5))
    converted_links = []
    if product_links:
        converted_links = generate_affiliate_links(product_links, args.cdp_url, args.linkbuilder_url, args.wait_seconds, batch_size)
    source_links = [*ready_links, *product_links]
    generated_links = [*ready_links, *converted_links]
    statuses = None
    if args.publish_site:
        statuses = publish_to_site(args.site_url, args.admin_user, args.admin_password, source_links, generated_links)

    write_csv(Path(args.output), source_links, generated_links, statuses)
    print(f"{len(generated_links)} links afiliados Shopee gerados.")
    print(f"CSV salvo em {args.output}")
    if args.publish_site:
        print("Publicacao no Mega Descontos concluida.")


if __name__ == "__main__":
    main()
