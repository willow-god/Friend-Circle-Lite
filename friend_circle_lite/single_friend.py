import logging
from datetime import datetime
import re
import os
import json
import requests
import feedparser
from friend_circle_lite import HEADERS_XML, timeout
from friend_circle_lite.utils.time import format_published_time
from friend_circle_lite.utils.url import replace_non_domain

def check_feed(blog_url, session):
    """
    检查博客的 RSS 或 Atom 订阅链接。

    优化点：
    - 检查 HTTP 状态码。
    - 检查 Content-Type 是否包含 xml / rss / atom。
    - 检查响应内容前几百字节内是否有 RSS/Atom 的特征标签。
    """
    possible_feeds = [
        ('atom', '/atom.xml'),
        ('rss', '/rss.xml'),  # 2024-07-26 添加 /rss.xml内容的支持
        ('rss2', '/rss2.xml'),
        ('rss3', '/rss.php'),  # 2024-12-07 添加 /rss.php内容的支持
        ('feed', '/feed'),
        ('feed2', '/feed.xml'),  # 2024-07-26 添加 /feed.xml内容的支持
        ('feed3', '/feed/'),
        ('feed4', '/feed.php'),  # 2025-07-22 添加 /feed.php内容的支持
        ('index', '/index.xml')  # 2024-07-25 添加 /index.xml内容的支持
    ]

    for feed_type, path in possible_feeds:
        feed_url = blog_url.rstrip('/') + path
        try:
            response = session.get(feed_url, headers=HEADERS_XML, timeout=timeout)
            if response.status_code == 200:
                # 检查 Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                    return [feed_type, feed_url]
                
                # 如果 Content-Type 是 text/html 或未明确，但内容本身是 RSS
                text_head = response.text[:1000].lower()  # 读取前1000字符
                if ('<rss' in text_head or '<feed' in text_head or '<rdf:rdf' in text_head):
                    return [feed_type, feed_url]
        except requests.RequestException:
            continue

    logging.warning(f"无法找到 {blog_url} 的订阅链接")
    return ['none', blog_url]

def parse_feed(url, session, count=5, blog_url=''):
    """
    解析 Atom 或 RSS2 feed 并返回包含网站名称、作者、原链接和每篇文章详细内容的字典。

    此函数接受一个 feed 的地址（atom.xml 或 rss2.xml），解析其中的数据，并返回一个字典结构，
    其中包括网站名称、作者、原链接和每篇文章的详细内容。

    参数：
    url (str): Atom 或 RSS2 feed 的 URL。
    session (requests.Session): 用于请求的会话对象。
    count (int): 获取文章数的最大数。如果小于则全部获取，如果文章数大于则只取前 count 篇文章。

    返回：
    dict: 包含网站名称、作者、原链接和每篇文章详细内容的字典。
    """
    try:
        response = session.get(url, headers=HEADERS_XML, timeout=timeout)
        response.encoding = response.apparent_encoding or 'utf-8'
        feed = feedparser.parse(response.text)
        
        result = {
            'website_name': feed.feed.title if 'title' in feed.feed else '', # type: ignore
            'author': feed.feed.author if 'author' in feed.feed else '', # type: ignore
            'link': feed.feed.link if 'link' in feed.feed else '', # type: ignore
            'articles': []
        }
        
        for _ , entry in enumerate(feed.entries):
            
            if 'published' in entry:
                published = format_published_time(entry.published)
            elif 'updated' in entry:
                published = format_published_time(entry.updated)
                # 输出警告信息
                logging.warning(f"文章 {entry.title} 未包含发布时间，已使用更新时间 {published}")
            else:
                published = ''
                logging.warning(f"文章 {entry.title} 未包含任何时间信息, 请检查原文, 设置为默认时间")
            
            # 处理链接中可能存在的错误，比如ip或localhost
            article_link = replace_non_domain(entry.link, blog_url) if 'link' in entry else '' # type: ignore
            
            article = {
                'title': entry.title if 'title' in entry else '',
                'author': result['author'],
                'link': article_link,
                'published': published,
                'summary': entry.summary if 'summary' in entry else '',
                'content': entry.content[0].value if 'content' in entry and entry.content else entry.description if 'description' in entry else ''
            }
            result['articles'].append(article)
        
        # 对文章按时间排序，并只取前 count 篇文章
        result['articles'] = sorted(result['articles'], key=lambda x: datetime.strptime(x['published'], '%Y-%m-%d %H:%M'), reverse=True)
        if count < len(result['articles']):
            result['articles'] = result['articles'][:count]
        
        return result
    except Exception as e:
        logging.error(f"无法解析FEED地址：{url} ，请自行排查原因！错误信息: {str(e)}")
        return {
            'website_name': '',
            'author': '',
            'link': '',
            'articles': []
        }

