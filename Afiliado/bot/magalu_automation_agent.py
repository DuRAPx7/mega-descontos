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
    from bot.amazon_discovery_bot import api_request
    from bot.magalu_discovery_bot import DEFAULT_OUTPUT, discover_offers, is_influencer_store_url, publish_to_site, write_csv
    from bot.mercadolivre_automation_agent import (
        CONFIG_PATH as ADMIN_CONFIG_PATH,
        authenticated_opener,
        browser_candidates,
        cdp_is_ready,
    )
except ImportError:
    from amazon_discovery_bot import api_request
    from magalu_discovery_bot import DEFAULT_OUTPUT, discover_offers, is_influencer_store_url, publish_to_site, write_csv
    from mercadolivre_automation_agent import (
        CONFIG_PATH as ADMIN_CONFIG_PATH,
        authenticated_opener,
        browser_candidates,
        cdp_is_ready,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "magalu_automation_agent.json"
PROFILE_DIR = ROOT_DIR / "browser-magalu-profile"


def configure(path: Path) -> None:
    current = {}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    store_url = str(current.get("storeUrl") or "").strip()
    while not is_influencer_store_url(store_url):
        store_url = input("Cole o endereco da sua loja do Influenciador Magalu: ").strip()
        if not is_influencer_store_url(store_url):
            print("Use um endereco como https://www.magazinevoce.com.br/sualoja/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "storeUrl": store_url,
                "cdpUrl": "http://127.0.0.1:9224",
                "pollSeconds": 15,
                "limit": 30,
                "scrolls": 10,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Agente Magalu configurado.")


def load_config(path: Path) -> dict:
    if not ADMIN_CONFIG_PATH.exists():
        raise FileNotFoundError("Configure primeiro a automacao completa.")
    if not path.exists():
        configure(path)
    return {
        **json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8")),
        **json.loads(path.read_text(encoding="utf-8")),
    }


def ensure_browser(config: dict) -> None:
    cdp_url = str(config.get("cdpUrl") or "http://127.0.0.1:9224")
    if cdp_is_ready(cdp_url):
        return
    browser = next((path for path in browser_candidates() if path.exists()), None)
    if not browser:
        raise RuntimeError("Brave, Chrome ou Edge nao foi encontrado.")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(browser),
            "--remote-debugging-port=9224",
            f"--user-data-dir={PROFILE_DIR}",
            str(config["storeUrl"]),
        ],
        close_fds=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if cdp_is_ready(cdp_url):
            return
        time.sleep(1)
    raise RuntimeError("O navegador Magalu abriu, mas o agente nao conseguiu se conectar.")


def update_status(opener, config: dict, state: str, message: str, processed: int = 0, failed: int = 0) -> None:
    api_request(
        opener,
        "POST",
        urljoin(config["siteUrl"].rstrip("/") + "/", "api/magalu-automation-agent/status"),
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
    payload = api_request(opener, "GET", urljoin(base_url, "api/magalu-automation-agent/work"))
    job = payload.get("job") or {}
    if job.get("state") != "processing":
        update_status(opener, config, "idle", "Agente Magalu conectado e aguardando seu proximo clique.")
        return 0, 0

    ensure_browser(config)
    update_status(opener, config, "processing", "Buscando ofertas atuais na sua loja Magalu.")
    offers = discover_offers(
        str(config["storeUrl"]),
        str(config.get("cdpUrl") or "http://127.0.0.1:9224"),
        max(1, min(int(job.get("target") or config.get("limit") or 30), 100)),
        max(1, int(config.get("scrolls") or 10)),
    )
    statuses = publish_to_site(config["siteUrl"], config["adminUsername"], config["adminPassword"], offers)
    write_csv(DEFAULT_OUTPUT, offers, statuses)
    processed = sum(status in {"publicado", "atualizado_existente"} for status in statuses)
    failed = len(statuses) - processed
    api_request(
        opener,
        "POST",
        urljoin(base_url, "api/magalu-automation-agent/job/complete"),
        {"jobId": job.get("id"), "state": "completed"},
    )
    update_status(
        opener,
        config,
        "completed",
        f"{processed} ofertas Magalu publicadas ou atualizadas; {failed} falharam.",
        processed,
        failed,
    )
    return processed, failed


def run_agent(config: dict, once: bool = False) -> None:
    poll_seconds = max(5, int(config.get("pollSeconds") or 15))
    print("Agente Magalu conectado ao Mega Descontos.")
    while True:
        try:
            process_job(config)
        except Exception as error:
            print(f"Falha na automacao Magalu: {error}")
            try:
                update_status(authenticated_opener(config), config, "error", str(error))
            except Exception:
                pass
        if once:
            return
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente local da automacao Magalu.")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config)
    if args.configure:
        configure(config_path)
    else:
        run_agent(load_config(config_path), once=args.once)


if __name__ == "__main__":
    main()
