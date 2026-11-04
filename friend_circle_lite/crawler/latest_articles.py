"""获取指定博客的最新文章，用于邮件订阅推送。"""

from __future__ import annotations

import logging

import requests

from friend_circle_lite.crawler.article_tracker import LatestArticleTracker
from friend_circle_lite.crawler.feed_discovery import FeedDiscoveryService
from friend_circle_lite.crawler.feed_parser import FeedParserService


def get_latest_articles_from_link(url: str, count: int = 5, last_articles_path: str = "./temp/newest_posts.json"):
    """Return newly published articles relative to the last local snapshot."""
    with requests.Session() as session:
        endpoint = FeedDiscoveryService(session).discover(url)
        if endpoint is None:
            logging.error(f"无法获取 {url} 的文章数据")
            return None
        latest_articles = FeedParserService(session).parse(endpoint.url, count=count, blog_url=url)

    updated_articles = LatestArticleTracker(last_articles_path).diff_and_persist(latest_articles)
    logging.info(
        f"从 {url} 获取到 {len(latest_articles)} 篇文章，"
        f"其中 {0 if updated_articles is None else len(updated_articles)} 篇为新文章"
    )
    return updated_articles
