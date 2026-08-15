import json
import logging
from pathlib import Path
from typing import Any, Optional

_VOLATILE_COMPARE_KEYS = frozenset({
    "last_updated_time",
    "link_last_checked_time",
})


def read_json(file_path: str | Path) -> Optional[dict | list]:
    """安全读取 JSON 文件，如果文件不存在或格式错误则返回 None"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"文件不存在: {file_path}")
        return None
    except json.JSONDecodeError:
        logging.warning(f"JSON 格式错误: {file_path}")
        return None
    except Exception as e:
        logging.warning(f"读取 JSON 文件时发生错误: {file_path}, 错误信息: {str(e)}")
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
    """安全写入 JSON 文件，返回是否写入成功"""
    try:
        path = Path(file_path)
        if path.is_file():
            try:
                with path.open('r', encoding='utf-8') as f:
                    existing = json.load(f)
                if _content_for_compare(existing) == _content_for_compare(data):
                    return True
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        return True
    except Exception as e:
        logging.warning(f"写入 JSON 文件时发生错误: {file_path}, 错误信息: {str(e)}")
        return False
