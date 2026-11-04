"""Persistent RSS endpoint cache."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import yaml

from friend_circle_lite.domain.models import CacheRecord
from friend_circle_lite.storage.schema import create_table_sql


class FeedCacheStore:
    """Persist and load discovered RSS endpoints using SQLite.

    For smooth upgrades, legacy JSON and YAML cache files are migrated on first
    load when present.
    """

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
                logging.info(f"[RSS 缓存] 已从旧格式迁移 {len(migrated_records)} 条 RSS 缓存到 SQLite")
            return migrated_records

        logging.info("[RSS 缓存] RSS 缓存文件不存在，将在首次抓取后自动创建")
        return []

    def save_records(self, records: list[CacheRecord]) -> bool:
        """Persist cache records to the SQLite database."""
        if not self.cache_path:
            return True

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.cache_path)) as connection:
                self._ensure_schema(connection)
                connection.execute("DELETE FROM feed_cache")
                connection.executemany(
                    "INSERT INTO feed_cache(name, url, source) VALUES (?, ?, ?)",
                    [
                        (record.name, record.url, record.source)
                        for record in sorted(records, key=lambda item: item.name)
                    ],
                )
                connection.commit()
            logging.info(f"[RSS 缓存] RSS 缓存已保存（{len(records)} 条）")
            return True
        except Exception as exc:
            logging.error(f"[RSS 缓存] 保存 RSS 缓存失败: {exc}")
            return False

    def _load_from_sqlite(self) -> list[CacheRecord]:
        """Load records from the current SQLite cache file."""
        try:
            with closing(sqlite3.connect(self.cache_path)) as connection:
                self._ensure_schema(connection)
                connection.commit()
                rows = connection.execute(
                    "SELECT name, url, source FROM feed_cache ORDER BY name"
                ).fetchall()
        except Exception as exc:
            logging.warning(f"[RSS 缓存] 读取 RSS 缓存失败: {exc}")
            return []

        return [
            CacheRecord(name=name, url=url, source=source or "cache")
            for name, url, source in rows
            if name and url
        ]

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        """Create the cache table when it does not exist yet."""
        connection.execute(create_table_sql("feed_cache", if_not_exists=True))

    def _load_legacy_records(self) -> list[CacheRecord]:
        """Read old cache formats for seamless upgrades."""
        return self._load_legacy_json_cache() or self._load_legacy_yaml_cache()

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
