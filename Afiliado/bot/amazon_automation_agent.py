import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


DLL_DIRECTORY_HANDLE = None
if os.name == "nt" and hasattr(os, "add_dll_directory"):
    bundled_dlls = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/libheif/libheif/bin"
    )
    if bundled_dlls.exists():
        DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(bundled_dlls))

try:
    from bot.amazon_discovery_bot import (
        DEFAULT_SOURCES,
        api_request,
        discover_offers,
        publish_to_site,
        read_source_urls,
        write_csv,
    )
    from bot.mercadolivre_automation_agent import (
        CONFIG_PATH as ADMIN_CONFIG_PATH,
        authenticated_opener,
        browser_candidates,
        cdp_is_ready,
    )
except ImportError:
    from amazon_discovery_bot import (
        DEFAULT_SOURCES,
        api_request,
        discover_offers,
        publish_to_site,
        read_source_urls,
        write_csv,
    )
    from mercadolivre_automation_agent import (
        CONFIG_PATH as ADMIN_CONFIG_PATH,
        authenticated_opener,
        browser_candidates,
        cdp_is_ready,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "amazon_automation_agent.json"
PROFILE_DIR = ROOT_DIR / "browser-amazon-profile"
OUTPUT_PATH = ROOT_DIR / "bot" / "links_amazon_afiliados_gerados.csv"
AMAZON_DEALS_URL = "https://www.amazon.com.br/deals"
DEFAULT_ASSOCIATE_TAG = "megadesco0304-20"


def configure(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "associateTag": DEFAULT_ASSOCIATE_TAG,
                "cdpUrl": "http://127.0.0.1:9223",
                "pollSeconds": 15,
                "limit": 30,
                "scrolls": 8,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Agente Amazon configurado com a tag {DEFAULT_ASSOCIATE_TAG}.")


def load_config(path: Path) -> dict:
    if not ADMIN_CONFIG_PATH.exists():
        raise FileNotFoundError(
            "Configure primeiro o agente principal em atalhos/instalar_agente_mercado_livre.bat."
        )
    if not path.exists():
        configure(path)
    admin_config = json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8"))
    amazon_config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(admin_config, dict) or not isinstance(amazon_config, dict):
        raise ValueError("A configuracao dos agentes e invalida.")
    return {**admin_config, **amazon_config}


def ensure_browser(cdp_url: str) -> None:
    if cdp_is_ready(cdp_url):
        return
    browser = next((path for path in browser_candidates() if path.exists()), None)
    if not browser:
        raise RuntimeError("Brave, Chrome ou Edge nao foi encontrado.")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(browser),
            "--remote-debugging-port=9223",
            f"--user-data-dir={PROFILE_DIR}",
            AMAZON_DEALS_URL,
        ],
        close_fds=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if cdp_is_ready(cdp_url):
            return
        time.sleep(1)
    raise RuntimeError("O navegador Amazon abriu, mas o agente nao conseguiu se conectar.")


def update_status(opener, config: dict, state: str, message: str, processed: int = 0, failed: int = 0) -> None:
    api_request(
        opener,
        "POST",
        urljoin(config["siteUrl"].rstrip("/") + "/", "api/amazon-automation-agent/status"),
        {
            "state": state,
            "message": message,
            "processed": processed,
            "failed": failed,
            "clientUpdatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )


def process_job(config: dict) -> tuple[int, int]:
    opener = authenticated_opener(config)
    base_url = config["siteUrl"].rstrip("/") + "/"
    payload = api_request(opener, "GET", urljoin(base_url, "api/amazon-automation-agent/work"))
    job = payload.get("job") or {}
    if job.get("state") != "processing":
        update_status(opener, config, "idle", "Agente Amazon conectado e aguardando seu proximo clique.")
        return 0, 0

    cdp_url = str(config.get("cdpUrl") or "http://127.0.0.1:9223")
    ensure_browser(cdp_url)
    update_status(opener, config, "processing", "Buscando ofertas atuais na Amazon.")
    offers = discover_offers(
        read_source_urls(DEFAULT_SOURCES),
        cdp_url,
        str(config.get("associateTag") or DEFAULT_ASSOCIATE_TAG),
        max(1, min(int(job.get("target") or config.get("limit") or 30), 100)),
        max(1, int(config.get("scrolls") or 8)),
    )
    statuses = publish_to_site(
        config["siteUrl"],
        config["adminUsername"],
        config["adminPassword"],
        offers,
    )
    write_csv(OUTPUT_PATH, offers, statuses)
    processed = sum(status in {"publicado", "atualizado_existente"} for status in statuses)
    failed = len(statuses) - processed
    api_request(
        opener,
        "POST",
        urljoin(base_url, "api/amazon-automation-agent/job/complete"),
        {"jobId": job.get("id"), "state": "completed"},
    )
    update_status(
        opener,
        config,
        "completed",
        f"{processed} ofertas Amazon publicadas ou atualizadas; {failed} falharam.",
        processed,
        failed,
    )
    return processed, failed


def run_agent(config: dict, once: bool = False) -> None:
    poll_seconds = max(5, int(config.get("pollSeconds") or 15))
    print("Agente Amazon conectado ao Mega Descontos.")
    while True:
        try:
            process_job(config)
        except Exception as error:
            print(f"Falha na automacao Amazon: {error}")
            try:
                opener = authenticated_opener(config)
                update_status(opener, config, "error", str(error))
            except Exception:
                pass
        if once:
            return
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente local da automacao Amazon.")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config)
    if args.configure:
        configure(config_path)
        return
    run_agent(load_config(config_path), once=args.once)


if __name__ == "__main__":
    main()
