import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.storage import OfferStorage


class OfferStorageTests(unittest.TestCase):
    def make_storage(self, path: Path) -> OfferStorage:
        with patch.dict(os.environ, {"SQLITE_PATH": str(path)}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            return OfferStorage()

    def test_migrates_seed_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.db"
            seed = [{"id": 1, "title": "Oferta inicial"}]

            storage = self.make_storage(path)
            self.assertEqual(storage.initialize(seed), 1)
            self.assertEqual(storage.read_all(), seed)

            storage.replace_all([])
            restarted_storage = self.make_storage(path)
            self.assertEqual(restarted_storage.initialize(seed), 0)
            self.assertEqual(restarted_storage.read_all(), [])

    def test_replaces_and_persists_offers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.db"
            storage = self.make_storage(path)
            storage.initialize([])

            offers = [
                {"id": "abc", "title": "Primeira", "source": "admin"},
                {"id": 2, "title": "Segunda", "expiresAt": "2030-01-01T00:00:00Z"},
            ]
            self.assertEqual(storage.replace_all(offers), 2)

            restarted_storage = self.make_storage(path)
            restarted_storage.initialize([])
            persisted = restarted_storage.read_all()
            self.assertEqual({offer["title"] for offer in persisted}, {"Primeira", "Segunda"})

    def test_duplicate_ids_keep_latest_offer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offers.db"
            storage = self.make_storage(path)
            storage.initialize([])

            storage.replace_all(
                [
                    {"id": 7, "title": "Antiga"},
                    {"id": 7, "title": "Atualizada"},
                ]
            )
            self.assertEqual(storage.read_all()[0]["title"], "Atualizada")

    def test_persists_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = self.make_storage(Path(directory) / "offers.db")
            storage.initialize([])
            candidates = [{"id": 10, "title": "Oferta encontrada"}]
            self.assertEqual(storage.replace_candidates(candidates), 1)
            self.assertEqual(storage.read_candidates(), candidates)

    def test_persists_and_deletes_integration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = self.make_storage(Path(directory) / "offers.db")
            storage.initialize([])
            tokens = {"accessToken": "token", "refreshToken": "refresh", "expiresAt": 123}
            storage.set_integration("mercadolivre", tokens)
            self.assertEqual(storage.get_integration("mercadolivre"), tokens)
            storage.delete_integration("mercadolivre")
            self.assertIsNone(storage.get_integration("mercadolivre"))

    def test_persists_discount_requests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = self.make_storage(Path(directory) / "offers.db")
            storage.initialize([])
            request = {
                "id": "pedido-1",
                "product": "Notebook para trabalho",
                "contact": "cliente@example.com",
                "status": "pending",
                "createdAt": "2026-07-05T12:00:00+00:00",
            }
            self.assertEqual(storage.create_discount_request(request), request)
            self.assertEqual(storage.read_discount_requests(), [request])


if __name__ == "__main__":
    unittest.main()
