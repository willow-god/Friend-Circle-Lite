from datetime import datetime
from dateutil import parser
import requests
import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed

# 标准化的请求头
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

timeout = (5, 10) # 连接超时和读取超时，防止requests接受时间过长

def format_published_time(time_str):
    """
    格式化发布时间为统一格式 YYYY-MM-DD HH:MM
    """
    try:
        # 尝试自动解析
        parsed_time = parser.parse(time_str)
        return parsed_time.strftime('%Y-%m-%d %H:%M')
    except (ValueError, parser.ParserError):
        pass
    
    time_formats = [
        '%a, %d %b %Y %H:%M:%S %z',       # Mon, 11 Mar 2024 14:08:32 +0000
        '%a, %d %b %Y %H:%M:%S GMT',      # Wed, 19 Jun 2024 09:43:53 GMT
        '%Y-%m-%dT%H:%M:%S%z',            # 2024-03-11T14:08:32+00:00
        '%Y-%m-%dT%H:%M:%SZ',             # 2024-03-11T14:08:32Z
        '%Y-%m-%d %H:%M:%S',              # 2024-03-11 14:08:32
        '%Y-%m-%d'                        # 2024-03-11
    ]

    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_str, fmt)
            return parsed_time.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            continue

    # 如果所有格式都无法匹配，返回原字符串或一个默认值
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
    
    atom_url = blog_url.rstrip('/') + '/atom.xml'
    rss_url = blog_url.rstrip('/') + '/rss2.xml'
    feed_url = blog_url.rstrip('/') + '/feed'
    
    try:
        atom_response = session.get(atom_url, headers=headers, timeout=timeout)
        if atom_response.status_code == 200:
            return ['atom', atom_url]
    except requests.RequestException:
        pass
    
    try:
        rss_response = session.get(rss_url, headers=headers, timeout=timeout)
        if rss_response.status_code == 200:
            return ['rss2', rss_url]
    except requests.RequestException:
        pass

    try:
        feed_response = session.get(feed_url, headers=headers, timeout=timeout)
        if feed_response.status_code == 200:
            return ['feed', feed_url]
    except requests.RequestException:
        pass
    
    return ['none', blog_url]

def parse_feed(url, session, count=5):
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
        response = session.get(url, headers=headers, timeout=timeout)
        response.encoding = 'utf-8'
        feed = feedparser.parse(response.text)
        
        result = {
            'website_name': feed.feed.title if 'title' in feed.feed else '',
            'author': feed.feed.author if 'author' in feed.feed else '',
            'link': feed.feed.link if 'link' in feed.feed else '',
            'articles': []
        }
        
        for i, entry in enumerate(feed.entries):
            if i >= count:
                break
            
            published = format_published_time(entry.published) if 'published' in entry else ''
            article = {
                'title': entry.title if 'title' in entry else '',
                'author': entry.author if 'author' in entry else '',
                'link': entry.link if 'link' in entry else '',
                'published': published,
                'summary': entry.summary if 'summary' in entry else '',
                'content': entry.content[0].value if 'content' in entry and entry.content else entry.description if 'description' in entry else ''
            }
            result['articles'].append(article)
        
        return result
    except Exception as e:
        print(f"不可链接的FEED地址：{url}: {e}")
        return {
            'website_name': '',
            'author': '',
            'link': '',
            'articles': []
        }

def process_friend(friend, session, count):
    """
    处理单个朋友的博客信息。

    参数：
    friend (list): 包含朋友信息的列表 [name, blog_url, avatar]。
    session (requests.Session): 用于请求的会话对象。
    count (int): 获取每个博客的最大文章数。

    返回：
    dict: 包含朋友博客信息的字典。
    """
    name, blog_url, avatar = friend
    feed_type, feed_url = check_feed(blog_url, session)

    if feed_type != 'none':
        feed_info = parse_feed(feed_url, session, count)
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
            print(f"{name} 发布了新文章：{article['title']}, 时间：{article['created']}")
        
        return {
            'name': name,
            'status': 'active',
            'articles': articles
        }
    else:
        print(f"{name} 的博客 {blog_url} 无法访问")
        return {
            'name': name,
            'status': 'error',
            'articles': []
        }

def fetch_and_process_data(json_url, count=5):
    """
    读取 JSON 数据并处理订阅信息，返回统计数据和文章信息。

    参数：
    json_url (str): 包含朋友信息的 JSON 文件的 URL。
    count (int): 获取每个博客的最大文章数。

    返回：
    dict: 包含统计数据和文章信息的字典。
    """
    session = requests.Session()
    
    try:
        response = session.get(json_url, headers=headers, timeout=timeout)
        friends_data = response.json()
    except Exception as e:
        print(f"无法获取该链接：{json_url}, 出现的问题为：{e}")
        return None

    total_friends = len(friends_data['friends'])
    active_friends = 0
    error_friends = 0
    total_articles = 0
    article_data = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_friend = {
            executor.submit(process_friend, friend, session, count): friend
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
            except Exception as e:
                print(f"处理 {friend} 时发生错误: {e}")
                error_friends += 1

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
    
    print("数据处理完成")
    print("总共有 %d 位朋友，其中 %d 位博客可访问，%d 位博客无法访问" % (total_friends, active_friends, error_friends))

    return result

def sort_articles_by_time(data):
    """
    对文章数据按时间排序

    参数：
    data (dict): 包含文章信息的字典

    返回：
    dict: 按时间排序后的文章信息字典
    """
    if 'article_data' in data:
        sorted_articles = sorted(
            data['article_data'],
            key=lambda x: datetime.strptime(x['created'], '%Y-%m-%d %H:%M'),
            reverse=True
        )
        data['article_data'] = sorted_articles
    return data
