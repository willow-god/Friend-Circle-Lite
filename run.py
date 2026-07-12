"""Friend-Circle-Lite application entrypoint."""

from __future__ import annotations

import logging

from friend_circle_lite.cli import FriendCircleLiteApplication
from friend_circle_lite.utils.config import load_config


def configure_logging() -> None:
    """Configure the global logging style used by the CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="😋 %(levelname)s: %(message)s",
    )


def main() -> None:
    """Load configuration and run the application."""
    configure_logging()
    app = FriendCircleLiteApplication(load_config("./conf.yaml"))
    app.run()


if __name__ == "__main__":
    main()
