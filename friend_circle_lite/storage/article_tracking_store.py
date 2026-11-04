"""Persistent article tracking for subscription notifications."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from friend_circle_lite.domain.models import Article
from friend_circle_lite.storage.schema import create_table_sql


class ArticleTrackingStore:
    """Persist and load article tracking data using SQLite."""

    def __init__(self, storage_path: str | Path | None, max_tracked_articles: int = 10):
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_tracked_articles = max_tracked_articles

    def load_articles(self) -> list[Article]:
        """Load tracked articles from SQLite, migrating from legacy JSON if needed."""
        if not self.storage_path:
            return []

        if self.storage_path.exists():
            return self._load_from_sqlite()

        migrated_articles = self._load_legacy_json()
        if migrated_articles:
            if self.save_articles(migrated_articles):
                logging.info(f"[文章追踪] 已从旧 JSON 格式迁移 {len(migrated_articles)} 篇文章记录到 SQLite")
            return migrated_articles

        logging.info("[文章追踪] 文章追踪数据不存在，这是首次运行")
        return []

    def save_articles(self, articles: list[Article]) -> bool:
        """Persist articles to SQLite, keeping only the most recent ones."""
        if not self.storage_path:
            return True

        try:
            valid_articles = [article for article in articles if article.published]
            valid_articles.sort(
                key=lambda item: datetime.strptime(item.published, "%Y-%m-%d %H:%M"),
                reverse=True,
            )
            articles_to_save = valid_articles[:self.max_tracked_articles]

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.storage_path)) as connection:
                self._ensure_schema(connection)
                connection.execute("DELETE FROM article_tracking")
                connection.executemany(
                    """INSERT INTO article_tracking(title, author, link, published, summary, content)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            article.title,
                            article.author,
                            article.link,
                            article.published,
                            article.summary,
                            article.content,
                        )
                        for article in articles_to_save
                    ],
                )
                connection.commit()
            return True
        except Exception as exc:
            logging.error(f"[文章追踪] 保存文章追踪数据失败: {exc}")
            return False

    def _load_from_sqlite(self) -> list[Article]:
        """Load articles from the SQLite database."""
        try:
            with closing(sqlite3.connect(self.storage_path)) as connection:
                self._ensure_schema(connection)
                connection.commit()
                rows = connection.execute(
                    """SELECT title, author, link, published, summary, content
                       FROM article_tracking
                       ORDER BY published DESC"""
                ).fetchall()
        except Exception as exc:
            logging.warning(f"[文章追踪] 读取文章追踪数据失败: {exc}")
            return []

        return [
            Article(
                title=title or "",
                author=author or "",
                link=link or "",
                published=published or "",
                summary=summary or "",
                content=content or "",
            )
            for title, author, link, published, summary, content in rows
        ]

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        """Create the article tracking table when it does not exist yet."""
        connection.execute(create_table_sql("article_tracking", if_not_exists=True))

    def _load_legacy_json(self) -> list[Article]:
        """Read the old JSON format for seamless upgrades."""
        if not self.storage_path:
            return []

        legacy_path = self.storage_path.with_name("newest_posts.json")
        if not legacy_path.exists():
            return []

        try:
            with open(legacy_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception as exc:
            logging.warning(f"读取旧 JSON 文章追踪文件失败: {exc}")
            return []

        articles_data = payload.get("articles", []) if isinstance(payload, dict) else []
        return [
            Article(
                title=item.get("title", ""),
                author=item.get("author", ""),
                link=item.get("link", ""),
                published=item.get("published", ""),
                summary=item.get("summary", ""),
                content=item.get("content", ""),
            )
            for item in articles_data
            if isinstance(item, dict)
        ]
