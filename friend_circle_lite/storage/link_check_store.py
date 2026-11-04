"""Persistent friend-link reachability checks."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from friend_circle_lite.domain.models import LinkCheckRecord, LinkMethodStatus, normalize_homepage_url
from friend_circle_lite.storage.schema import create_table_sql


class LinkCheckStore:
    """Persist friend link reachability checks using SQLite."""

    def __init__(self, cache_path: str | Path | None):
        self.cache_path = Path(cache_path) if cache_path else None

    def load_records(self, urls: list[str] | None = None) -> dict[str, LinkCheckRecord]:
        if not self.cache_path or not self.cache_path.exists():
            return {}

        try:
            with closing(sqlite3.connect(self.cache_path)) as connection:
                self._ensure_schema(connection)
                connection.commit()
                rows = connection.execute(
                    """
                    SELECT url, name, avatar, linkpage, checked_at, reachable, crawl_allowed,
                           best_method, best_latency, backlink_checked, has_author_link,
                           rss_crawl_reason, last_post_published, last_post_days_ago,
                           unreachable_since, rss_unavailable_since,
                           direct_success, direct_status_code, direct_latency,
                           proxy_success, proxy_status_code, proxy_latency, api_success,
                           api_status_code, api_latency
                    FROM link_check_state
                    """
                ).fetchall()
        except Exception as exc:
            logging.warning(f"[友链检测] 读取友链检测缓存失败: {exc}")
            return {}

        allowed_urls = {normalize_homepage_url(url) for url in (urls or [])}
        records: dict[str, LinkCheckRecord] = {}
        for row in rows:
            (
                url, name, avatar, linkpage, checked_at, reachable, crawl_allowed,
                best_method, best_latency, backlink_checked, has_author_link,
                rss_crawl_reason, last_post_published, last_post_days_ago,
                unreachable_since, rss_unavailable_since,
                direct_success, direct_status_code, direct_latency,
                proxy_success, proxy_status_code, proxy_latency, api_success,
                api_status_code, api_latency,
            ) = row
            normalized_url = normalize_homepage_url(url or "")
            if allowed_urls and normalized_url not in allowed_urls:
                continue
            records[normalized_url] = LinkCheckRecord(
                name=name or "",
                url=normalized_url,
                avatar=avatar or "",
                linkpage=linkpage or "",
                checked_at=checked_at or "",
                reachable=bool(reachable),
                crawl_allowed=bool(crawl_allowed),
                best_method=best_method or "none",
                best_latency=best_latency if best_latency is not None else -1,
                backlink_checked=bool(backlink_checked),
                has_author_link=bool(has_author_link),
                rss_crawl_reason=rss_crawl_reason or "blocked_unreachable",
                last_post_published=last_post_published or "",
                last_post_days_ago=last_post_days_ago,
                unreachable_since=unreachable_since or (checked_at or "" if not bool(reachable) else ""),
                rss_unavailable_since=rss_unavailable_since or (checked_at or "" if bool(reachable) and not bool(crawl_allowed) else ""),
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
            with closing(sqlite3.connect(self.cache_path)) as connection:
                self._ensure_schema(connection)
                connection.executemany(
                    """
                    INSERT INTO link_check_state(
                        url, name, avatar, linkpage, checked_at, reachable, crawl_allowed,
                        best_method, best_latency, backlink_checked, has_author_link,
                        rss_crawl_reason, last_post_published, last_post_days_ago,
                        unreachable_since, rss_unavailable_since,
                        direct_success, direct_status_code, direct_latency,
                        proxy_success, proxy_status_code, proxy_latency, api_success,
                        api_status_code, api_latency
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        name = excluded.name,
                        avatar = excluded.avatar,
                        linkpage = excluded.linkpage,
                        checked_at = excluded.checked_at,
                        reachable = excluded.reachable,
                        crawl_allowed = excluded.crawl_allowed,
                        best_method = excluded.best_method,
                        best_latency = excluded.best_latency,
                        backlink_checked = excluded.backlink_checked,
                        has_author_link = excluded.has_author_link,
                        rss_crawl_reason = excluded.rss_crawl_reason,
                        last_post_published = excluded.last_post_published,
                        last_post_days_ago = excluded.last_post_days_ago,
                        unreachable_since = excluded.unreachable_since,
                        rss_unavailable_since = excluded.rss_unavailable_since,
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
            logging.info(f"[友链检测] 友链检测缓存已保存（{len(records)} 条）")
            return True
        except Exception as exc:
            logging.error(f"[友链检测] 保存友链检测缓存失败: {exc}")
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
            normalize_homepage_url(record.url),
            record.name,
            record.avatar,
            record.linkpage,
            record.checked_at,
            int(record.reachable),
            int(record.crawl_allowed),
            record.best_method,
            record.best_latency,
            int(record.backlink_checked),
            int(record.has_author_link),
            record.rss_crawl_reason,
            record.last_post_published,
            record.last_post_days_ago,
            record.unreachable_since,
            record.rss_unavailable_since,
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
        connection.execute(create_table_sql("link_check_state", if_not_exists=True))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(link_check_state)").fetchall()}
        if "last_post_published" not in columns:
            connection.execute("ALTER TABLE link_check_state ADD COLUMN last_post_published TEXT DEFAULT ''")
        if "last_post_days_ago" not in columns:
            connection.execute("ALTER TABLE link_check_state ADD COLUMN last_post_days_ago INTEGER")
        if "unreachable_since" not in columns:
            connection.execute("ALTER TABLE link_check_state ADD COLUMN unreachable_since TEXT DEFAULT ''")
        if "rss_unavailable_since" not in columns:
            connection.execute("ALTER TABLE link_check_state ADD COLUMN rss_unavailable_since TEXT DEFAULT ''")