def process_friend(friend, session: requests.Session, count: int, specific_and_cache=None):
    """
    处理单个朋友的博客信息。
    
    参数：
        friend (list/tuple): [name, blog_url, avatar]
        session (requests.Session): 请求会话
        count (int): 每个博客最大文章数
        specific_and_cache (list[dict]): [{name, url, source?}]，合并后的特殊 + 缓存列表
    
    返回：
        {
            'name': name,
            'status': 'active' | 'error',
            'articles': [...],
            'feed_url': str | None,
            'feed_type': str,
            'cache_update': {
                'action': 'set' | 'delete' | 'none',
                'name': name,
                'url': feed_url_or_None,
                'reason': 'auto_discovered' | 'repair_cache' | 'remove_invalid',
            },
            'source_used': 'manual' | 'cache' | 'auto' | 'none'
        }
    """
    if specific_and_cache is None:
        specific_and_cache = []

    # 解包 friend
    try:
        name, blog_url, avatar = friend
    except Exception:
        logging.error(f"friend 数据格式不正确: {friend!r}")
        return {
            'name': None,
            'status': 'error',
            'articles': [],
            'feed_url': None,
            'feed_type': 'none',
            'cache_update': {'action': 'none', 'name': None, 'url': None, 'reason': 'bad_friend_data'},
            'source_used': 'none',
        }

    rss_lookup = {e['name']: e for e in specific_and_cache if 'name' in e and 'url' in e}
    cache_update = {'action': 'none', 'name': name, 'url': None, 'reason': ''}
    feed_url, feed_type, source_used = None, 'none', 'none'

    # ---- 1. 优先使用 specific 或 cache ----
    entry = rss_lookup.get(name)
    if entry:
        feed_url = entry['url']
        feed_type = 'specific'
        source_used = entry.get('source', 'unknown')
        logging.info(f"“{name}” 使用预设 RSS 源：{feed_url} （source={source_used}）。")
    else:
        # ---- 2. 自动探测 ----
        feed_type, feed_url = check_feed(blog_url, session)
        source_used = 'auto'
        logging.info(f"“{name}” 自动探测 RSS：type：{feed_type}, url：{feed_url} 。")

        if feed_type != 'none' and feed_url:
            cache_update = {'action': 'set', 'name': name, 'url': feed_url, 'reason': 'auto_discovered'}

    # ---- 3. 尝试解析 RSS ----
    articles, parse_error = [], False
    if feed_type != 'none' and feed_url:
        try:
            feed_info = parse_feed(feed_url, session, count, blog_url)
            if isinstance(feed_info, dict) and 'articles' in feed_info:
                articles = [
                    {
                        'title': a['title'],
                        'created': a['published'],
                        'link': a['link'],
                        'author': name,
                        'avatar': avatar,
                    }
                    for a in feed_info['articles']
                ]

                for a in articles:
                    logging.info(f"{name} 发布了新文章：{a['title']}，时间：{a['created']}，链接：{a['link']}")
            else:
                parse_error = True
        except Exception as e:
            logging.warning(f"解析 RSS 失败（{name} -> {feed_url}）：{e}")
            parse_error = True

    # ---- 4. 如果缓存 RSS 无效则重新探测 ----
    if parse_error and source_used in ('cache', 'unknown'):
        logging.info(f"缓存 RSS 无效，重新探测：{name} ({blog_url})。")
        new_type, new_url = check_feed(blog_url, session)
        if new_type != 'none' and new_url:
            try:
                feed_info = parse_feed(new_url, session, count, blog_url)
                if isinstance(feed_info, dict) and 'articles' in feed_info:
                    articles = [
                        {
                            'title': a['title'],
                            'created': a['published'],
                            'link': a['link'],
                            'author': name,
                            'avatar': avatar,
                        }
                        for a in feed_info['articles']
                    ]

                    for a in articles:
                        logging.info(f"{name} 发布了新文章：{a['title']}，时间：{a['created']}，链接：{a['link']}")

                    feed_type, feed_url, source_used = new_type, new_url, 'auto'
                    cache_update = {'action': 'set', 'name': name, 'url': new_url, 'reason': 'repair_cache'}
                    parse_error = False
            except Exception as e:
                logging.warning(f"重新探测解析仍失败：{name} ({new_url})：{e}")
                cache_update = {'action': 'delete', 'name': name, 'url': None, 'reason': 'remove_invalid'}
                feed_type, feed_url = 'none', None
        else:
            cache_update = {'action': 'delete', 'name': name, 'url': None, 'reason': 'remove_invalid'}
            feed_type, feed_url = 'none', None

    # ---- 5. 最终状态 ----
    status = 'active' if articles else 'error'
    if not articles:
        if feed_type == 'none':
            logging.warning(f"{name} 的博客 {blog_url} 未找到有效 RSS。")
        else:
            logging.warning(f"{name} 的 RSS {feed_url} 未解析出文章。")

    return {
        'name': name,
        'status': status,
        'articles': articles,
        'feed_url': feed_url,
        'feed_type': feed_type,
        'cache_update': cache_update,
        'source_used': source_used,
    }

