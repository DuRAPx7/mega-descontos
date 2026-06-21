import argparse
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "bot" / "links_shopee_promocoes_potenciais.txt"
DEFAULT_SOURCES = ROOT_DIR / "bot" / "shopee_discovery_sources.txt"
DEFAULT_SOURCE_URLS = [
    "https://affiliate.shopee.com.br/offer/product_offer",
    "https://affiliate.shopee.com.br/offer",
    "https://shopee.com.br/search?keyword=ofertas",
]


def is_shopee_host(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host == "shopee.com.br" or host.endswith(".shopee.com.br") or host == "shope.ee"


def is_probable_product_url(value: str) -> bool:
    if not is_shopee_host(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    text = f"{parsed.path}?{parsed.query}".lower()
    return bool(re.search(r"i\.\d+\.\d+|sp_atk=|itemid=|shopid=|-i\.", text))


def is_ready_affiliate_url(value: str) -> bool:
    if not is_shopee_host(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host == "shope.ee" or host == "s.shopee.com.br"


def read_source_urls(path: Path) -> list[str]:
    if not path.exists():
        path.write_text(
            "\n".join(["# Paginas onde o bot vai procurar produtos da Shopee.", *DEFAULT_SOURCE_URLS]) + "\n",
            encoding="utf-8",
        )
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#") and value.startswith("https://"):
            urls.append(value)
    return urls or DEFAULT_SOURCE_URLS


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
        raise RuntimeError("Nao consegui controlar o navegador. Abra a Shopee pelo .bat e tente novamente.") from error
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return playwright, context


def clean_candidate_url(value: str, base_url: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("/"):
        text = urljoin(base_url, text)
    cleaned = text.strip().rstrip(".,;)")
    if is_probable_product_url(cleaned) or is_ready_affiliate_url(cleaned):
        return cleaned
    return None


def collect_links_from_page(page, base_url: str) -> list[str]:
    raw_values = page.evaluate(
        """
        () => {
          const values = [];
          document.querySelectorAll("a[href]").forEach((node) => values.push(node.getAttribute("href")));
          document.querySelectorAll("[data-testid], [class], p, span, div").forEach((node) => {
            const text = node.innerText || node.textContent || "";
            if (text.includes("shopee.com.br") || text.includes("shope.ee")) values.push(text);
          });
          return values;
        }
        """
    )

    urls = []
    seen = set()
    url_pattern = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
    for value in raw_values:
        text = str(value or "").strip()
        candidates = url_pattern.findall(text)
        if text.startswith("/"):
            candidates.append(urljoin(base_url, text))
        elif text.startswith("https://"):
            candidates.append(text)
        for candidate in candidates:
            cleaned = clean_candidate_url(candidate, base_url)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                urls.append(cleaned)
    return urls


def click_product_offer_mass_links(page, limit: int) -> None:
    selected = page.evaluate(
        """
        (limit) => {
          const candidates = [...document.querySelectorAll("input[type='checkbox']")]
            .filter((box) => !box.disabled && box.offsetParent !== null);
          let total = 0;
          for (const box of candidates) {
            if (total >= limit) break;
            if (!box.checked) box.click();
            total += 1;
          }
          return total;
        }
        """,
        min(max(limit, 1), 100),
    )
    if not selected:
        return

    page.wait_for_timeout(700)
    clicked = page.evaluate(
        """
        () => {
          const words = ["obter link em massa", "obter link", "gerar link", "get link"];
          const nodes = [...document.querySelectorAll("button, [role='button'], a")];
          const target = nodes.reverse().find((node) => {
            if (node.disabled || node.getAttribute("aria-disabled") === "true") return false;
            const text = (node.innerText || node.textContent || "").toLowerCase().trim();
            return words.some((word) => text.includes(word));
          });
          if (!target) return false;
          target.click();
          return true;
        }
        """
    )
    if clicked:
        page.wait_for_timeout(3_000)


def discover_links(source_urls: list[str], cdp_url: str, limit: int, scrolls: int) -> list[str]:
    playwright, context = connect_browser(cdp_url)
    try:
        page = next((item for item in context.pages if "shopee" in item.url.lower()), None)
        if page is None:
            page = context.new_page()

        found = []
        seen = set()
        for source_url in source_urls:
            page.goto(source_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2_000)
            if "affiliate.shopee.com.br/offer/product_offer" in source_url:
                click_product_offer_mass_links(page, limit)
                for link in collect_links_from_page(page, source_url):
                    if link not in seen:
                        seen.add(link)
                        found.append(link)
                        if len(found) >= limit:
                            return found
            for _ in range(max(scrolls, 1)):
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(1_000)
                for link in collect_links_from_page(page, source_url):
                    if link not in seen:
                        seen.add(link)
                        found.append(link)
                        if len(found) >= limit:
                            return found
            for link in collect_links_from_page(page, source_url):
                if link not in seen:
                    seen.add(link)
                    found.append(link)
                    if len(found) >= limit:
                        return found
        return found
    finally:
        playwright.stop()


def write_links(path: Path, links: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# Links encontrados automaticamente pelo bot da Shopee.",
        "# Voce pode editar este arquivo antes de gerar os links afiliados.",
    ]
    path.write_text("\n".join([*header, *links]) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Busca links de produtos Shopee para conversao em afiliados.")
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES), help="TXT com paginas onde procurar produtos.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="TXT de saida com links de produtos.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="URL CDP do navegador controlavel.")
    parser.add_argument("--limit", type=int, default=25, help="Quantidade maxima de links para coletar.")
    parser.add_argument("--scrolls", type=int, default=8, help="Quantidade de rolagens em cada pagina.")
    args = parser.parse_args()

    source_urls = read_source_urls(Path(args.sources))
    links = discover_links(source_urls, args.cdp_url, max(args.limit, 1), max(args.scrolls, 1))
    write_links(Path(args.output), links)
    print(f"{len(links)} links de produtos Shopee salvos em {args.output}")
    if not links:
        raise SystemExit("Nenhum link de produto Shopee foi encontrado nas paginas configuradas.")


if __name__ == "__main__":
    main()
