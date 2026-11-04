"""Command-line entrypoint."""

from __future__ import annotations

import logging

from friend_circle_lite.application import FriendCircleLiteApplication
from friend_circle_lite.config.loader import load_config


def configure_logging() -> None:
    """Configure the global logging style used by the CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="😋 %(levelname)s: %(message)s",
    )


def main(config_file: str = "./conf.yaml") -> None:
    """Load configuration and run the application."""
    configure_logging()
    FriendCircleLiteApplication(load_config(config_file)).run()
