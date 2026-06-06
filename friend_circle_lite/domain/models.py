"""Domain models for Friend-Circle-Lite.

These models centralize the core concepts used across the crawler so that the
transport layer, parsing logic, cache logic, and output formatting can evolve
independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class Website:
    """Represents a friend website entry from the upstream friend list."""

    name: str
    url: str
    avatar: str = ""
    linkpage: str = ""

    @classmethod
    def from_friend_item(cls, raw_friend: list | tuple | dict) -> "Website":
        """Create a website from common friend link structures."""
        if isinstance(raw_friend, dict):
            return cls(
                name=str(raw_friend.get("name", "")).strip(),
                url=str(raw_friend.get("link") or raw_friend.get("url") or "").strip(),
                avatar=str(raw_friend.get("avatar", "")).strip(),
                linkpage=str(raw_friend.get("linkpage", "")).strip(),
            )

        name = raw_friend[0]
        url = raw_friend[1]
        if len(raw_friend) > 3:
            linkpage = raw_friend[2]
            avatar = raw_friend[3]
        else:
            linkpage = ""
            avatar = raw_friend[2] if len(raw_friend) > 2 else ""
        return cls(name=str(name).strip(), url=str(url).strip(), avatar=str(avatar or "").strip(), linkpage=str(linkpage or "").strip())

    def to_error_payload(self) -> list[str]:
        """Return the legacy structure used by `errors.json`."""
        return [self.name, self.url, self.avatar]

    def to_public_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "url": self.url,
            "avatar": self.avatar,
            "linkpage": self.linkpage,
        }


@dataclass(slots=True)
class LinkMethodStatus:
    """Status for one link-check method."""

    success: bool = False
    status_code: int | None = None
    latency: float = -1

    def to_dict(self) -> dict[str, bool | int | float | None]:
        return {
            "success": self.success,
            "status_code": self.status_code,
            "latency": self.latency,
        }


@dataclass(slots=True)
class LinkCheckRecord:
    """Reachability status for one friend website."""

    name: str
    url: str
    avatar: str = ""
    linkpage: str = ""
    checked_at: str = ""
    reachable: bool = False
    crawl_allowed: bool = False
    best_method: str = "none"
    best_latency: float = -1
    fail_count: int = 0
    backlink_checked: bool = False
    has_author_link: bool = False
    rss_crawl_reason: str = "blocked_unreachable"
    direct: LinkMethodStatus = field(default_factory=LinkMethodStatus)
    proxy: LinkMethodStatus = field(default_factory=LinkMethodStatus)
    api: LinkMethodStatus = field(default_factory=LinkMethodStatus)

    @classmethod
    def unchecked(cls, website: Website, checked_at: str = "") -> "LinkCheckRecord":
        return cls(name=website.name, url=website.url, avatar=website.avatar, linkpage=website.linkpage, checked_at=checked_at)

    def to_public_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "url": self.url,
            "avatar": self.avatar,
            "linkpage": self.linkpage,
            "checked_at": self.checked_at,
            "reachable": self.reachable,
            "crawl_allowed": self.crawl_allowed,
            "best_method": self.best_method,
            "best_latency": self.best_latency,
            "fail_count": self.fail_count,
            "backlink_checked": self.backlink_checked,
            "has_author_link": self.has_author_link,
            "rss_crawl_reason": self.rss_crawl_reason,
            "methods": {
                "direct": self.direct.to_dict(),
                "proxy": self.proxy.to_dict(),
                "api": self.api.to_dict(),
            },
        }
    def to_link_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "link": self.url,
            "link_page": self.linkpage,
            "avatar": self.avatar,
            "reachable": self.reachable,
            "crawlable": self.crawl_allowed,
            "method": self.best_method,
            "latency": self.best_latency,
            "fail_count": self.fail_count,
            "checked_at": self.checked_at,
            "has_backlink": self.has_author_link if self.backlink_checked else None,
            "reason": self.rss_crawl_reason,
        }


@dataclass(slots=True)
class Article:
    """Represents one crawled article belonging to a website."""

    title: str
    author: str
    link: str
    published: str
    summary: str = ""
    content: str = ""
    avatar: str = ""

    def to_public_dict(self) -> dict[str, str]:
        """Return the legacy public article schema used by `all.json`."""
        return {
            "title": self.title,
            "created": self.published,
            "link": self.link,
            "author": self.author,
            "avatar": self.avatar,
        }

    def to_tracking_dict(self) -> dict[str, str]:
        """Return the article schema used by the latest article tracker."""
        return {
            "title": self.title,
            "author": self.author,
            "link": self.link,
            "published": self.published,
            "summary": self.summary,
            "content": self.content,
        }


@dataclass(slots=True)
class FeedEndpoint:
    """Represents a concrete feed endpoint and how it was found."""

    url: str
    feed_type: str
    source: str


@dataclass(slots=True)
class CacheRecord:
    """Represents one cached RSS endpoint mapping for a website."""

    name: str
    url: str
    source: str = "cache"

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "url": self.url,
        }


@dataclass(slots=True)
class CacheUpdate:
    """Describes how a crawl should update the persisted RSS cache."""

    action: str = "none"
    name: str | None = None
    url: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, str | None]:
        return {
            "action": self.action,
            "name": self.name,
            "url": self.url,
            "reason": self.reason,
        }


@dataclass(slots=True)
class CrawlResult:
    """Represents the crawl result for a single website."""

    website: Website
    status: str
    articles: list[Article] = field(default_factory=list)
    feed_url: str | None = None
    feed_type: str = "none"
    source_used: str = "none"
    cache_update: CacheUpdate = field(default_factory=CacheUpdate)

    def to_legacy_dict(self) -> dict[str, object]:
        return {
            "name": self.website.name,
            "status": self.status,
            "articles": [article.to_public_dict() for article in self.articles],
            "feed_url": self.feed_url,
            "feed_type": self.feed_type,
            "cache_update": self.cache_update.to_dict(),
            "source_used": self.source_used,
        }


@dataclass(slots=True)
class CrawlStatistics:
    """Aggregated crawl statistics for the generated `all.json` output."""

    friends_num: int = 0
    active_num: int = 0
    error_num: int = 0
    article_num: int = 0
    last_updated_time: str = ""

    @classmethod
    def create(cls, friends_num: int, active_num: int, error_num: int, article_num: int) -> "CrawlStatistics":
        return cls(
            friends_num=friends_num,
            active_num=active_num,
            error_num=error_num,
            article_num=article_num,
            last_updated_time=datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def to_dict(self) -> dict[str, int | str]:
        return {
            "friends_num": self.friends_num,
            "active_num": self.active_num,
            "error_num": self.error_num,
            "article_num": self.article_num,
            "last_updated_time": self.last_updated_time,
        }
