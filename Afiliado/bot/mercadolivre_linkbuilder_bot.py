import argparse
import csv
import json
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT_DIR / "bot" / "links_promocoes_potenciais.txt"
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "links_afiliados_gerados.csv"
LINKBUILDER_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"


def read_source_links(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {path}")

    links = []
    seen = set()
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames:
                preferred = [
                    "Product Link",
                    "product link",
                    "productUrl",
                    "produto_url",
                    "url",
                    "link",
                    "produto",
                    "product_url",
                    "Offer Link",
                ]
                field = next((name for name in preferred if name in reader.fieldnames), reader.fieldnames[0])
                for row in reader:
                    value = str(row.get(field) or "").strip()
                    if value and value not in seen:
                        links.append(value)
                        seen.add(value)
            else:
                file.seek(0)
                for row in csv.reader(file):
                    value = str(row[0] if row else "").strip()
                    if value and value not in seen:
                        links.append(value)
                        seen.add(value)
    else:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and value not in seen:
                links.append(value)
                seen.add(value)

    return [link for link in links if link.startswith("http")]


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def is_generated_affiliate_url(value: str, source_links: set[str]) -> bool:
    value = value.strip()
    if not value.startswith("http"):
        return False
    normalized = normalize_url(value)
    if normalized in source_links:
        return False

    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host == "meli.la" or (
        host.endswith("mercadolivre.com.br") and "/social/" in parsed.path
    )


def infer_category_from_url(product_url: str) -> str:
    text = product_url.lower()
    rules = [
        (
            "Celulares",
            [
                "celular",
                "smartphone",
                "iphone",
                "galaxy",
                "xiaomi",
                "motorola",
                "redmi",
                "poco",
                "realme",
            ],
        ),
        ("Eletronicos", ["fone", "headphone", "bluetooth", "caixa-de-som", "smartwatch", "tv-", "televisao"]),
        ("Informatica", ["notebook", "computador", "pc-", "monitor", "teclado", "mouse", "ssd", "impressora"]),
        ("Casa e Cozinha", ["cozinha", "air-fryer", "fritadeira", "cafeteira", "panela", "organizador"]),
        ("Beleza", ["maquiagem", "perfume", "shampoo", "creme", "beleza"]),
        ("Moda", ["camiseta", "blusa", "calca", "tenis", "moletom", "bolsa"]),
        ("Esportes", ["bike", "bicicleta", "halter", "academia", "fitness", "esporte"]),
        ("Livros", ["livro", "box-", "ebook"]),
        ("Brinquedos", ["brinquedo", "lego", "boneca", "carrinho"]),
        ("Automotivo", ["pneu", "carro", "moto", "automotivo"]),
        ("Ferramentas", ["furadeira", "parafusadeira", "ferramenta", "serra"]),
    ]
    for category, terms in rules:
        if any(term in text for term in terms):
            return category
    return "Ofertas"


def comparable_text(value: object) -> str:
    without_accents = unicodedata.normalize("NFKD", str(value or "").lower())
    without_accents = "".join(char for char in without_accents if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def title_tokens(value: object) -> set[str]:
    ignored = {
        "com",
        "sem",
        "para",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "novo",
        "original",
        "preto",
        "branco",
        "azul",
        "verde",
    }
    return {token for token in comparable_text(value).split() if len(token) > 2 and token not in ignored}


def parse_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    normalized = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if not normalized:
        return None
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def prices_are_close(left: object, right: object) -> bool:
    left_price = parse_float(left)
    right_price = parse_float(right)
    if left_price is None or right_price is None:
        return True
    if left_price == right_price:
        return True
    reference = max(left_price, right_price, 1)
    return abs(left_price - right_price) / reference <= 0.03


def titles_are_similar(left: object, right: object) -> bool:
    left_text = comparable_text(left)
    right_text = comparable_text(right)
    if not left_text or not right_text:
        return False
    if left_text == right_text or left_text in right_text or right_text in left_text:
        return True

    left_tokens = title_tokens(left_text)
    right_tokens = title_tokens(right_text)
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
        if overlap >= 0.72:
            return True

    return SequenceMatcher(None, left_text, right_text).ratio() >= 0.84


def find_existing_similar_offer(new_offer: dict, current_offers: list[dict]) -> dict | None:
    new_store = comparable_text(new_offer.get("store"))
    new_category = comparable_text(new_offer.get("category"))
    for offer in current_offers:
        if not isinstance(offer, dict):
            continue
        if str(offer.get("id") or "") == str(new_offer.get("id") or ""):
            return offer
        if comparable_text(offer.get("affiliateUrl")) == comparable_text(new_offer.get("affiliateUrl")):
            return offer
        if new_store and comparable_text(offer.get("store")) != new_store:
            continue

        offer_category = comparable_text(offer.get("category"))
        categories_match = not new_category or not offer_category or new_category == offer_category
        if not categories_match:
            continue
        if not prices_are_close(offer.get("currentPrice"), new_offer.get("currentPrice")):
            continue
        if titles_are_similar(offer.get("title"), new_offer.get("title")):
            return offer
    return None


def merge_duplicate_offer(existing_offer: dict, new_offer: dict) -> dict:
    merged = {**existing_offer, **new_offer}
    merged["id"] = existing_offer.get("id") or new_offer.get("id")
    if comparable_text(new_offer.get("category")) == "ofertas" and existing_offer.get("category"):
        merged["category"] = existing_offer["category"]
    return merged


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


def connect_to_linkbuilder(cdp_url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(
            "Instale as dependencias com: pip install -r requirements.txt"
        ) from error

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as error:
        playwright.stop()
        raise RuntimeError(
            "Nao consegui controlar o navegador. Abra o Mercado Livre usando "
            "abrir_gerador_mercado_livre.bat e tente novamente."
        ) from error
    pages = [page for context in browser.contexts for page in context.pages]
    page = next((item for item in pages if "mercadolivre.com.br/afiliados/linkbuilder" in item.url), None)
    if page is None:
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        page.goto(LINKBUILDER_URL, wait_until="domcontentloaded")
    return playwright, browser, page


def generate_affiliate_links(source_links: list[str], cdp_url: str, wait_seconds: int) -> list[str]:
    playwright, browser, page = connect_to_linkbuilder(cdp_url)
    try:
        page.bring_to_front()
        page.wait_for_selector("textarea", timeout=30_000)
        page.locator("textarea").first.fill("\n".join(source_links))

        button = page.get_by_role("button", name=re.compile("Gerar", re.IGNORECASE))
        button.click(timeout=15_000)

        source_set = {normalize_url(link) for link in source_links}
        deadline = time.time() + wait_seconds
        generated = []
        while time.time() < deadline:
            generated = collect_urls_from_page(page, source_set)
            if len(generated) >= len(source_links):
                break
            time.sleep(1)
        return generated
    finally:
        # Nao fechamos o navegador conectado por CDP para preservar o login e a pagina aberta.
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
            writer.writerow(
                {
                    "produto_url": product_url,
                    "link_afiliado": affiliate_url,
                    "status": status,
                }
            )


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
                urljoin(base_url, "api/mercadolivre/import-link"),
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

    merged = list(offers_by_id.values())
    api_request(opener, "PUT", urljoin(base_url, "api/offers"), merged)
    return statuses


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera links afiliados no Link Builder do Mercado Livre.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="TXT ou CSV com links de produtos, um por linha.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV de saida com produto_url e link_afiliado.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="URL CDP do navegador controlavel.")
    parser.add_argument("--wait-seconds", type=int, default=90, help="Tempo maximo aguardando os links gerados.")
    parser.add_argument("--publish-site", action="store_true", help="Publica no Mega Descontos depois de gerar.")
    parser.add_argument("--site-url", default=os.environ.get("SITE_URL", "http://127.0.0.1:8000"), help="URL do Mega Descontos.")
    parser.add_argument("--admin-user", default=os.environ.get("ADMIN_USERNAME", "admin"), help="Usuario admin.")
    parser.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD", "admin123"), help="Senha admin.")
    args = parser.parse_args()

    source_links = read_source_links(Path(args.input))
    if not source_links:
        raise SystemExit(f"Nenhum link encontrado em {args.input}")

    generated_links = generate_affiliate_links(source_links, args.cdp_url, args.wait_seconds)
    statuses = None
    if args.publish_site:
        statuses = publish_to_site(args.site_url, args.admin_user, args.admin_password, source_links, generated_links)

    write_csv(Path(args.output), source_links, generated_links, statuses)
    print(f"{len(generated_links)} links afiliados gerados.")
    print(f"CSV salvo em {args.output}")
    if args.publish_site:
        print("Publicacao no Mega Descontos concluida.")


if __name__ == "__main__":
    main()
