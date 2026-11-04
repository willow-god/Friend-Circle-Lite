"""Key-value application state persisted alongside the crawl cache."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from friend_circle_lite.storage.schema import create_table_sql


class StateStore:
    """Persist small application state values in SQLite.

    This is used for cross-run bookkeeping such as the last email push time.
    """

    def __init__(self, database_path: str | Path | None):
        self.database_path = Path(database_path) if database_path else None

    def get(self, key: str) -> str | None:
        if not self.database_path or not self.database_path.exists():
            return None
        try:
            with closing(sqlite3.connect(self.database_path)) as connection:
                self._ensure_schema(connection)
                connection.commit()
                row = connection.execute(
                    "SELECT value FROM app_state WHERE key = ?", (key,)
                ).fetchone()
            return row[0] if row else None
        except Exception as exc:
            logging.warning(f"[应用状态] 读取 {key} 失败: {exc}")
            return None

    def set(self, key: str, value: str) -> bool:
        if not self.database_path:
            return True
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.database_path)) as connection:
                self._ensure_schema(connection)
                connection.execute(
                    """
                    INSERT INTO app_state(key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
                connection.commit()
            return True
        except Exception as exc:
            logging.warning(f"[应用状态] 保存 {key} 失败: {exc}")
            return False

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(create_table_sql("app_state", if_not_exists=True))
