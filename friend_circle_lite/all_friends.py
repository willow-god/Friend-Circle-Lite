import string
import requests
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from friend_circle_lite.utils.cache import load_cache, save_cache
from friend_circle_lite.single_friend import process_friend
from friend_circle_lite import HEADERS_JSON, timeout

def fetch_and_process_data(json_url: str, specific_RSS: list = None, count: int = 5, cache_file: str = None):
    """
    读取 JSON 数据并处理订阅信息，返回统计数据和文章信息。

    参数：
        json_url (str): 包含朋友信息的 JSON 文件的 URL。
        count (int): 获取每个博客的最大文章数。
        specific_RSS (list): 包含特定 RSS 源的字典列表 [{name, url}]（来自 YAML）。
        cache_file (str): 缓存文件路径。

    返回：
        (result_dict, error_friends_info_list)
    """
    if specific_RSS is None:
        specific_RSS = []

    # 1. 加载缓存
    cache_list = load_cache(cache_file)

    # 2. 标记 YAML 条目
    manual_list = []
    for item in specific_RSS:
        if isinstance(item, dict) and 'name' in item and 'url' in item:
            manual_list.append({'name': item['name'], 'url': item['url'], 'source': 'manual'})

    # 3. 合并（缓存先，YAML 后覆盖）
    combined_map = {e['name']: e for e in cache_list}
    for e in manual_list:  # 手动优先
        combined_map[e['name']] = e
    specific_and_cache = list(combined_map.values())

    # 4. 建立方便判断的集合：手动源名称集合
    manual_name_set = {e['name'] for e in manual_list}

    # 5. 获取朋友列表
    session = requests.Session()
    try:
        response = session.get(json_url, headers=HEADERS_JSON, timeout=timeout)
        friends_data = response.json()
    except Exception as e:
        logging.error(f"无法获取链接：{json_url} ：{e}", exc_info=True)
        return None

    friends = friends_data.get('friends', [])
    total_friends = len(friends)
    active_friends = 0
    error_friends = 0
    total_articles = 0
    article_data = []
    error_friends_info = []
    cache_updates = []  # 用于收集缓存更新（线程安全：用局部列表 + 合并）

    # 6. 并发处理
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_friend = {
            executor.submit(process_friend, friend, session, count, specific_and_cache): friend
            for friend in friends
        }

        for future in as_completed(future_to_friend):
            friend = future_to_friend[future]
            try:
                result = future.result()

                # 拿回缓存更新意图
                upd = result.get('cache_update', {})
                if upd and upd.get('action') != 'none':
                    cache_updates.append(upd)

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

    # 7. 处理缓存更新
    cache_map = {e['name']: e for e in cache_list}

    # 去重 & 过滤无效条目
    unique_updates = {}
    for upd in cache_updates:
        name = upd.get('name')
        action = upd.get('action')
        url = upd.get('url')
        if not name:
            continue

        # 过滤手动 YAML 的条目（不允许覆盖）
        if name in manual_name_set:
            continue

        # 只缓存有效 RSS 地址
        if action == 'set':
            if url and url != 'none' and url != '':
                unique_updates[name] = {'action': 'set', 'url': url, 'reason': upd.get('reason', '')}
        elif action == 'delete':
            unique_updates[name] = {'action': 'delete', 'url': None, 'reason': upd.get('reason', '')}

    # 应用缓存更新
    for name, upd in unique_updates.items():
        if upd['action'] == 'set':
            cache_map[name] = {'name': name, 'url': upd['url'], 'source': 'cache'}
            logging.info(f"缓存更新：SET {name} -> {upd['url']} ({upd['reason']})")
        elif upd['action'] == 'delete':
            if name in cache_map:
                cache_map.pop(name)
                logging.info(f"缓存更新：DELETE {name} ({upd['reason']})")

    # 8. 保存缓存
    save_cache(cache_file, list(cache_map.values()))

    # 9. 汇总统计
    result = {
        'statistical_data': {
            'friends_num': total_friends,
            'active_num': active_friends,
            'error_num': error_friends,
            'article_num': total_articles,
            'last_updated_time': datetime.now(ZoneInfo("Asia/Shanghai")).strftime('%Y-%m-%d %H:%M:%S'),
        },
        'article_data': article_data,
    }

    logging.info(
        f"数据处理完成，总共有 {total_friends} 位朋友，其中 {active_friends} 位博客可访问，"
        f"{error_friends} 位博客无法访问。缓存更新 {len(unique_updates)} 条。"
    )

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
            logging.warning(f"文章 {article['title']} 未包含时间信息，已设置为默认时间 2024-01-01 00:00")
    
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
        response = requests.get(marge_json_url, headers=HEADERS_JSON, timeout=timeout)
        marge_data = response.json()
    except Exception as e:
        logging.error(f"无法获取链接：{marge_json_url}，出现的问题为：{e}", exc_info=True)
        return data
    
    if 'article_data' in marge_data:
        logging.info(f"开始合并数据，原数据共有 {len(data['article_data'])} 篇文章，第三方数据共有 {len(marge_data['article_data'])} 篇文章")
        data['article_data'].extend(marge_data['article_data'])
        data['article_data'] = list({v['link']:v for v in data['article_data']}.values())
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

    # 提取 marge_errors 中的 URL
    marge_urls = {item[1] for item in marge_errors}

    # 使用过滤器保留 errors 中在 marge_errors 中出现的 URL
    filtered_errors = [error for error in errors if error[1] in marge_urls]

    logging.info(f"合并错误信息完成，合并后共有 {len(filtered_errors)} 位朋友")
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