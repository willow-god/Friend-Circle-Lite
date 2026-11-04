"""RSS/Atom 订阅源探测。"""

from __future__ import annotations

import logging

import requests

from friend_circle_lite.config.models import ProxySettings
from friend_circle_lite.crawler.http_client import DEFAULT_TIMEOUT, HEADERS_XML, WebFetchClient
from friend_circle_lite.domain.models import FeedEndpoint


class FeedDiscoveryService:
    """Discover an RSS or Atom endpoint for a website."""

    POSSIBLE_FEEDS = [
        ("rss1", "/feed"),        # WordPress / 最常见
        ("rss2", "/feed/"),       # WordPress 兼容写法
        ("rss3", "/rss.xml"),     # 很多传统站点
        ("rss4", "/atom.xml"),    # 静态博客常见（Hugo / Jekyll）
        ("rss5", "/feed.xml"),    # 通用型
        ("rss6", "/index.xml"),   # Hugo / 一些静态站
        ("rss7", "/feed.atom"),   # Atom 明确路径
        ("rss8", "/rss2.xml"),    # 老系统遗留
        ("rss9", "/rss/feed.xml"),# 少见但存在
        ("rss10", "/rss.php"),    # 老 PHP 程序
        ("rss11", "/feed.php"),   # 同上
    ]

    def __init__(self, session: requests.Session, proxy_settings: ProxySettings | None = None):
        self.session = session
        self.fetcher = WebFetchClient(session, proxy_settings)
        self.last_latency = 0.01

    def discover(self, website_url: str) -> FeedEndpoint | None:
        """Try common feed endpoints and return the first valid match."""
        for feed_type, path in self.POSSIBLE_FEEDS:
            feed_url = website_url.rstrip("/") + path
            result = self.fetcher.get(feed_url, headers=HEADERS_XML, timeout=DEFAULT_TIMEOUT, desc="RSS 探测")
            response = result.response

            if response is None or response.status_code != 200:
                continue

            content_type = response.headers.get("Content-Type", "").lower()
            if "xml" in content_type or "rss" in content_type or "atom" in content_type:
                return FeedEndpoint(url=feed_url, feed_type=feed_type, source="auto")

            text_head = response.text[:1000].lower()
            if "<rss" in text_head or "<feed" in text_head or "<rdf:rdf" in text_head:
                return FeedEndpoint(url=feed_url, feed_type=feed_type, source="auto")

        logging.warning(f"[RSS 探测] 未找到 {website_url} 的 RSS 订阅源")
        return None
