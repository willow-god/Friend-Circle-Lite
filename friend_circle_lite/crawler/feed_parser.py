"""RSS/Atom 文章解析。"""

from __future__ import annotations

import logging
from datetime import datetime

import feedparser
import requests

from friend_circle_lite.config.models import ProxySettings
from friend_circle_lite.crawler.http_client import DEFAULT_TIMEOUT, HEADERS_XML, WebFetchClient
from friend_circle_lite.domain.models import Article, normalize_latency
from friend_circle_lite.utils.time import format_published_time
from friend_circle_lite.utils.url import replace_non_domain


class FeedParserService:
    """Parse a discovered feed into normalized article objects."""

    def __init__(self, session: requests.Session, proxy_settings: ProxySettings | None = None):
        self.session = session
        self.fetcher = WebFetchClient(session, proxy_settings)
        self.last_latency = 0.01

    def parse(self, feed_url: str, count: int = 5, blog_url: str = "") -> list[Article]:
        """Parse a feed URL and return the newest `count` articles."""
        try:
            result = self.fetcher.get(feed_url, headers=HEADERS_XML, timeout=DEFAULT_TIMEOUT, desc="RSS 抓取")
            self.last_latency = normalize_latency(result.latency)
            if result.response is None:
                return []
            response = result.response
            # 强制使用 UTF-8 编码，因为 apparent_encoding 可能检测错误
            response.encoding = "utf-8"
            feed = feedparser.parse(response.text)
        except Exception as exc:
            logging.error(f"[RSS 抓取] 解析 RSS 失败：{feed_url}，错误: {exc}")
            return []

        default_author = feed.feed.author if "author" in feed.feed else ""
        articles: list[Article] = []

        for entry in feed.entries:
            published = self._extract_published_time(entry)
            article_link = replace_non_domain(entry.link, blog_url) if "link" in entry else ""
            article = Article(
                title=entry.title if "title" in entry else "",
                author=default_author,
                link=article_link,
                published=published,
                summary=entry.summary if "summary" in entry else "",
                content=entry.content[0].value if "content" in entry and entry.content else entry.description if "description" in entry else "",
            )
            articles.append(article)

        valid_articles = [article for article in articles if article.published]
        articles_with_dates: list[tuple[Article, datetime]] = []
        for article in valid_articles:
            try:
                articles_with_dates.append((article, datetime.strptime(article.published, "%Y-%m-%d %H:%M")))
            except ValueError:
                logging.warning(f"[RSS 抓取] 文章 {article.title} 的发布时间格式异常: {article.published}，已跳过")

        articles_with_dates.sort(key=lambda item: item[1], reverse=True)
        sorted_articles = [article for article, _ in articles_with_dates]
        return sorted_articles[:count]

    @staticmethod
    def _extract_published_time(entry) -> str:
        """Extract a normalized publish time from a feed entry."""
        import time

        def convert_time_to_string(time_value):
            """Convert various time formats to string."""
            if isinstance(time_value, str):
                return time_value
            if isinstance(time_value, time.struct_time):
                if time_value.tm_year < 1900:
                    logging.warning(f"[RSS 抓取] 文章 {entry.get('title', 'Unknown')} 的时间年份异常: {time_value.tm_year}，已跳过")
                    return ""
                return time.strftime('%Y-%m-%dT%H:%M:%SZ', time_value)
            logging.warning(f"[RSS 抓取] 文章 {entry.get('title', 'Unknown')} 的时间格式未知: {type(time_value)}，已跳过")
            return ""

        if "published" in entry:
            time_str = convert_time_to_string(entry.published)
            if not time_str:
                return ""
            return format_published_time(time_str)
        if "updated" in entry:
            time_str = convert_time_to_string(entry.updated)
            if not time_str:
                return ""
            published = format_published_time(time_str)
            logging.warning(f"[RSS 抓取] 文章 {entry.title} 未包含发布时间，已使用更新时间 {published}")
            return published

        logging.warning(f"[RSS 抓取] 文章 {entry.title} 未包含任何时间信息，请检查原文，跳过该文章")
        return ""
