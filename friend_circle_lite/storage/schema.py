"""Central SQLite schema definitions.

Keeping every table definition in one place avoids drift between the runtime
stores and the debug dumper's schema repair logic.
"""

from __future__ import annotations


CREATE_FEED_CACHE = """
CREATE TABLE feed_cache (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'cache'
)
"""

CREATE_ARTICLE_TRACKING = """
CREATE TABLE article_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    link TEXT NOT NULL,
    published TEXT NOT NULL,
    summary TEXT,
    content TEXT
)
"""

# `fail_count` is intentionally absent: unreachable duration is derived from
# `unreachable_since`, and keeping the retired column only caused schema drift.
CREATE_LINK_CHECK_STATE = """
CREATE TABLE link_check_state (
    url TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar TEXT DEFAULT '',
    linkpage TEXT DEFAULT '',
    checked_at TEXT NOT NULL,
    reachable INTEGER NOT NULL DEFAULT 0,
    crawl_allowed INTEGER NOT NULL DEFAULT 0,
    best_method TEXT NOT NULL DEFAULT 'none',
    best_latency REAL DEFAULT -1,
    backlink_checked INTEGER NOT NULL DEFAULT 0,
    has_author_link INTEGER NOT NULL DEFAULT 0,
    rss_crawl_reason TEXT NOT NULL DEFAULT '',
    last_post_published TEXT DEFAULT '',
    last_post_days_ago INTEGER,
    unreachable_since TEXT DEFAULT '',
    rss_unavailable_since TEXT DEFAULT '',
    direct_success INTEGER NOT NULL DEFAULT 0,
    direct_status_code INTEGER,
    direct_latency REAL DEFAULT -1,
    proxy_success INTEGER NOT NULL DEFAULT 0,
    proxy_status_code INTEGER,
    proxy_latency REAL DEFAULT -1,
    api_success INTEGER NOT NULL DEFAULT 0,
    api_status_code INTEGER,
    api_latency REAL DEFAULT -1
)
"""

CREATE_APP_STATE = """
CREATE TABLE app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


TABLE_SCHEMAS: dict[str, tuple[list[str], str]] = {
    "feed_cache": (["name", "url", "source"], CREATE_FEED_CACHE),
    "article_tracking": (
        ["id", "title", "author", "link", "published", "summary", "content"],
        CREATE_ARTICLE_TRACKING,
    ),
    "link_check_state": (
        [
            "url",
            "name",
            "avatar",
            "linkpage",
            "checked_at",
            "reachable",
            "crawl_allowed",
            "best_method",
            "best_latency",
            "backlink_checked",
            "has_author_link",
            "rss_crawl_reason",
            "last_post_published",
            "last_post_days_ago",
            "unreachable_since",
            "rss_unavailable_since",
            "direct_success",
            "direct_status_code",
            "direct_latency",
            "proxy_success",
            "proxy_status_code",
            "proxy_latency",
            "api_success",
            "api_status_code",
            "api_latency",
        ],
        CREATE_LINK_CHECK_STATE,
    ),
    "app_state": (["key", "value"], CREATE_APP_STATE),
}


DEFAULT_EXPRESSIONS: dict[str, str] = {
    "key": "''",
    "value": "''",
    "id": "NULL",
    "name": "''",
    "url": "''",
    "source": "'cache'",
    "title": "''",
    "author": "''",
    "link": "''",
    "published": "''",
    "summary": "NULL",
    "content": "NULL",
    "avatar": "''",
    "linkpage": "''",
    "checked_at": "''",
    "reachable": "0",
    "crawl_allowed": "0",
    "best_method": "'none'",
    "best_latency": "-1",
    "backlink_checked": "0",
    "has_author_link": "0",
    "rss_crawl_reason": "''",
    "last_post_published": "''",
    "last_post_days_ago": "NULL",
    "unreachable_since": "''",
    "rss_unavailable_since": "''",
    "direct_success": "0",
    "direct_status_code": "NULL",
    "direct_latency": "-1",
    "proxy_success": "0",
    "proxy_status_code": "NULL",
    "proxy_latency": "-1",
    "api_success": "0",
    "api_status_code": "NULL",
    "api_latency": "-1",
}


def create_table_sql(table: str, *, if_not_exists: bool = False) -> str:
    """Return the CREATE TABLE statement for a known table."""
    create_sql = TABLE_SCHEMAS[table][1]
    if not if_not_exists:
        return create_sql
    return create_sql.replace(
        f"CREATE TABLE {table}",
        f"CREATE TABLE IF NOT EXISTS {table}",
        1,
    )
