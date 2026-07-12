"""Backward-compatible application entrypoint exports.

New code should import from `friend_circle_lite.cli`.
"""

from friend_circle_lite.cli import FriendCircleLiteApplication  # noqa: F401
