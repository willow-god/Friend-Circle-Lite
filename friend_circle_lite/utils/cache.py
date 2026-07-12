"""Backward-compatible cache helpers.

The crawler now stores feed cache records as YAML through `FeedCacheStore`.
These wrappers keep the old function names available for any external callers.
"""

from friend_circle_lite.domain.models import CacheRecord
from friend_circle_lite.storage.sqlite_store import FeedCacheStore


def load_cache(cache_file: str):
    """Load cache records and expose the legacy list-of-dicts structure."""
    records = FeedCacheStore(cache_file).load_records()
    return [{"name": item.name, "url": item.url, "source": item.source} for item in records]


def save_cache(cache_file: str, cache_items: list[dict]):
    """Persist cache records while accepting the legacy input structure."""
    records = [
        CacheRecord(name=item["name"], url=item["url"], source=item.get("source", "cache"))
        for item in cache_items
        if item.get("name") and item.get("url")
    ]
    return FeedCacheStore(cache_file).save_records(records)
