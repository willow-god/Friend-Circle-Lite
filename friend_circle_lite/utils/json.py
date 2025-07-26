import json
import logging
from pathlib import Path
from typing import Any, Optional

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

def write_json(file_path: str | Path, data: Any) -> bool:
    """安全写入 JSON 文件，返回是否写入成功"""
    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.warning(f"写入 JSON 文件时发生错误: {file_path}, 错误信息: {str(e)}")
        return False
