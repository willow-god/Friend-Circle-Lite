import logging
from datetime import datetime, timedelta, timezone
from dateutil import parser
import requests
import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlunparse, urljoin
import ipaddress
import socket

# 设置日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 标准化的请求头
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

timeout = (10, 15) # 连接超时和读取超时，防止requests接受时间过长

def format_published_time(time_str):
    """
    格式化发布时间为统一格式 YYYY-MM-DD HH:MM

    参数:
    time_str (str): 输入的时间字符串，可能是多种格式。

    返回:
    str: 格式化后的时间字符串，若解析失败返回空字符串。
    """
    try:
        parsed_time = parser.parse(time_str, fuzzy=True)
        # 如果没有时区信息，则将其视为 UTC
        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
        
        # 转换为上海时区（UTC+8）
        shanghai_time = parsed_time.astimezone(timezone(timedelta(hours=8)))
        return shanghai_time.strftime('%Y-%m-%d %H:%M')
    
    except (ValueError, parser.ParserError):
        logging.warning(f"无法解析时间字符串：{time_str}")
        return ''

def check_feed(blog_url, session):
    """
    检查博客的 RSS 或 Atom 订阅链接。

    此函数接受一个博客地址，尝试在其后拼接 '/atom.xml', '/rss2.xml' 和 '/feed'，并检查这些链接是否可访问。
    Atom 优先，如果都不能访问，则返回 ['none', 源地址]。

    参数：
    blog_url (str): 博客的基础 URL。
    session (requests.Session): 用于请求的会话对象。

    返回：
    list: 包含类型和拼接后的链接的列表。如果 atom 链接可访问，则返回 ['atom', atom_url]；
            如果 rss2 链接可访问，则返回 ['rss2', rss_url]；
            如果 feed 链接可访问，则返回 ['feed', feed_url]；
            如果都不可访问，则返回 ['none', blog_url]。
    """
    possible_feeds = [
        ('atom', '/atom.xml'),
        ('rss', '/rss.xml'), # 2024-07-26 添加 /rss.xml内容的支持
        ('rss2', '/rss2.xml'),
        ('feed', '/feed'),
        ('feed2', '/feed.xml'), # 2024-07-26 添加 /feed.xml内容的支持
        ('feed3', '/feed/'),
        ('index', '/index.xml') # 2024-07-25 添加 /index.xml内容的支持
    ]

    for feed_type, path in possible_feeds:
        feed_url = blog_url.rstrip('/') + path
        # 确保 feed_url 使用 https 协议
        feed_url = ensure_https(feed_url)
        try:
            response = session.get(feed_url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return [feed_type, feed_url]
        except requests.RequestException:
            continue

    return ['none', blog_url]

def is_bad_link(link):
    """
    判断链接是否是IP地址+端口、localhost+端口或缺少域名的链接

    参数：
    link (str): 要检查的链接

    返回：
    bool: 如果是IP地址+端口、localhost+端口或缺少域名，返回True；否则返回False
    """
    try:
        parsed_url = urlparse(link)
        netloc = parsed_url.netloc

        if not netloc:
            return True  # 缺少主机部分

        # 分割出主机和端口
        if ':' in netloc:
            host, _ = netloc.split(':', 1)
        else:
            host = netloc

        # 检查是否是localhost或环回地址127.0.0.1，包括IPv6的 ::1
        if host in ['localhost', '::1', '127.0.0.1']:
            return True

        # 检查是否是IP地址
        try:
            ip = ipaddress.ip_address(host)
            if socket.inet_aton(host) or ip.is_private or ip.is_loopback:
                return True
            return False
        except ValueError:
            return False

    except Exception:
        return False

def ensure_https(url):
    """
    确保链接使用 https 协议

    参数：
    url (str): 原始链接

    返回：
    str: 使用 https 协议的链接
    """
    parsed_url = urlparse(url)
    if parsed_url.scheme != 'https':
        parsed_url = parsed_url._replace(scheme='https')
        return urlunparse(parsed_url)
    return url

def fix_link(link, blog_url):
    """
    修复链接，将IP地址、localhost或缺少域名的链接替换为blog_url的域名，并确保使用HTTPS

    参数：
    link (str): 原始链接
    blog_url (str): 博客的URL

    返回：
    str: 修复后的链接
    """
    if not link or not blog_url:
        return link

    parsed_blog_url = urlparse(blog_url)

    # 如果链接是相对路径，或者缺少协议，则使用 urljoin
    if not urlparse(link).netloc:
        link = urljoin(blog_url, link)

    parsed_link = urlparse(link)

    # 强制使用 https 协议
    if parsed_link.scheme != 'https':
        parsed_link = parsed_link._replace(scheme='https')

    if is_bad_link(link):
        fixed_link = urlunparse(parsed_link._replace(netloc=parsed_blog_url.netloc))
        return fixed_link
    else:
        # 确保链接使用 https 协议
        fixed_link = urlunparse(parsed_link)
        if parsed_link.scheme != 'https':
            logging.info(f"将链接协议从 {link} 强制改为 HTTPS: {fixed_link}")
        return fixed_link

def parse_feed(url, session, count=5, blog_url=None):
    """
    解析 Atom 或 RSS2 feed 并返回包含网站名称、作者、原链接和每篇文章详细内容的字典。

    此函数接受一个 feed 的地址（atom.xml 或 rss2.xml），解析其中的数据，并返回一个字典结构，
    其中包括网站名称、作者、原链接和每篇文章的详细内容。

    参数：
    url (str): Atom 或 RSS2 feed 的 URL。
    session (requests.Session): 用于请求的会话对象。
    count (int): 获取文章数的最大数。如果小于则全部获取，如果文章数大于则只取前 count 篇文章。
    blog_url (str): 目标博客的 URL，用于修复文章链接。

    返回：
    dict: 包含网站名称、作者、原链接和每篇文章详细内容的字典。
    """
    try:
        response = session.get(url, headers=headers, timeout=timeout)
        response.encoding = 'utf-8'
        feed = feedparser.parse(response.text)
        
        result = {
            'website_name': feed.feed.title if 'title' in feed.feed else '',
            'author': feed.feed.author if 'author' in feed.feed else '',
            'link': feed.feed.link if 'link' in feed.feed else '',
            'articles': []
        }

        for entry in feed.entries:
            if 'published' in entry:
                published = format_published_time(entry.published)
            elif 'updated' in entry:
                published = format_published_time(entry.updated)
                logging.warning(f"文章 {entry.title} 未包含发布时间，已使用更新时间 {published}")
            else:
                published = ''
                logging.warning(f"文章 {entry.title} 未包含任何时间信息")

            entry_link = entry.link if 'link' in entry else ''
            fixed_link = fix_link(entry_link, blog_url)
            article = {
                'title': entry.title if 'title' in entry else '',
                'author': result['author'],
                'link': fixed_link,
                'published': published,
                'summary': entry.summary if 'summary' in entry else '',
                'content': entry.content[0].value if 'content' in entry and entry.content else entry.description if 'description' in entry else ''
            }
            result['articles'].append(article)
        
        # 对文章按时间排序，并只取前 count 篇文章
        result['articles'] = sorted(
            result['articles'],
            key=lambda x: datetime.strptime(x['published'], '%Y-%m-%d %H:%M') if x['published'] else datetime.min,
            reverse=True
        )[:count]

        return result
    except Exception as e:
        logging.error(f"无法解析FEED地址：{url} : {e}", exc_info=True)
        return {
            'website_name': '',
            'author': '',
            'link': '',
            'articles': []
        }

def process_friend(friend, session, count, specific_RSS=[]):
    """
    处理单个朋友的博客信息。

    参数：
    friend (list): 包含朋友信息的列表 [name, blog_url, avatar]。
    session (requests.Session): 用于请求的会话对象。
    count (int): 获取每个博客的最大文章数。
    specific_RSS (list): 包含特定 RSS 源的字典列表 [{name, url}]

    返回：
    dict: 包含朋友博客信息的字典。
    """
    name, blog_url, avatar = friend

    # 确保博客 URL 使用 https 协议
    blog_url = ensure_https(blog_url)

    # 如果 specific_RSS 中有对应的 name，则直接返回 feed_url
    if specific_RSS is None:
        specific_RSS = []
    rss_feed = next((rss['url'] for rss in specific_RSS if rss['name'] == name), None)
    if rss_feed:
        feed_url = rss_feed
        feed_type = 'specific'
        logging.info(f"“{name}”的博客“{blog_url}”为特定RSS源“{feed_url}”")
    else:
        feed_type, feed_url = check_feed(blog_url, session)
        logging.info(f"“{name}”的博客“{blog_url}”的feed类型为“{feed_type}”")

    if feed_type != 'none':
        feed_info = parse_feed(feed_url, session, count, blog_url=blog_url)
        articles = [
            {
                'title': article['title'],
                'created': article['published'],
                'link': article['link'],
                'author': name,
                'avatar': avatar
            }
            for article in feed_info['articles']
        ]
        
        for article in articles:
            logging.info(f"{name} 发布了新文章：{article['title']}，时间：{article['created']}，链接：{article['link']}")

        return {
            'name': name,
            'status': 'active',
            'articles': articles
        }
    else:
        logging.warning(f"{name} 的博客 {blog_url} 无法访问")
        return {
            'name': name,
            'status': 'error',
            'articles': []
        }

def fetch_and_process_data(json_url, specific_RSS=[], count=5):
    """
    读取 JSON 数据并处理订阅信息，返回统计数据和文章信息。

    参数：
    json_url (str): 包含朋友信息的 JSON 文件的 URL。
    count (int): 获取每个博客的最大文章数。
    specific_RSS (list): 包含特定 RSS 源的字典列表 [{name, url}]

    返回：
    tuple: (处理后的数据字典, 错误的朋友信息列表)
    """
    session = requests.Session()
    retries = requests.packages.urllib3.util.retry.Retry(
        total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504]
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    try:
        response = session.get(json_url, headers=headers, timeout=timeout)
        friends_data = response.json()
    except Exception as e:
        logging.error(f"无法获取链接：{json_url}，出现的问题为：{e}", exc_info=True)
        return None, []

    total_friends = len(friends_data['friends'])
    active_friends = 0
    error_friends = 0
    total_articles = 0
    article_data = []
    error_friends_info = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_friend = {
            executor.submit(process_friend, friend, session, count, specific_RSS): friend
            for friend in friends_data['friends']
        }
        
        for future in as_completed(future_to_friend):
            friend = future_to_friend[future]
            try:
                result = future.result()
                if result['status'] == 'active':
                    active_friends += 1
                    article_data.extend(result['articles'])
                    total_articles += len(result['articles'])
                else:
                    error_friends += 1
                    error_friends_info.append(friend)
            except Exception as e:
                logging.error(f"处理 {friend} 时发生错误: {e}", exc_info=True)
                error_friends += 1
                error_friends_info.append(friend)

    result = {
        'statistical_data': {
            'friends_num': total_friends,
            'active_num': active_friends,
            'error_num': error_friends,
            'article_num': total_articles,
            'last_updated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        'article_data': article_data
    }

    logging.info(f"数据处理完成，总共有 {total_friends} 位朋友，其中 {active_friends} 位博客可访问，{error_friends} 位博客无法访问")

    return result, error_friends_info

def sort_articles_by_time(data):
    """
    对文章数据按时间排序

    参数：
    data (dict): 包含文章信息的字典

    返回：
    dict: 按时间排序后的文章信息字典
    """
    # 先确保每个元素存在时间
    for article in data.get('article_data', []):
        if not article.get('created'):
            article['created'] = '2024-01-01 00:00'
            logging.warning(f"文章 {article['title']} 未包含时间信息，已设置为默认时间 2024-01-01 00:00")

    if 'article_data' in data:
        sorted_articles = sorted(
            data['article_data'],
            key=lambda x: datetime.strptime(x['created'], '%Y-%m-%d %H:%M') if x['created'] else datetime.min,
            reverse=True
        )
        data['article_data'] = sorted_articles
    return data

def marge_data_from_json_url(data, marge_json_url):
    """
    从另一个 JSON 文件中获取数据并合并到原数据中。

    参数：
    data (dict): 包含文章信息的字典
    marge_json_url (str): 包含另一个文章信息的 JSON 文件的 URL。

    返回：
    dict: 合并后的文章信息字典，已去重处理
    """
    try:
        response = requests.get(marge_json_url, headers=headers, timeout=timeout)
        marge_data = response.json()
    except Exception as e:
        logging.error(f"无法获取链接：{marge_json_url}，出现的问题为：{e}", exc_info=True)
        return data
    
    if 'article_data' in marge_data:
        logging.info(f"开始合并数据，原数据共有 {len(data['article_data'])} 篇文章，境外数据共有 {len(marge_data['article_data'])} 篇文章")

        existing_links = set(article['link'] for article in data['article_data'])
        new_articles = [article for article in marge_data['article_data'] if article['link'] not in existing_links]

        data['article_data'].extend(new_articles)
        logging.info(f"合并数据完成，现在共有 {len(data['article_data'])} 篇文章")
    return data


def marge_errors_from_json_url(errors, marge_json_url):
    """
    从另一个网络 JSON 文件中获取错误信息并遍历，删除在errors中，
    不存在于marge_errors中的友链信息。

    参数：
    errors (list): 包含错误信息的列表
    marge_json_url (str): 包含另一个错误信息的 JSON 文件的 URL。

    返回：
    list: 合并后的错误信息列表
    """
    try:
        response = requests.get(marge_json_url, timeout=10)  # 设置请求超时时间
        marge_errors = response.json()
    except Exception as e:
        logging.error(f"无法获取链接：{marge_json_url}，出现的问题为：{e}", exc_info=True)
        return errors

    # 合并错误信息列表并去重
    errors_set = set(tuple(error) for error in errors)
    marge_errors_set = set(tuple(error) for error in marge_errors)
    combined_errors = list(errors_set.union(marge_errors_set))

    logging.info(f"合并错误信息完成，合并后共有 {len(combined_errors)} 位朋友")
    return combined_errors

def deal_with_large_data(result):
    """
    处理文章数据，保留前150篇及其作者在后续文章中的出现。
    
    参数：
    result (dict): 包含统计数据和文章数据的字典。
    
    返回：
    dict: 处理后的数据，只包含需要的文章。
    """
    result = sort_articles_by_time(result)
    article_data = result.get("article_data", [])
    
    # 检查文章数量是否大于 150
    max_articles = 150
    if len(article_data) > max_articles:
        logging.info("数据量较大，开始进行处理...")
        # 获取前 max_articles 篇文章的作者集合
        top_authors = {article["author"] for article in article_data[:max_articles]}

        # 从第 {max_articles + 1} 篇开始过滤，只保留前 max_articles 篇出现过的作者的文章
        filtered_articles = article_data[:max_articles] + [
            article for article in article_data[max_articles:]
            if article["author"] in top_authors
        ]

        # 更新结果中的 article_data
        result["article_data"] = filtered_articles
        # 更新结果中的统计数据
        result["statistical_data"]["article_num"] = len(filtered_articles)
        logging.info(f"数据处理完成，保留 {len(filtered_articles)} 篇文章")

    return result
