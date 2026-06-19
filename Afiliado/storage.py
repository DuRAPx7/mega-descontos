import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = ROOT_DIR / "data" / "mega_descontos.db"
MIGRATION_KEY = "offers_json_migration_v1"


class OfferStorage:
    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "").strip()
        self.sqlite_path = Path(os.environ.get("SQLITE_PATH", DEFAULT_SQLITE_PATH))
        self.backend = "postgresql" if self.database_url else "sqlite"
        self._lock = threading.RLock()
        self._initialized = False

    @property
    def description(self) -> str:
        if self.backend == "postgresql":
            return "PostgreSQL persistente"
        return f"SQLite local ({self.sqlite_path})"

    def _connect(self):
        if self.backend == "postgresql":
            try:
                import psycopg
            except ImportError as error:
                raise RuntimeError(
                    "DATABASE_URL foi configurada, mas o driver psycopg nao esta instalado. "
                    "Execute: pip install -r requirements.txt"
                ) from error
            return psycopg.connect(self.database_url)

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _placeholder(self) -> str:
        return "%s" if self.backend == "postgresql" else "?"

    def initialize(self, seed_offers: list[dict]) -> int:
        with self._lock:
            if self._initialized:
                return 0

            with closing(self._connect()) as connection:
                imported = self._initialize_connection(connection, seed_offers)
                connection.commit()
            self._initialized = True
            return imported

    def _initialize_connection(self, connection, seed_offers: list[dict]) -> int:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS offers (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                expires_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS offer_candidates (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        placeholder = self._placeholder()
        migrated = connection.execute(
            f"SELECT value FROM app_meta WHERE key = {placeholder}",
            (MIGRATION_KEY,),
        ).fetchone()
        imported = 0

        if not migrated:
            existing_count = connection.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
            if existing_count == 0 and seed_offers:
                imported = self._replace_all(connection, seed_offers)
            connection.execute(
                f"INSERT INTO app_meta (key, value) VALUES ({placeholder}, {placeholder})",
                (MIGRATION_KEY, datetime.now(timezone.utc).isoformat()),
            )

        return imported

    def read_all(self) -> list[dict]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute("SELECT payload FROM offers ORDER BY updated_at DESC").fetchall()

        offers = []
        for row in rows:
            try:
                payload = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                offers.append(payload)
        return offers

    def replace_all(self, offers: list[dict]) -> int:
        with self._lock, closing(self._connect()) as connection:
            total = self._replace_all(connection, offers)
            connection.commit()
            return total

    def read_candidates(self) -> list[dict]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM offer_candidates ORDER BY updated_at DESC"
            ).fetchall()
        return self._decode_payload_rows(rows)

    def replace_candidates(self, candidates: list[dict]) -> int:
        unique_candidates = {
            str(candidate["id"]): candidate
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("id") is not None
        }
        with self._lock, closing(self._connect()) as connection:
            connection.execute("DELETE FROM offer_candidates")
            if unique_candidates:
                placeholder = self._placeholder()
                query = (
                    "INSERT INTO offer_candidates (id, payload, updated_at) "
                    f"VALUES ({placeholder}, {placeholder}, {placeholder})"
                )
                updated_at = datetime.now(timezone.utc).isoformat()
                rows = [
                    (
                        candidate_id,
                        json.dumps(candidate, ensure_ascii=False, separators=(",", ":")),
                        updated_at,
                    )
                    for candidate_id, candidate in unique_candidates.items()
                ]
                cursor = connection.cursor()
                try:
                    cursor.executemany(query, rows)
                finally:
                    cursor.close()
            connection.commit()
        return len(unique_candidates)

    @staticmethod
    def _decode_payload_rows(rows) -> list[dict]:
        payloads = []
        for row in rows:
            try:
                payload = json.loads(row[0])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def _replace_all(self, connection, offers: list[dict]) -> int:
        unique_offers = {
            str(offer["id"]): offer
            for offer in offers
            if isinstance(offer, dict) and offer.get("id") is not None
        }
        normalized = list(unique_offers.values())
        connection.execute("DELETE FROM offers")
        if not normalized:
            return 0

        placeholder = self._placeholder()
        query = (
            "INSERT INTO offers (id, payload, source, expires_at, updated_at) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})"
        )
        updated_at = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                str(offer["id"]),
                json.dumps(offer, ensure_ascii=False, separators=(",", ":")),
                str(offer.get("source") or ""),
                str(offer.get("expiresAt") or ""),
                updated_at,
            )
            for offer in normalized
        ]
        cursor = connection.cursor()
        try:
            cursor.executemany(query, rows)
        finally:
            cursor.close()
        return len(rows)


offer_storage = OfferStorage()