def get_latest_articles_from_link(url, count=5, last_articles_path="./temp/newest_posts.json"):
    """
    从指定链接获取最新的文章数据并与本地存储的上次的文章数据进行对比。

    参数：
    url (str): 用于获取文章数据的链接。
    count (int): 获取文章数的最大数。如果小于则全部获取，如果文章数大于则只取前 count 篇文章。

    返回：
    list: 更新的文章列表，如果没有更新的文章则返回 None。
    """
    # 本地存储上次文章数据的文件
    local_file = last_articles_path
    
    # 检查和解析 feed
    session = requests.Session()
    feed_type, feed_url = check_feed(url, session)
    if feed_type == 'none':
        logging.error(f"无法获取 {url} 的文章数据")
        return None

    # 获取最新的文章数据
    latest_data = parse_feed(feed_url, session ,count)
    latest_articles = latest_data['articles']
    
    # 读取本地存储的上次的文章数据
    if os.path.exists(local_file):
        with open(local_file, 'r', encoding='utf-8') as file:
            last_data = json.load(file)
    else:
        last_data = {'articles': []}
    
    last_articles = last_data['articles']

    # 找到更新的文章
    updated_articles = []
    last_titles = {article['link'] for article in last_articles}

    for article in latest_articles:
        if article['link'] not in last_titles:
            updated_articles.append(article)
    
    logging.info(f"从 {url} 获取到 {len(latest_articles)} 篇文章，其中 {len(updated_articles)} 篇为新文章")

    # 更新本地存储的文章数据
    with open(local_file, 'w', encoding='utf-8') as file:
        json.dump({'articles': latest_articles}, file, ensure_ascii=False, indent=4)
    
    # 如果有更新的文章，返回这些文章，否则返回 None
    return updated_articles if updated_articles else None

