"""JSON file helpers with change detection."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional


_VOLATILE_COMPARE_KEYS = frozenset({
    "last_updated_time",
    "link_last_checked_time",
})


def read_json(file_path: str | Path) -> Optional[dict | list]:
    """Safely read a JSON file; return None when missing or malformed."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        logging.warning(f"文件不存在: {file_path}")
        return None
    except json.JSONDecodeError:
        logging.warning(f"JSON 格式错误: {file_path}")
        return None
    except Exception as exc:
        logging.warning(f"读取 JSON 文件时发生错误: {file_path}, 错误信息: {exc}")
        return None


def _content_for_compare(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _content_for_compare(item)
            for key, item in value.items()
            if key not in _VOLATILE_COMPARE_KEYS
        }
    if isinstance(value, list):
        return [_content_for_compare(item) for item in value]
    return value


def write_json(file_path: str | Path, data: Any) -> bool:
    """Write JSON, skipping the write when only volatile timestamps changed."""
    try:
        path = Path(file_path)
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as file:
                    existing = json.load(file)
                if _content_for_compare(existing) == _content_for_compare(data):
                    return True
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, separators=(",", ":"))
        return True
    except Exception as exc:
        logging.warning(f"写入 JSON 文件时发生错误: {file_path}, 错误信息: {exc}")
        return False
