"""Configuration loading utilities."""

from __future__ import annotations

import copy
import logging
import os

import yaml

from friend_circle_lite.config.models import ApplicationConfig


CONFIG_OVERRIDE_ENV_NAME = "FCL_CONFIG_OVERRIDES"


def _config_overrides_from_env() -> str:
    """Return the first configured environment override block."""
    return os.getenv(CONFIG_OVERRIDE_ENV_NAME, "")


def _parse_config_overrides(raw: str) -> dict:
    """Parse dotted YAML paths from a line-oriented environment value."""
    overrides: dict = {}
    for line_number, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            logging.warning("配置覆盖第 %s 行格式无效，已忽略", line_number)
            continue
        path, value_text = (part.strip() for part in line.split("=", 1))
        path_parts = [part.strip() for part in path.split(".") if part.strip()]
        if not path_parts or any(part.startswith("__") for part in path_parts):
            logging.warning("配置覆盖第 %s 行路径无效，已忽略", line_number)
            continue
        try:
            value = yaml.safe_load(value_text) if value_text else ""
        except yaml.YAMLError:
            logging.warning("配置覆盖第 %s 行的值无法解析，已忽略", line_number)
            continue
        target = overrides
        for part in path_parts[:-1]:
            current = target.get(part)
            if not isinstance(current, dict):
                current = {}
                target[part] = current
            target = current
        target[path_parts[-1]] = value
    return overrides


def _apply_config_overrides(config: dict, raw: str) -> dict:
    """Apply environment overrides without mutating the YAML-loaded object."""
    overrides = _parse_config_overrides(raw)
    if not overrides:
        return config
    merged = copy.deepcopy(config)

    def merge(target: dict, source: dict) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value

    merge(merged, overrides)
    logging.info("已应用 %s 个环境配置覆盖项", sum(1 for _ in _flatten_override_paths(overrides)))
    return merged


def _flatten_override_paths(value: dict, prefix: str = ""):
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            yield from _flatten_override_paths(child, path)
        else:
            yield path

def load_raw_config(config_file: str) -> dict:
    """Load the raw YAML config dictionary from disk."""
    try:
        with open(config_file, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file) or {}
            override_block = _config_overrides_from_env()
            return _apply_config_overrides(config, override_block) if override_block else config
    except FileNotFoundError:
        logging.error(f"配置文件 {config_file} 未找到")
        return {}
    except yaml.YAMLError as e:
        logging.error(f"YAML解析错误: {str(e)}")
        return {}
    except Exception as e:
        logging.error(f"加载配置文件时发生未知错误: {str(e)}")
        return {}


def load_config(config_file: str) -> ApplicationConfig:
    """Load and validate the application configuration as typed objects."""
    return ApplicationConfig.from_dict(load_raw_config(config_file))
