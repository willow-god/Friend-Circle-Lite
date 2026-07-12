"""Backward-compatible storage exports.

New code should import from `friend_circle_lite.storage.sqlite_store`.
"""

from friend_circle_lite.storage.sqlite_store import *  # noqa: F401,F403
