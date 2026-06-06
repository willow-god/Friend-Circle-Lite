"""Persistent RSS cache and article tracking storage.

SQLite is used for both feed cache and article tracking because it is more robust
than hand-edited text formats for internal state:

- schema is explicit and stable;
- writes are transactional;
- corruption risk from accidental manual edits is lower;
- Python ships with `sqlite3`, so no extra dependency is required.

For smooth upgrades, this store can also migrate legacy cache data from the old
JSON cache file and the intermediate YAML cache file if they exist.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from friend_circle_lite.domain.models import Article, CacheRecord, LinkCheckRecord, LinkMethodStatus


class FeedCacheStore:
    """Persist and load discovered RSS endpoints using SQLite."""

    def __init__(self, cache_path: str | Path | None):
        self.cache_path = Path(cache_path) if cache_path else None

    def load_records(self) -> list[CacheRecord]:
        """Load cache records from SQLite, migrating legacy formats if needed."""
        if not self.cache_path:
            return []

        if self.cache_path.exists():
            return self._load_from_sqlite()

        migrated_records = self._load_legacy_records()
        if migrated_records:
            if self.save_records(migrated_records):
                logging.info(f"已从旧格式迁移 {len(migrated_records)} 条 RSS 缓存到 SQLite")
            return migrated_records

        logging.info(f"RSS 缓存文件不存在，将在首次抓取后自动创建")
        return []

    def save_records(self, records: list[CacheRecord]) -> bool:
        """Persist cache records to the SQLite database."""
        if not self.cache_path:
            return True

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.cache_path) as connection:
                self._ensure_schema(connection)
                connection.execute("DELETE FROM feed_cache")
                connection.executemany(
                    "INSERT INTO feed_cache(name, url, source) VALUES (?, ?, ?)",
                    [(record.name, record.url, record.source) for record in sorted(records, key=lambda item: item.name)],
                )
                connection.commit()
            logging.info(f"RSS 缓存已保存（{len(records)} 条）")
            return True
        except Exception as exc:
            logging.error(f"保存 RSS 缓存失败: {exc}")
            return False

    def _load_from_sqlite(self) -> list[CacheRecord]:
        """Load records from the current SQLite cache file."""
        try:
            with sqlite3.connect(self.cache_path) as connection:
                self._ensure_schema(connection)
                rows = connection.execute(
                    "SELECT name, url, source FROM feed_cache ORDER BY name"
                ).fetchall()
        except Exception as exc:
            logging.warning(f"读取 RSS 缓存失败: {exc}")
            return []

        return [
            CacheRecord(name=name, url=url, source=source or "cache")
            for name, url, source in rows
            if name and url
        ]

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        """Create the cache table when it does not exist yet."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS feed_cache (
                name TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'cache'
            )
            """
        )

    def _load_legacy_records(self) -> list[CacheRecord]:
        """Read old cache formats for seamless upgrades."""
        json_records = self._load_legacy_json_cache()
        if json_records:
            return json_records

        yaml_records = self._load_legacy_yaml_cache()
        if yaml_records:
            return yaml_records

        return []

    def _load_legacy_json_cache(self) -> list[CacheRecord]:
        """Read the previous JSON cache file format."""
        if not self.cache_path:
            return []

        legacy_path = self.cache_path.with_name("cache.json")
        if not legacy_path.exists():
            return []

        try:
            with open(legacy_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception as exc:
            logging.warning(f"读取旧 JSON 缓存失败: {exc}")
            return []

        if not isinstance(payload, list):
            return []

        return self._normalize_legacy_items(payload)

    def _load_legacy_yaml_cache(self) -> list[CacheRecord]:
        """Read the temporary YAML cache format used during refactoring."""
        if not self.cache_path:
            return []

        legacy_path = self.cache_path.with_name("feed_cache.yaml")
        if not legacy_path.exists():
            return []

        try:
            with open(legacy_path, "r", encoding="utf-8") as file:
                payload = yaml.safe_load(file) or {}
        except Exception as exc:
            logging.warning(f"读取旧 YAML 缓存失败: {exc}")
            return []

        items = payload.get("feeds", []) if isinstance(payload, dict) else []
        return self._normalize_legacy_items(items)

    @staticmethod
    def _normalize_legacy_items(items: list[object]) -> list[CacheRecord]:
        """Normalize legacy cache items into typed cache records."""
        records: list[CacheRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            url = str(item.get("url", "")).strip()
            source = str(item.get("source", "cache")).strip() or "cache"
            if name and url:
                records.append(CacheRecord(name=name, url=url, source=source))
        return records


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

        # Try to migrate from legacy JSON format
        migrated_articles = self._load_legacy_json()
        if migrated_articles:
            if self.save_articles(migrated_articles):
                logging.info(f"已从旧 JSON 格式迁移 {len(migrated_articles)} 篇文章记录到 SQLite")
            return migrated_articles

        logging.info(f"文章追踪数据不存在，这是首次运行")
        return []

    def save_articles(self, articles: list[Article]) -> bool:
        """Persist articles to SQLite, keeping only the most recent max_tracked_articles."""
        if not self.storage_path:
            return True

        try:
            # Sort by date and keep only the most recent articles
            valid_articles = [article for article in articles if article.published]
            valid_articles.sort(
                key=lambda item: datetime.strptime(item.published, "%Y-%m-%d %H:%M"),
                reverse=True
            )
            articles_to_save = valid_articles[:self.max_tracked_articles]

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.storage_path) as connection:
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
            logging.error(f"保存文章追踪数据失败: {exc}")
            return False

    def _load_from_sqlite(self) -> list[Article]:
        """Load articles from the SQLite database."""
        try:
            with sqlite3.connect(self.storage_path) as connection:
                self._ensure_schema(connection)
                rows = connection.execute(
                    """SELECT title, author, link, published, summary, content
                       FROM article_tracking
                       ORDER BY published DESC"""
                ).fetchall()
        except Exception as exc:
            logging.warning(f"读取文章追踪数据失败: {exc}")
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS article_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                link TEXT NOT NULL,
                published TEXT NOT NULL,
                summary TEXT,
                content TEXT
            )
            """
        )

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
        articles: list[Article] = []
        for item in articles_data:
            if not isinstance(item, dict):
                continue
            articles.append(
                Article(
                    title=item.get("title", ""),
                    author=item.get("author", ""),
                    link=item.get("link", ""),
                    published=item.get("published", ""),
                    summary=item.get("summary", ""),
                    content=item.get("content", ""),
                )
            )
        return articles


