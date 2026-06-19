"""Configuration loading utilities."""

from __future__ import annotations

import logging

import yaml

from friend_circle_lite.config.models import ApplicationConfig

def load_raw_config(config_file: str) -> dict:
    """Load the raw YAML config dictionary from disk."""
    try:
        with open(config_file, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file) or {}
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
