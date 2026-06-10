"""SQLite 缓存诊断与安全整理。

本文件只负责调试期开启的 SQLite 检查：
- 输出当前数据库中的全部表结构与全部数据；
- 对项目内部核心表执行保守 schema 整理，移除残留旧字段；
- 不自动删除未知表，避免误删用户额外保存的数据。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path


EXPECTED_SCHEMAS: dict[str, tuple[list[str], str]] = {
    "feed_cache": (
        ["name", "url", "source"],
        """
        CREATE TABLE feed_cache (
            name TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'cache'
        )
        """,
    ),
    "article_tracking": (
        ["id", "title", "author", "link", "published", "summary", "content"],
        """
        CREATE TABLE article_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            link TEXT NOT NULL,
            published TEXT NOT NULL,
            summary TEXT,
            content TEXT
        )
        """,
    ),
    "link_check_state": (
        [
            "url",
            "name",
            "avatar",
            "linkpage",
            "checked_at",
            "reachable",
            "crawl_allowed",
            "best_method",
            "best_latency",
            "fail_count",
            "backlink_checked",
            "has_author_link",
            "rss_crawl_reason",
            "last_post_published",
            "last_post_days_ago",
            "direct_success",
            "direct_status_code",
            "direct_latency",
            "proxy_success",
            "proxy_status_code",
            "proxy_latency",
            "api_success",
            "api_status_code",
            "api_latency",
        ],
        """
        CREATE TABLE link_check_state (
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
            last_post_published TEXT DEFAULT '',
            last_post_days_ago INTEGER,
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
        """,
    ),
}

DEFAULT_EXPRESSIONS: dict[str, str] = {
    "id": "NULL",
    "name": "''",
    "url": "''",
    "source": "'cache'",
    "title": "''",
    "author": "''",
    "link": "''",
    "published": "''",
    "summary": "NULL",
    "content": "NULL",
    "avatar": "''",
    "linkpage": "''",
    "checked_at": "''",
    "reachable": "0",
    "crawl_allowed": "0",
    "best_method": "'none'",
    "best_latency": "-1",
    "fail_count": "0",
    "backlink_checked": "0",
    "has_author_link": "0",
    "rss_crawl_reason": "''",
    "last_post_published": "''",
    "last_post_days_ago": "NULL",
    "direct_success": "0",
    "direct_status_code": "NULL",
    "direct_latency": "-1",
    "proxy_success": "0",
    "proxy_status_code": "NULL",
    "proxy_latency": "-1",
    "api_success": "0",
    "api_status_code": "NULL",
    "api_latency": "-1",
}


class SQLiteDebugDumper:
    """打印 SQLite 全量调试信息，并清理核心表中的旧字段。"""

    def __init__(self, database_path: str | Path | None):
        self.database_path = Path(database_path) if database_path else None

    def run(self) -> str:
        """执行 schema 检查、保守清理与全量数据输出。"""
        lines: list[str] = []
        self._append(lines, "=" * 60)
        self._append(lines, "SQLite 调试信息")
        self._append(lines, "=" * 60)

        if not self.database_path:
            self._append(lines, "未配置 SQLite 缓存路径，跳过调试输出")
            return self._flush(lines)

        self._append(lines, f"数据库路径: {self.database_path}")
        if not self.database_path.exists():
            self._append(lines, "数据库文件不存在，跳过调试输出")
            return self._flush(lines)

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            self._report_schema_state(connection, lines)
            self._clean_known_tables(connection, lines)
            self._dump_all_tables(connection, lines)

        return self._flush(lines)

    def _report_schema_state(self, connection: sqlite3.Connection, lines: list[str]) -> None:
        tables = self._table_names(connection)
        self._append(lines, f"当前表数量: {len(tables)}")
        for table in tables:
            columns = self._column_names(connection, table)
            self._append(lines, f"表 {table} 字段: {', '.join(columns)}")
            expected = EXPECTED_SCHEMAS.get(table)
            if not expected:
                self._append(lines, f"表 {table} 不是 Friend-Circle-Lite 核心表，保留不清理")
                continue
            extra_columns = [column for column in columns if column not in expected[0]]
            missing_columns = [column for column in expected[0] if column not in columns]
            if extra_columns:
                self._append(lines, f"表 {table} 检测到旧字段: {', '.join(extra_columns)}")
            if missing_columns:
                self._append(lines, f"表 {table} 缺少当前字段，将使用默认值补齐: {', '.join(missing_columns)}")

    def _clean_known_tables(self, connection: sqlite3.Connection, lines: list[str]) -> None:
        for table, (expected_columns, create_sql) in EXPECTED_SCHEMAS.items():
            if table not in self._table_names(connection):
                connection.execute(create_sql)
                self._append(lines, f"表 {table} 不存在，已按当前 schema 创建")
                continue

            current_columns = self._column_names(connection, table)
            if current_columns == expected_columns:
                self._append(lines, f"表 {table} schema 已匹配，无需清理")
                continue

            temp_table = f"__fcl_rebuild_{table}"
            connection.execute(f"DROP TABLE IF EXISTS {temp_table}")
            connection.execute(create_sql.replace(f"CREATE TABLE {table}", f"CREATE TABLE {temp_table}", 1))

            common_columns = [column for column in expected_columns if column in current_columns]
            insert_columns = ", ".join(self._quote_identifier(column) for column in expected_columns)
            select_expressions = ", ".join(
                self._quote_identifier(column) if column in current_columns else DEFAULT_EXPRESSIONS[column]
                for column in expected_columns
            )
            connection.execute(
                f"INSERT INTO {self._quote_identifier(temp_table)} ({insert_columns}) "
                f"SELECT {select_expressions} FROM {self._quote_identifier(table)}"
            )

            connection.execute(f"DROP TABLE {self._quote_identifier(table)}")
            connection.execute(
                f"ALTER TABLE {self._quote_identifier(temp_table)} RENAME TO {self._quote_identifier(table)}"
            )
            self._append(lines, f"表 {table} 已重建为当前 schema，保留字段: {', '.join(common_columns)}")
        connection.commit()

    def _dump_all_tables(self, connection: sqlite3.Connection, lines: list[str]) -> None:
        tables = self._table_names(connection)
        self._append(lines, "SQLite 全量数据开始")
        for table in tables:
            rows = connection.execute(f"SELECT * FROM {self._quote_identifier(table)}").fetchall()
            self._append(lines, f"表 {table} 行数: {len(rows)}")
            for index, row in enumerate(rows, start=1):
                row_data = {key: row[key] for key in row.keys()}
                self._append(lines, f"表 {table} 第 {index} 行: {json.dumps(row_data, ensure_ascii=False)}")
        self._append(lines, "SQLite 全量数据结束")

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row[0] for row in rows]

    @staticmethod
    def _column_names(connection: sqlite3.Connection, table: str) -> list[str]:
        rows = connection.execute(f"PRAGMA table_info({SQLiteDebugDumper._quote_identifier(table)})").fetchall()
        return [row[1] for row in rows]

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _append(lines: list[str], message: str) -> None:
        lines.append(message)

    @staticmethod
    def _flush(lines: list[str]) -> str:
        output = "\n".join(lines)
        for line in lines:
            logging.info(line)
        return output
