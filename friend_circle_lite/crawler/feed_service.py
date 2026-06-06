"""RSS 发现、解析与文章更新追踪服务。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

from friend_circle_lite import HEADERS_XML, timeout
from friend_circle_lite.config.models import ProxySettings
from friend_circle_lite.crawler.http_client import WebFetchClient
from friend_circle_lite.domain.models import Article, FeedEndpoint, Website, normalize_latency
from friend_circle_lite.utils.time import format_published_time
from friend_circle_lite.utils.url import replace_non_domain


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
            result = self.fetcher.get(feed_url, headers=HEADERS_XML, timeout=timeout, desc="RSS 探测")
            response = result.response

            if response is None or response.status_code != 200:
                continue

            content_type = response.headers.get("Content-Type", "").lower()
            if "xml" in content_type or "rss" in content_type or "atom" in content_type:
                return FeedEndpoint(url=feed_url, feed_type=feed_type, source="auto")

            text_head = response.text[:1000].lower()
            if "<rss" in text_head or "<feed" in text_head or "<rdf:rdf" in text_head:
                return FeedEndpoint(url=feed_url, feed_type=feed_type, source="auto")

        logging.warning(f"未找到 {website_url} 的 RSS 订阅源")
        return None


class FeedParserService:
    """Parse a discovered feed into normalized article objects."""

    def __init__(self, session: requests.Session, proxy_settings: ProxySettings | None = None):
        self.session = session
        self.fetcher = WebFetchClient(session, proxy_settings)
        self.last_latency = 0.01

    def parse(self, feed_url: str, count: int = 5, blog_url: str = "") -> list[Article]:
        """Parse a feed URL and return the newest `count` articles.

        The returned articles are normalized to the project's internal domain
        model, while preserving the original public output fields.
        """
        try:
            result = self.fetcher.get(feed_url, headers=HEADERS_XML, timeout=timeout, desc="RSS 抓取")
            self.last_latency = normalize_latency(result.latency)
            if result.response is None:
                return []
            response = result.response
            # 强制使用 UTF-8 编码，因为 apparent_encoding 可能检测错误
            response.encoding = "utf-8"
            feed = feedparser.parse(response.text)
        except Exception as exc:
            logging.error(f"解析 RSS 失败：{feed_url}，错误: {exc}")
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
        
        # 过滤掉无法解析的日期格式
        def safe_parse_date(article):
            try:
                return datetime.strptime(article.published, "%Y-%m-%d %H:%M")
            except ValueError:
                logging.warning(f"文章 {article.title} 的发布时间格式异常: {article.published}，已跳过")
                return None
        
        # 只保留能成功解析日期的文章
        valid_articles_with_dates = []
        for article in valid_articles:
            parsed_date = safe_parse_date(article)
            if parsed_date:
                valid_articles_with_dates.append((article, parsed_date))
        
        # 按日期排序
        valid_articles_with_dates.sort(key=lambda item: item[1], reverse=True)
        sorted_articles = [item[0] for item in valid_articles_with_dates]
        
        return sorted_articles[:count] if count < len(sorted_articles) else sorted_articles

    @staticmethod
    def _extract_published_time(entry) -> str:
        """Extract a normalized publish time from a feed entry."""
        import time
        
        def convert_time_to_string(time_value):
            """Convert various time formats to string."""
            if isinstance(time_value, str):
                return time_value
            elif isinstance(time_value, time.struct_time):
                # 检查年份是否异常
                if time_value.tm_year < 1900:
                    logging.warning(f"文章 {entry.get('title', 'Unknown')} 的时间年份异常: {time_value.tm_year}，已跳过")
                    return ""
                return time.strftime('%Y-%m-%dT%H:%M:%SZ', time_value)
            else:
                logging.warning(f"文章 {entry.get('title', 'Unknown')} 的时间格式未知: {type(time_value)}，已跳过")
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
            logging.warning(f"文章 {entry.title} 未包含发布时间，已使用更新时间 {published}")
            return published

        logging.warning(f"文章 {entry.title} 未包含任何时间信息, 请检查原文, 跳过该文章")
        return ""


class LatestArticleTracker:
    """Track whether a website published new posts since the last crawl."""

    def __init__(self, storage_path: str | Path, max_tracked_articles: int = 10):
        from friend_circle_lite.storage.sqlite_store import ArticleTrackingStore
        self.store = ArticleTrackingStore(storage_path, max_tracked_articles)

    def diff_and_persist(self, latest_articles: list[Article]) -> list[dict] | None:
        """Return newly seen articles and update the local storage.
        
        Returns None if:
        - This is the first run (no previous data exists)
        - No new articles are found
        - New articles exist but are not newer than the most recent tracked article
        """
        previous_articles = self.store.load_articles()
        
        # First run: no previous data exists, skip sending to prevent sending old articles
        if not previous_articles:
            logging.info(f"首次运行：跳过推送以防止发送旧文章")
            self.store.save_articles(latest_articles)
            return None
        
        previous_latest_date = self._get_latest_date(previous_articles)
        
        # Find articles that are truly new (check only: link, title, published)
        new_articles = []
        for article in latest_articles:
            if self._is_truly_new_article(article, previous_articles):
                new_articles.append(article)
        
        if not new_articles:
            self.store.save_articles(latest_articles)
            return None
        
        # Filter new articles: only keep those newer than the previous latest date
        truly_new_articles = []
        for article in new_articles:
            if not article.published:
                continue
            try:
                article_date = datetime.strptime(article.published, "%Y-%m-%d %H:%M")
                if previous_latest_date is None or article_date > previous_latest_date:
                    truly_new_articles.append(article)
            except Exception as exc:
                logging.warning(f"解析文章日期失败: {article.title}, 日期: {article.published}, 错误: {exc}")
                continue
        
        self.store.save_articles(latest_articles)
        
        if truly_new_articles:
            logging.info(f"发现 {len(truly_new_articles)} 篇新文章（日期比之前更新）")
            return [article.to_tracking_dict() for article in truly_new_articles]
        else:
            logging.info(f"发现 {len(new_articles)} 篇新文章，但日期不够新，跳过推送")
            return None

    @staticmethod
    def _is_truly_new_article(article: Article, previous_articles: list[Article]) -> bool:
        """Check if an article is truly new by comparing link, title, and published date.
        
        An article is considered new only if its link, title, and published date
        do not match any previous article (empty values are skipped).
        """
        for prev in previous_articles:
            # Check link, title, and published: if any non-empty field matches, it's not new
            if article.link and article.link == prev.link:
                return False
            if article.title and article.title == prev.title:
                return False
            if article.published and article.published == prev.published:
                return False
        
        return True

    @staticmethod
    def _get_latest_date(articles: list[Article]) -> datetime | None:
        """Find the latest publish date from a list of articles."""
        latest_date = None
        for article in articles:
            if not article.published:
                continue
            try:
                article_date = datetime.strptime(article.published, "%Y-%m-%d %H:%M")
                if latest_date is None or article_date > latest_date:
                    latest_date = article_date
            except Exception:
                continue
        return latest_date


def extract_blog_origin(url: str) -> str:
    """Return a normalized origin for display or author profile links."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"
