import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from friend_circle_lite.crawler.article_tracker import LatestArticleTracker
from friend_circle_lite.domain.models import Article


OLD_TRACKING_SCHEMA = """
CREATE TABLE article_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    link TEXT NOT NULL,
    published TEXT NOT NULL,
    summary TEXT,
    content TEXT
)
"""


class ArticleTrackingTest(unittest.TestCase):
    def test_previous_version_snapshot_does_not_resend_old_articles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cache.sqlite3"
            # Simulate a cache file written by the previous version. The table
            # structure is intentionally identical to the current one.
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(OLD_TRACKING_SCHEMA)
                connection.executemany(
                    """INSERT INTO article_tracking(title, author, link, published, summary, content)
                       VALUES (?, ?, ?, ?, '', '')""",
                    [
                        ("Old A", "Site", "https://site.example/old-a", "2026-11-01 10:00"),
                        ("Old B", "Site", "https://site.example/old-b", "2026-11-02 10:00"),
                    ],
                )
                connection.commit()

            latest_articles = [
                Article(title="Old A", author="Site", link="https://site.example/old-a", published="2026-11-01 10:00"),
                Article(title="Old B", author="Site", link="https://site.example/old-b", published="2026-11-02 10:00"),
                Article(title="New C", author="Site", link="https://site.example/new-c", published="2026-11-03 10:00"),
            ]

            updated = LatestArticleTracker(db_path).diff_and_persist(latest_articles)

        self.assertEqual([article["title"] for article in updated], ["New C"])

    def test_same_articles_are_not_returned_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cache.sqlite3"
            tracker = LatestArticleTracker(db_path)
            articles = [
                Article(title="Post", author="Site", link="https://site.example/post", published="2026-11-03 10:00"),
            ]

            self.assertIsNone(tracker.diff_and_persist(articles))  # first run: baseline only
            self.assertIsNone(tracker.diff_and_persist(articles))  # second run: nothing new

    def test_missing_tracking_table_starts_with_a_baseline_instead_of_resending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cache.sqlite3"

            updated = LatestArticleTracker(db_path).diff_and_persist([
                Article(title="Old", author="Site", link="https://site.example/old", published="2026-11-01 10:00"),
            ])

        self.assertIsNone(updated)


if __name__ == "__main__":
    unittest.main()
