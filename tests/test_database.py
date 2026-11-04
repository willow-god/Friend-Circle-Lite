import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from friend_circle_lite.domain.models import LinkCheckRecord
from friend_circle_lite.storage.link_check_store import LinkCheckStore
from friend_circle_lite.storage.state_store import StateStore


class DatabaseTest(unittest.TestCase):
    def test_state_store_roundtrips_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StateStore(Path(temp_dir) / "cache.sqlite3")

            self.assertTrue(store.set("key", "value"))

            self.assertEqual(store.get("key"), "value")
            self.assertIsNone(store.get("missing"))

    def test_link_check_store_schema_no_longer_contains_fail_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cache.sqlite3"
            store = LinkCheckStore(db_path)
            record = LinkCheckRecord(
                name="Site",
                url="https://site.example/",
                checked_at="2026-11-04 08:00:00",
                reachable=True,
                crawl_allowed=True,
                best_method="rss",
                best_latency=0.3,
            )

            self.assertTrue(store.save_records([record]))
            loaded = store.load_records()

            with closing(sqlite3.connect(db_path)) as connection:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(link_check_state)").fetchall()]

        self.assertNotIn("fail_count", columns)
        self.assertEqual(loaded["https://site.example/"].name, "Site")
        self.assertTrue(loaded["https://site.example/"].crawl_allowed)


if __name__ == "__main__":
    unittest.main()
