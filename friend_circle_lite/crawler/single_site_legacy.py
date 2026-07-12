"""Legacy-compatible single website helpers.

The project now uses dedicated domain models and services, but these helpers are
kept as a compatibility layer because existing entrypoints still import them.
"""

from __future__ import annotations

import logging

import requests

from friend_circle_lite.crawler.feed_service import FeedDiscoveryService, FeedParserService, LatestArticleTracker
from friend_circle_lite.domain.models import CacheUpdate, Website

def check_feed(blog_url, session):
    """Return the discovered feed type and URL in the historical tuple format."""
    endpoint = FeedDiscoveryService(session).discover(blog_url)
    if endpoint is None:
        return ["none", blog_url]
    return [endpoint.feed_type, endpoint.url]

def parse_feed(url, session, count=5, blog_url=''):
    """Parse a feed and return the historical dictionary structure."""
    articles = FeedParserService(session).parse(url, count=count, blog_url=blog_url)
    return {
        'website_name': '',
        'author': articles[0].author if articles else '',
        'link': '',
        'articles': [article.to_tracking_dict() for article in articles],
    }

def process_friend(friend, session: requests.Session, count: int, specific_and_cache=None):
    """Crawl one friend entry and return the historical result shape."""
    if specific_and_cache is None:
        specific_and_cache = []

    try:
        website = Website.from_friend_item(friend)
    except Exception:
        logging.error(f"friend 数据格式不正确: {friend!r}")
        return {
            'name': None,
            'status': 'error',
            'articles': [],
            'feed_url': None,
            'feed_type': 'none',
            'cache_update': CacheUpdate(action='none', name=None, url=None, reason='bad_friend_data').to_dict(),
            'source_used': 'none',
        }

    rss_lookup = {entry['name']: entry for entry in specific_and_cache if entry.get('name') and entry.get('url')}
    entry = rss_lookup.get(website.name)

    endpoint = None
    cache_update = CacheUpdate(action='none', name=website.name)
    if entry:
        source = entry.get('source', 'unknown')
        endpoint = {'feed_type': 'specific', 'url': entry['url'], 'source': source}
        if source == 'manual':
            logging.info(f"'{website.name}' 使用预设 RSS 源：{entry['url']}")
        elif source == 'cache':
            logging.info(f"'{website.name}' 使用缓存 RSS 源：{entry['url']}")
        else:
            logging.info(f"'{website.name}' 使用 RSS 源：{entry['url']} (来源: {source})")
    else:
        feed_type, feed_url = check_feed(website.url, session)
        if feed_type != 'none' and feed_url:
            endpoint = {'feed_type': feed_type, 'url': feed_url, 'source': 'auto'}
            cache_update = CacheUpdate(action='set', name=website.name, url=feed_url, reason='auto_discovered')
            logging.info(f"'{website.name}' 自动探测到 RSS：{feed_url}")

    articles = []
    parse_error = endpoint is not None
    if endpoint:
        parsed = FeedParserService(session).parse(endpoint['url'], count=count, blog_url=website.url)
        articles = [
            {
                'title': article.title,
                'created': article.published,
                'link': article.link,
                'author': website.name,
                'avatar': website.avatar,
            }
            for article in parsed
        ]
        parse_error = not articles

    if parse_error and endpoint and endpoint['source'] in ('cache', 'unknown'):
        logging.warning(f"'{website.name}' 缓存的 RSS 源无效，尝试重新探测...")
        new_feed_type, new_feed_url = check_feed(website.url, session)
        if new_feed_type != 'none' and new_feed_url:
            reparsed = FeedParserService(session).parse(new_feed_url, count=count, blog_url=website.url)
            articles = [
                {
                    'title': article.title,
                    'created': article.published,
                    'link': article.link,
                    'author': website.name,
                    'avatar': website.avatar,
                }
                for article in reparsed
            ]
            if articles:
                endpoint = {'feed_type': new_feed_type, 'url': new_feed_url, 'source': 'auto'}
                cache_update = CacheUpdate(action='set', name=website.name, url=new_feed_url, reason='repair_cache')
                logging.info(f"'{website.name}' 重新探测成功，更新缓存：{new_feed_url}")
            else:
                endpoint = None
                cache_update = CacheUpdate(action='delete', name=website.name, url=None, reason='remove_invalid')
                logging.warning(f"'{website.name}' 重新探测失败，删除无效缓存")
        else:
            endpoint = None
            cache_update = CacheUpdate(action='delete', name=website.name, url=None, reason='remove_invalid')
            logging.warning(f"'{website.name}' 未找到有效 RSS，删除无效缓存")

    return {
        'name': website.name,
        'status': 'active' if articles else 'error',
        'articles': articles,
        'feed_url': endpoint['url'] if endpoint else None,
        'feed_type': endpoint['feed_type'] if endpoint else 'none',
        'cache_update': cache_update.to_dict(),
        'source_used': endpoint['source'] if endpoint else 'none',
    }

def get_latest_articles_from_link(url, count=5, last_articles_path="./temp/newest_posts.json"):
    """Return newly published articles relative to the last local snapshot."""
    session = requests.Session()
    feed_type, feed_url = check_feed(url, session)
    if feed_type == 'none':
        logging.error(f"无法获取 {url} 的文章数据")
        return None

    latest_articles = FeedParserService(session).parse(feed_url, count=count, blog_url=url)
    updated_articles = LatestArticleTracker(last_articles_path).diff_and_persist(latest_articles)
    logging.info(
        f"从 {url} 获取到 {len(latest_articles)} 篇文章，其中 {0 if updated_articles is None else len(updated_articles)} 篇为新文章"
    )
    return updated_articles

