from datetime import datetime, timedelta, timezone
from dateutil import parser
import requests
import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    # 尝试自动解析输入时间字符串
    try:
        parsed_time = parser.parse(time_str)
        # 如果没有时区信息，则将其视为 UTC
        if parsed_time.tzinfo is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
        
        # 转换为上海时区（UTC+8）
        shanghai_time = parsed_time.astimezone(timezone(timedelta(hours=8)))
        return shanghai_time.strftime('%Y-%m-%d %H:%M')
    
    except (ValueError, parser.ParserError):
        pass

    # 定义支持的时间格式
    time_formats = [
        '%a, %d %b %Y %H:%M:%S %z',  # Mon, 11 Mar 2024 14:08:32 +0000
        '%a, %d %b %Y %H:%M:%S GMT',   # Wed, 19 Jun 2024 09:43:53 GMT
        '%Y-%m-%dT%H:%M:%S%z',         # 2024-03-11T14:08:32+00:00
        '%Y-%m-%dT%H:%M:%SZ',          # 2024-03-11T14:08:32Z
        '%Y-%m-%d %H:%M:%S',           # 2024-03-11 14:08:32
        '%Y-%m-%d'                     # 2024-03-11
    ]

    # 遍历所有支持的时间格式进行解析
    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_str, fmt)
            # 将解析的时间视为 UTC
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
            # 转换为上海时区
            shanghai_time = parsed_time.astimezone(timezone(timedelta(hours=8)))
            return shanghai_time.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            continue

    # 如果所有格式都无法匹配，返回空字符串
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
    rss_url = blog_url.rstrip('/') + '/rss.xml'  # 2024-07-26 添加 /rss.xml内容的支持
    rss2_url = blog_url.rstrip('/') + '/rss2.xml'
    feed_url = blog_url.rstrip('/') + '/feed'
    feed2_url = blog_url.rstrip('/') + '/feed.xml'  # 2024-07-26 添加 /feed.xml内容的支持
    feed3_url = blog_url.rstrip('/') + '/feed/'  # 2024-07-26 添加 /feed/内容的支持
    index_url = blog_url.rstrip('/') + '/index.xml' # 2024-07-25 添加 /index.xml内容的支持
    
    try:
        atom_response = session.get(atom_url, headers=headers, timeout=timeout)
        if atom_response.status_code == 200:
            return ['atom', atom_url]
    except requests.RequestException:
        pass
    
    try:
        rss_response = session.get(rss_url, headers=headers, timeout=timeout)
        if rss_response.status_code == 200:
            return ['rss', rss_url]
    except requests.RequestException:
        pass
    
    try:
        rss_response = session.get(rss2_url, headers=headers, timeout=timeout)
        if rss_response.status_code == 200:
            return ['rss2', rss2_url]
    except requests.RequestException:
        pass

    try:
        feed_response = session.get(feed_url, headers=headers, timeout=timeout)
        if feed_response.status_code == 200:
            return ['feed', feed_url]
    except requests.RequestException:
        pass
    
    try:
        feed_response = session.get(feed2_url, headers=headers, timeout=timeout)
        if feed_response.status_code == 200:
            return ['feed2', feed2_url]
    except requests.RequestException:
        pass
    
    try:
        feed_response = session.get(index_url, headers=headers, timeout=timeout)
        if feed_response.status_code == 200:
            return ['index', index_url]
    except requests.RequestException:
        pass
    
    try:
        feed_response = session.get(feed3_url, headers=headers, timeout=timeout)
        if feed_response.status_code == 200:
            return ['feed3', feed3_url]
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
            
            if 'published' in entry:
                published = format_published_time(entry.published)
            elif 'updated' in entry:
                published = format_published_time(entry.updated)
                # 输出警告信息
                print(f"警告：文章 {entry.title} 未包含发布时间，请尽快联系站长处理，暂时已设置为更新时间 {published}")
            else:
                published = ''
                print(f"警告：文章 {entry.title} 未包含任何时间信息，请尽快联系站长处理")
            article = {
                'title': entry.title if 'title' in entry else '',
                'author': result['author'],
                'link': entry.link if 'link' in entry else '',
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
        print(f"不可链接的FEED地址：{url} : {e}")
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
    
    # 如果 specific_RSS 中有对应的 name，则直接返回 feed_url
    if specific_RSS is None:
        specific_RSS = []
    rss_feed = next((rss['url'] for rss in specific_RSS if rss['name'] == name), None)
    if rss_feed:
        feed_url = rss_feed
        feed_type = 'specific'
        print(f"========“{name}”的博客“{blog_url} ”为特定RSS源“{feed_url}”========")
    else:
        feed_type, feed_url = check_feed(blog_url, session)
        print(f"========“{name}”的博客“{blog_url} ”的feed类型为“{feed_type}”========")

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

def fetch_and_process_data(json_url, specific_RSS=[], count=5):
    """
    读取 JSON 数据并处理订阅信息，返回统计数据和文章信息。

    参数：
    json_url (str): 包含朋友信息的 JSON 文件的 URL。
    count (int): 获取每个博客的最大文章数。
    specific_RSS (list): 包含特定 RSS 源的字典列表 [{name, url}]

    返回：
    dict: 包含统计数据和文章信息的字典。
    """
    session = requests.Session()
    
    # 检查是否是 GitHub 仓库路径
    if '/' in json_url and not json_url.startswith('http'):
        json_url = f"https://raw.githubusercontent.com/{json_url}/output/v2/data.json"

    try:
        response = session.get(json_url, headers=headers, timeout=timeout)
        friends_data = response.json()
    except Exception as e:
        print(f"无法获取该链接：{json_url} , 出现的问题为：{e}")
        return None

    # 处理两种数据格式
    if 'friends' in friends_data:
        friends = friends_data['friends']
    elif 'content' in friends_data:
        friends = [
            [friend['title'], friend['url'], friend.get('avatar', '')]
            for friend in friends_data['content']
        ]
    else:
        print("未知的数据格式")
        return None

    total_friends = len(friends)
    active_friends = 0
    error_friends = 0
    total_articles = 0
    article_data = []
    error_friends_info = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_friend = {
            executor.submit(process_friend, friend, session, count, specific_RSS): friend
            for friend in friends
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
                print(f"处理 {friend} 时发生错误: {e}")
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
    
    print("数据处理完成")
    print("总共有 %d 位朋友，其中 %d 位博客可访问，%d 位博客无法访问" % (total_friends, active_friends, error_friends))

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
    for article in data['article_data']:
        if article['created'] == '' or article['created'] == None:
            article['created'] = '2024-01-01 00:00'
            # 输出警告信息
            print(f"警告：文章 {article['title']} 未包含任何可提取的时间信息，已设置为默认时间 2024-01-01 00:00")
    
    if 'article_data' in data:
        sorted_articles = sorted(
            data['article_data'],
            key=lambda x: datetime.strptime(x['created'], '%Y-%m-%d %H:%M'),
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
        print(f"无法获取该链接：{marge_json_url} , 出现的问题为：{e}")
        return data
    
    if 'article_data' in marge_data:
        print("开始合并数据，原数据共有 %d 篇文章，境外数据共有 %d 篇文章" % (len(data['article_data']), len(marge_data['article_data'])))
        data['article_data'].extend(marge_data['article_data'])
        data['article_data'] = list({v['link']:v for v in data['article_data']}.values())
        print("合并数据完成，现在共有 %d 篇文章" % len(data['article_data']))
    return data

import requests

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
        print(f"无法获取该链接：{marge_json_url}，出现的问题为：{e}")
        return errors

    # 提取 marge_errors 中的 URL
    marge_urls = {item[1] for item in marge_errors}

    # 使用过滤器保留 errors 中在 marge_errors 中出现的 URL
    filtered_errors = [error for error in errors if error[1] in marge_urls]

    print("合并错误信息完成，保留了 %d 位朋友" % len(filtered_errors))
    return filtered_errors

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
    if len(article_data) > 150:
        print("数据量较大，开始进行处理···")
        # 获取前 150 篇文章的作者集合
        first_200_authors = {article["author"] for article in article_data[:150]}
        
        # 从第151篇开始过滤，只保留前150篇出现过的作者的文章
        filtered_articles = article_data[:150] + [
            article for article in article_data[150:]
            if article["author"] in first_200_authors
        ]
        
        # 更新结果中的 article_data
        result["article_data"] = filtered_articles
        # 更新结果中的统计数据
        result["statistical_data"]["article_num"] = len(filtered_articles)
        print("数据处理完成，保留 %d 篇文章" % len(filtered_articles))

    return result
