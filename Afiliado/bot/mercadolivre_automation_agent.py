import argparse
import getpass
import json
import os
import subprocess
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, build_opener, urlopen

try:
    from bot.mercadolivre_linkbuilder_bot import (
        LINKBUILDER_URL,
        api_request,
        generate_affiliate_links,
        publish_to_site,
    )
except ImportError:
    from mercadolivre_linkbuilder_bot import (
        LINKBUILDER_URL,
        api_request,
        generate_affiliate_links,
        publish_to_site,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "automation_agent.json"
PROFILE_DIR = ROOT_DIR / "browser-ml-profile"
DEFAULT_SITE_URL = "https://mega-descontos.onrender.com"


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Configuracao ausente em {path}. Execute o agente com --configure."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("A configuracao do agente e invalida.")
    return payload


def configure(path: Path) -> None:
    try:
        site_url = input(f"Site [{DEFAULT_SITE_URL}]: ").strip() or DEFAULT_SITE_URL
        username = input("Usuario administrador: ").strip()
        password = getpass.getpass("Senha administrador: ")
    except (EOFError, KeyboardInterrupt) as error:
        raise SystemExit("Configuracao cancelada.") from error
    if not username or not password:
        raise ValueError("Usuario e senha sao obrigatorios.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "siteUrl": site_url.rstrip("/"),
                "adminUsername": username,
                "adminPassword": password,
                "cdpUrl": "http://127.0.0.1:9222",
                "pollSeconds": 15,
                "batchSize": 20,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Configuracao salva somente neste computador em {path}.")


def browser_candidates() -> list[Path]:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", "C:/"))
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    return [
        local_app_data / "BraveSoftware/Brave-Browser/Application/brave.exe",
        program_files / "BraveSoftware/Brave-Browser/Application/brave.exe",
        local_app_data / "Google/Chrome/Application/chrome.exe",
        program_files / "Google/Chrome/Application/chrome.exe",
        program_files / "Microsoft/Edge/Application/msedge.exe",
        program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
    ]


def cdp_is_ready(cdp_url: str) -> bool:
    try:
        with urlopen(cdp_url.rstrip("/") + "/json/version", timeout=3):
            return True
    except Exception:
        return False


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
            "--remote-debugging-port=9222",
            f"--user-data-dir={PROFILE_DIR}",
            LINKBUILDER_URL,
        ],
        close_fds=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if cdp_is_ready(cdp_url):
            return
        time.sleep(1)
    raise RuntimeError("O navegador abriu, mas a automacao nao conseguiu se conectar.")


def authenticated_opener(config: dict):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    base_url = config["siteUrl"].rstrip("/") + "/"
    api_request(
        opener,
        "POST",
        urljoin(base_url, "api/login"),
        {
            "username": config["adminUsername"],
            "password": config["adminPassword"],
        },
    )
    return opener


def update_status(opener, config: dict, state: str, message: str, processed: int = 0, failed: int = 0) -> None:
    api_request(
        opener,
        "POST",
        urljoin(config["siteUrl"].rstrip("/") + "/", "api/automation-agent/status"),
        {
            "state": state,
            "message": message,
            "processed": processed,
            "failed": failed,
        },
    )


def process_candidates(config: dict) -> tuple[int, int]:
    opener = authenticated_opener(config)
    base_url = config["siteUrl"].rstrip("/") + "/"
    payload = api_request(opener, "GET", urljoin(base_url, "api/candidates"))
    candidates = [
        candidate
        for candidate in payload.get("candidates", [])
        if candidate.get("store") == "Mercado Livre" and candidate.get("productUrl")
    ]
    if not candidates:
        update_status(opener, config, "idle", "Agente conectado e aguardando novas ofertas.")
        return 0, 0

    ensure_browser(str(config.get("cdpUrl") or "http://127.0.0.1:9222"))
    update_status(opener, config, "processing", f"Gerando links para {len(candidates)} ofertas do Mercado Livre.")

    processed_ids = []
    failed = 0
    batch_size = max(1, min(int(config.get("batchSize") or 20), 50))
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        source_links = [str(candidate["productUrl"]) for candidate in batch]
        generated = generate_affiliate_links(
            source_links,
            str(config.get("cdpUrl") or "http://127.0.0.1:9222"),
            90,
        )
        statuses = publish_to_site(
            config["siteUrl"],
            config["adminUsername"],
            config["adminPassword"],
            source_links,
            generated,
        )
        for index, candidate in enumerate(batch):
            status = statuses[index] if index < len(statuses) else "nao_gerado"
            if status in {"publicado", "atualizado_existente"}:
                processed_ids.append(candidate["id"])
            else:
                failed += 1
        update_status(
            opener,
            config,
            "processing",
            f"{min(start + len(batch), len(candidates))} de {len(candidates)} ofertas processadas.",
            len(processed_ids),
            failed,
        )

    if processed_ids:
        api_request(
            opener,
            "POST",
            urljoin(base_url, "api/candidates/complete"),
            {"ids": processed_ids},
        )
    update_status(
        opener,
        config,
        "completed",
        f"{len(processed_ids)} ofertas publicadas ou atualizadas; {failed} falharam.",
        len(processed_ids),
        failed,
    )
    return len(processed_ids), failed


def run_agent(config: dict, once: bool = False) -> None:
    poll_seconds = max(5, int(config.get("pollSeconds") or 15))
    print("Agente Mercado Livre conectado ao Mega Descontos.")
    while True:
        try:
            process_candidates(config)
        except Exception as error:
            print(f"Falha na automacao: {error}")
            try:
                opener = authenticated_opener(config)
                update_status(opener, config, "error", str(error))
            except Exception:
                pass
        if once:
            return
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente local da automacao Mercado Livre.")
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
