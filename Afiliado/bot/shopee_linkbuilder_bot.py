import argparse
import csv
import json
import os
import re
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from mercadolivre_linkbuilder_bot import (
    find_existing_similar_offer,
    infer_category_from_text,
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
    return bool(re.search(r"/product/\d+/\d+|i\.\d+\.\d+|sp_atk=|itemid=|shopid=|-i\.", text))


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
    return is_ready_affiliate_url(value) and normalize_url(value) not in source_links


def collect_urls_from_page(page, source_links: set[str]) -> list[str]:
    url_pattern = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
    urls = []
    seen = set()
    for context in [page, *page.frames]:
        try:
            raw_values = context.evaluate(
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
        except Exception:
            continue
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
        try:
            page.goto(linkbuilder_url, wait_until="networkidle", timeout=60_000)
        except Exception:
            page.goto(linkbuilder_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3_000)
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
    deadline = time.time() + 45
    while time.time() < deadline:
        for context in [page, *page.frames]:
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    if locator.count():
                        locator.first.fill(joined_links, timeout=5_000)
                        return
                except Exception:
                    continue
        page.wait_for_timeout(1_000)
    raise RuntimeError("Nao encontrei o campo para colar os links na pagina da Shopee.")


def click_generate(page) -> None:
    button_names = ["Obter Link", "Obter link", "Gerar", "Converter", "Criar", "Generate", "Convert", "Create"]
    deadline = time.time() + 30
    while time.time() < deadline:
        for context in [page, *page.frames]:
            for name in button_names:
                try:
                    button = context.get_by_role("button", name=re.compile(name, re.IGNORECASE))
                    if button.count():
                        button.first.click(timeout=5_000)
                        return
                except Exception:
                    continue
            try:
                clicked = context.evaluate(
                    """
                    () => {
                      const words = ["obter link", "gerar", "converter", "criar", "generate", "convert", "create"];
                      const buttons = [...document.querySelectorAll("button, [role='button']")];
                      const target = buttons.find((button) => {
                        if (button.disabled || button.getAttribute("aria-disabled") === "true") return false;
                        const text = (button.innerText || button.textContent || "").toLowerCase();
                        return words.some((word) => text.includes(word));
                      });
                      if (!target) return false;
                      target.click();
                      return true;
                    }
                    """
                )
            except Exception:
                clicked = False
            if clicked:
                return
        page.wait_for_timeout(1_000)
    raise RuntimeError("Nao encontrei o botao de gerar/converter links na Shopee.")


def collect_urls_from_result(candidate, page, source_links: set[str]) -> tuple[list[str], object | None]:
    result_dialog = candidate.locator(
        "xpath=ancestor::*[@role='dialog' or "
        "contains(concat(' ', normalize-space(@class), ' '), ' ant-modal-content ')][1]"
    )
    if not result_dialog.count() or not result_dialog.first.is_visible():
        return collect_urls_from_page(page, source_links), None

    raw_values = result_dialog.first.evaluate(
        """
        (root) => {
          const values = [root.innerText || root.textContent || ""];
          root.querySelectorAll("a[href]").forEach((node) => values.push(node.href));
          root.querySelectorAll("input, textarea").forEach((node) => values.push(node.value || ""));
          return values;
        }
        """
    )
    url_pattern = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
    urls = []
    seen = set()
    for value in raw_values:
        for match in url_pattern.findall(str(value)):
            cleaned = match.strip().rstrip(".,;)")
            if is_generated_affiliate_url(cleaned, source_links) and cleaned not in seen:
                urls.append(cleaned)
                seen.add(cleaned)
    return urls, result_dialog.first


def dismiss_open_result_modal(page) -> None:
    for context in [page, *page.frames]:
        copy_buttons = context.get_by_role(
            "button", name=re.compile(r"^Copiar\s+Links?$", re.IGNORECASE)
        )
        if not any(copy_buttons.nth(index).is_visible() for index in range(copy_buttons.count())):
            continue
        close_buttons = context.locator("button.ant-modal-close:visible, button[aria-label='Close']:visible")
        if close_buttons.count():
            close_buttons.first.click(timeout=5_000)
            page.wait_for_timeout(500)
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return


def finish_generated_batch(page, source_links: set[str], expected_count: int, wait_seconds: int) -> list[str]:
    deadline = time.time() + wait_seconds
    generated = []
    copy_context = None
    copy_candidate = None
    result_dialog = None
    reported_count = -1
    print("  Aguardando a Shopee exibir os links afiliados do lote...")
    while time.time() < deadline:
        for context in [page, *page.frames]:
            copy_buttons = context.get_by_role(
                "button", name=re.compile(r"^Copiar\s+Links?$", re.IGNORECASE)
            )
            for index in range(copy_buttons.count()):
                candidate = copy_buttons.nth(index)
                if candidate.is_visible():
                    copy_context = context
                    copy_candidate = candidate
                    break
            if copy_candidate is not None:
                break
        if copy_candidate is not None:
            generated, result_dialog = collect_urls_from_result(copy_candidate, page, source_links)
            if len(generated) != reported_count:
                print(f"  Links validos encontrados: {len(generated)}/{expected_count}")
                reported_count = len(generated)
            if len(generated) >= expected_count:
                break
        page.wait_for_timeout(1_000)

    generated = generated[:expected_count]
    if len(generated) != expected_count:
        raise RuntimeError(
            f"A Shopee retornou {len(generated)} de {expected_count} links no lote atual."
        )

    if copy_context is None or copy_candidate is None:
        raise RuntimeError("Os links apareceram, mas nao encontrei o botao 'Copiar Link'.")
    copy_candidate.click(timeout=5_000)

    page.wait_for_timeout(700)
    visible_copy_button = copy_context.get_by_role(
        "button", name=re.compile(r"^Copiar\s+Links?$", re.IGNORECASE)
    )
    modal_is_open = (
        result_dialog is not None and result_dialog.is_visible()
    ) or any(visible_copy_button.nth(index).is_visible() for index in range(visible_copy_button.count()))
    if modal_is_open:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        modal_is_open = (
            result_dialog is not None and result_dialog.is_visible()
        ) or any(visible_copy_button.nth(index).is_visible() for index in range(visible_copy_button.count()))
    if modal_is_open:
        dialogs = copy_context.locator("[role='dialog']:visible, .ant-modal:visible, .shopee-modal:visible")
        for dialog_index in range(dialogs.count()):
            buttons = dialogs.nth(dialog_index).locator("button")
            for button_index in range(buttons.count()):
                button = buttons.nth(button_index)
                if button.is_visible() and "copiar" not in button.inner_text().strip().lower():
                    button.click(timeout=5_000)
                    page.wait_for_timeout(500)
                    modal_is_open = (
                        result_dialog is not None and result_dialog.is_visible()
                    ) or any(
                        visible_copy_button.nth(index).is_visible()
                        for index in range(visible_copy_button.count())
                    )
                    break
            if not modal_is_open:
                break
    if modal_is_open:
        raise RuntimeError("Copiei o lote, mas nao consegui fechar a janela de resultados da Shopee.")
    return generated


def generate_affiliate_links(
    source_links: list[str],
    cdp_url: str,
    linkbuilder_url: str,
    wait_seconds: int,
    batch_size: int,
    checkpoint_path: Path | None = None,
    initial_generated: list[str] | None = None,
) -> list[str]:
    playwright, page = connect_to_linkbuilder(cdp_url, linkbuilder_url)
    try:
        page.bring_to_front()
        all_generated = list(initial_generated or [])
        for start in range(len(all_generated), len(source_links), batch_size):
            batch = source_links[start:start + batch_size]
            batch_number = (start // batch_size) + 1
            total_batches = (len(source_links) + batch_size - 1) // batch_size
            print(f"Processando lote {batch_number}/{total_batches} ({len(batch)} links)...")
            dismiss_open_result_modal(page)
            fill_source_links(page, batch)
            click_generate(page)

            source_set = {normalize_url(link) for link in batch}
            generated = finish_generated_batch(page, source_set, len(batch), wait_seconds)
            all_generated.extend(generated)
            if checkpoint_path is not None:
                write_csv(checkpoint_path, source_links, all_generated)
            print(f"Lote {batch_number}/{total_batches} copiado e salvo.")
        return all_generated
    finally:
        playwright.stop()


def read_generated_checkpoint(output_path: Path, source_links: list[str]) -> list[str]:
    if not output_path.exists():
        return []
    try:
        with output_path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
    except (OSError, csv.Error):
        return []

    generated_by_source = {
        normalize_url(row.get("produto_url", "")): row.get("link_afiliado", "").strip()
        for row in rows
        if row.get("produto_url") and row.get("link_afiliado")
    }
    completed = []
    for source_link in source_links:
        affiliate_link = generated_by_source.get(normalize_url(source_link), "")
        if not is_ready_affiliate_url(affiliate_link):
            break
        completed.append(affiliate_link)
    return completed


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


def parse_brl_price(value: str) -> float | None:
    match = re.search(r"R\$\s*([\d.]+,\d{2})", value)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def collect_product_details(source_links: list[str], affiliate_links: list[str], cdp_url: str) -> list[dict | None]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("Instale as dependencias com: pip install -r requirements.txt") from error

    playwright = sync_playwright().start()
    details = []
    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        total = len(source_links)
        for index, source_link in enumerate(source_links):
            affiliate_link = affiliate_links[index] if index < len(affiliate_links) else ""
            print(f"Coletando dados do produto {index + 1}/{total}...")
            try:
                page.goto(source_link, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(3_000)
                raw = page.evaluate(
                    r"""
                    () => {
                      const visible = (node) => {
                        const style = getComputedStyle(node);
                        return style.display !== "none" && style.visibility !== "hidden";
                      };
                      const texts = [...document.querySelectorAll("div, span")]
                        .filter((node) => node.children.length === 0 && visible(node))
                        .map((node) => (node.innerText || node.textContent || "").trim());
                      return {
                        title: document.querySelector('meta[property="og:title"]')?.content || document.title || "",
                        image: document.querySelector('meta[property="og:image"]')?.content || "",
                        prices: texts.filter((text) => /^R\$\s*[\d.]+,\d{2}/.test(text)),
                        discounts: texts.filter((text) => /^-\d{1,2}%$/.test(text)),
                      };
                    }
                    """
                )
                current_price = parse_brl_price(raw.get("prices", [""])[0]) if raw.get("prices") else None
                old_price = parse_brl_price(raw.get("prices", ["", ""])[1]) if len(raw.get("prices", [])) > 1 else None
                if current_price and (not old_price or old_price <= current_price) and raw.get("discounts"):
                    discount = int(re.search(r"\d+", raw["discounts"][0]).group())
                    if 0 < discount < 100:
                        old_price = current_price / (1 - discount / 100)
                title = re.sub(r"\s*\|\s*Shopee.*$", "", str(raw.get("title") or "")).strip()
                image = str(raw.get("image") or "").strip()
                if not title or not image.startswith("https://") or not current_price or not old_price or old_price <= current_price:
                    raise ValueError("titulo, imagem ou precos nao foram encontrados na pagina")
                details.append(
                    {
                        "productUrl": source_link,
                        "affiliateUrl": affiliate_link,
                        "title": title,
                        "image": image,
                        "currentPrice": current_price,
                        "oldPrice": round(old_price, 2),
                        "category": infer_category_from_text(title, fallback=infer_category_from_url(source_link)),
                    }
                )
            except Exception as error:
                print(f"  Nao consegui coletar este produto: {error}")
                details.append(None)
        page.close()
    finally:
        playwright.stop()
    return details


def api_request(opener, method: str, url: str, payload: object | None = None) -> object:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=30) as response:
            text = response.read().decode("utf-8")
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(response_text).get("error") or response_text
        except json.JSONDecodeError:
            message = response_text
        raise RuntimeError(f"HTTP {error.code}: {message}") from error
    return json.loads(text) if text else {}


def publish_to_site(
    site_url: str,
    username: str,
    password: str,
    source_links: list[str],
    affiliate_links: list[str],
    product_details: list[dict | None],
) -> list[str]:
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
            detail_payload = product_details[index] if index < len(product_details) and product_details[index] else None
            mode = "dados completos" if detail_payload else "link afiliado"
            print(f"Publicando Shopee {index + 1}/{len(affiliate_links)} ({mode})...")
            payload = api_request(
                opener,
                "POST",
                urljoin(base_url, "api/shopee/import-link"),
                detail_payload if detail_payload else {
                    "affiliateUrl": affiliate_link,
                    "productUrl": source_link,
                    "category": infer_category_from_url(source_link),
                },
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
        checkpoint_links = read_generated_checkpoint(Path(args.output), product_links)
        if checkpoint_links:
            print(f"Retomando apos {len(checkpoint_links)} links ja salvos no CSV.")
        converted_links = generate_affiliate_links(
            product_links,
            args.cdp_url,
            args.linkbuilder_url,
            args.wait_seconds,
            batch_size,
            Path(args.output),
            checkpoint_links,
        )
    source_links = [*ready_links, *product_links]
    generated_links = [*ready_links, *converted_links]
    statuses = None
    if args.publish_site:
        product_details = collect_product_details(source_links, generated_links, args.cdp_url)
        statuses = publish_to_site(
            args.site_url,
            args.admin_user,
            args.admin_password,
            source_links,
            generated_links,
            product_details,
        )

    write_csv(Path(args.output), source_links, generated_links, statuses)
    print(f"{len(generated_links)} links afiliados Shopee gerados.")
    print(f"CSV salvo em {args.output}")
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