class LinkCheckStore:
    """Persist friend link reachability checks using SQLite."""

    def __init__(self, cache_path: str | Path | None):
        self.cache_path = Path(cache_path) if cache_path else None

    def load_records(self, urls: list[str] | None = None) -> dict[str, LinkCheckRecord]:
        if not self.cache_path or not self.cache_path.exists():
            return {}

        try:
            with sqlite3.connect(self.cache_path) as connection:
                self._ensure_schema(connection)
                rows = connection.execute(
                    """
                    SELECT url, name, avatar, linkpage, checked_at, reachable, crawl_allowed,
                           best_method, best_latency, fail_count, backlink_checked, has_author_link,
                           rss_crawl_reason, direct_success, direct_status_code, direct_latency,
                           proxy_success, proxy_status_code, proxy_latency, api_success,
                           api_status_code, api_latency
                    FROM link_check_state
                    """
                ).fetchall()
        except Exception as exc:
            logging.warning(f"读取友链检测缓存失败: {exc}")
            return {}

        allowed_urls = set(urls or [])
        records: dict[str, LinkCheckRecord] = {}
        for row in rows:
            (
                url, name, avatar, linkpage, checked_at, reachable, crawl_allowed,
                best_method, best_latency, fail_count, backlink_checked, has_author_link,
                rss_crawl_reason, direct_success, direct_status_code, direct_latency,
                proxy_success, proxy_status_code, proxy_latency, api_success,
                api_status_code, api_latency,
            ) = row
            if allowed_urls and url not in allowed_urls:
                continue
            records[url] = LinkCheckRecord(
                name=name or "",
                url=url or "",
                avatar=avatar or "",
                linkpage=linkpage or "",
                checked_at=checked_at or "",
                reachable=bool(reachable),
                crawl_allowed=bool(crawl_allowed),
                best_method=best_method or "none",
                best_latency=best_latency if best_latency is not None else -1,
                fail_count=fail_count or 0,
                backlink_checked=bool(backlink_checked),
                has_author_link=bool(has_author_link),
                rss_crawl_reason=rss_crawl_reason or "blocked_unreachable",
                direct=LinkMethodStatus(bool(direct_success), direct_status_code, direct_latency if direct_latency is not None else -1),
                proxy=LinkMethodStatus(bool(proxy_success), proxy_status_code, proxy_latency if proxy_latency is not None else -1),
                api=LinkMethodStatus(bool(api_success), api_status_code, api_latency if api_latency is not None else -1),
            )
        return records

    def save_records(self, records: list[LinkCheckRecord]) -> bool:
        if not self.cache_path:
            return True

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.cache_path) as connection:
                self._ensure_schema(connection)
                connection.executemany(
                    """
                    INSERT INTO link_check_state(
                        url, name, avatar, linkpage, checked_at, reachable, crawl_allowed,
                        best_method, best_latency, fail_count, backlink_checked, has_author_link,
                        rss_crawl_reason, direct_success, direct_status_code, direct_latency,
                        proxy_success, proxy_status_code, proxy_latency, api_success,
                        api_status_code, api_latency
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        name = excluded.name,
                        avatar = excluded.avatar,
                        linkpage = excluded.linkpage,
                        checked_at = excluded.checked_at,
                        reachable = excluded.reachable,
                        crawl_allowed = excluded.crawl_allowed,
                        best_method = excluded.best_method,
                        best_latency = excluded.best_latency,
                        fail_count = excluded.fail_count,
                        backlink_checked = excluded.backlink_checked,
                        has_author_link = excluded.has_author_link,
                        rss_crawl_reason = excluded.rss_crawl_reason,
                        direct_success = excluded.direct_success,
                        direct_status_code = excluded.direct_status_code,
                        direct_latency = excluded.direct_latency,
                        proxy_success = excluded.proxy_success,
                        proxy_status_code = excluded.proxy_status_code,
                        proxy_latency = excluded.proxy_latency,
                        api_success = excluded.api_success,
                        api_status_code = excluded.api_status_code,
                        api_latency = excluded.api_latency
                    """,
                    [self._record_to_row(record) for record in records],
                )
                connection.commit()
            logging.info(f"友链检测缓存已保存（{len(records)} 条）")
            return True
        except Exception as exc:
            logging.error(f"保存友链检测缓存失败: {exc}")
            return False

    @staticmethod
    def is_fresh(record: LinkCheckRecord, max_age_hours: int) -> bool:
        if not record.checked_at:
            return False
        try:
            checked_at = datetime.strptime(record.checked_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        age_seconds = (datetime.now() - checked_at).total_seconds()
        return age_seconds < max_age_hours * 3600

    @staticmethod
    def _record_to_row(record: LinkCheckRecord) -> tuple:
        return (
            record.url,
            record.name,
            record.avatar,
            record.linkpage,
            record.checked_at,
            int(record.reachable),
            int(record.crawl_allowed),
            record.best_method,
            record.best_latency,
            record.fail_count,
            int(record.backlink_checked),
            int(record.has_author_link),
            record.rss_crawl_reason,
            int(record.direct.success),
            record.direct.status_code,
            record.direct.latency,
            int(record.proxy.success),
            record.proxy.status_code,
            record.proxy.latency,
            int(record.api.success),
            record.api.status_code,
            record.api.latency,
        )

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS link_check_state (
                url TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                avatar TEXT DEFAULT '',
                linkpage TEXT DEFAULT '',
                checked_at TEXT NOT NULL,
                reachable INTEGER NOT NULL DEFAULT 0,
                crawl_allowed INTEGER NOT NULL DEFAULT 0,
                best_method TEXT NOT NULL DEFAULT 'none',
                best_latency REAL DEFAULT -1,
                fail_count INTEGER NOT NULL DEFAULT 0,
                backlink_checked INTEGER NOT NULL DEFAULT 0,
                has_author_link INTEGER NOT NULL DEFAULT 0,
                rss_crawl_reason TEXT NOT NULL DEFAULT '',
                direct_success INTEGER NOT NULL DEFAULT 0,
                direct_status_code INTEGER,
                direct_latency REAL DEFAULT -1,
                proxy_success INTEGER NOT NULL DEFAULT 0,
                proxy_status_code INTEGER,
                proxy_latency REAL DEFAULT -1,
                api_success INTEGER NOT NULL DEFAULT 0,
                api_status_code INTEGER,
                api_latency REAL DEFAULT -1
            )
            """
        )
