"""Legacy-compatible crawl entrypoints.

The internal implementation is now delegated to `crawler_service`, but these
functions keep the existing public API stable for `run.py` and external users.
"""

import logging
from datetime import datetime
from math import ceil

import requests

from friend_circle_lite import HEADERS_JSON, timeout
from friend_circle_lite.domain.models import normalize_latency
from friend_circle_lite.crawler.service import (
    FriendCircleCrawlService,
    limit_large_dataset as _limit_large_dataset,
    sort_articles_by_time as _sort_articles_by_time,
)

def fetch_and_process_data(
    json_url: str,
    specific_RSS: list = None,
    count: int = 5,
    cache_file: str = None,
    link_check_config=None,
    proxy_settings=None,
):
    """Legacy wrapper around the new crawler orchestration service."""
    return FriendCircleCrawlService(
        json_url=json_url,
        count=count,
        specific_rss=specific_RSS,
        cache_file=cache_file,
        link_check_config=link_check_config,
        proxy_settings=proxy_settings,
    ).run()

def sort_articles_by_time(data, future_tolerance_days=2):
    """Legacy wrapper around the refactored sort helper."""
    return _sort_articles_by_time(data, future_tolerance_days=future_tolerance_days)

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
        logging.error(f"无法获取链接：{marge_json_url} ，出现的问题为：{e}", exc_info=True)
        return data

    if 'article_data' in marge_data:
        logging.info(f"开始合并文章数据，原数据共有 {len(data['article_data'])} 篇文章，第三方数据共有 {len(marge_data['article_data'])} 篇文章")
        data['article_data'].extend(marge_data['article_data'])
        data['article_data'] = list({v['link']:v for v in data['article_data']}.values())
        logging.info(f"合并文章数据完成，现在共有 {len(data['article_data'])} 篇文章")
    return data


def merge_link_data_from_json_url(link_data, merge_json_url):
    """
    从另一个 link.json 文件中获取友链可达性数据并智能合并。

    合并策略：
    - 可达性优先级：direct > proxy > api > none
    - 延迟取最优（最小值）
    - 反链取并集（任一为 true 则为 true）
    - 失败次数取最小值

    参数：
    link_data (dict): 本地友链数据，包含 statistical_data 和 link_data
    merge_json_url (str): 远程 link.json 的 URL

    返回：
    dict: 合并后的友链数据
    """
    try:
        response = requests.get(merge_json_url, headers=HEADERS_JSON, timeout=timeout)
        remote_data = response.json()
    except Exception as e:
        logging.warning(f"无法获取友链数据：{merge_json_url} ，跳过友链数据合并。错误：{e}")
        return link_data

    if not _extract_links(remote_data):
        logging.warning("远程数据不包含可用友链字段，跳过友链数据合并")
        return link_data

    local_links = [_normalize_merge_link(link) for link in _extract_links(link_data)]
    remote_links = [_normalize_merge_link(link) for link in _extract_links(remote_data)]

    logging.info(f"开始合并友链数据，本地 {len(local_links)} 条，远程 {len(remote_links)} 条")

    # 按 URL 建立索引
    link_map = {link["url"]: link for link in local_links}

    for remote_link in remote_links:
        url = remote_link["url"]
        if url not in link_map:
            # 新友链，直接添加
            link_map[url] = remote_link
        else:
            # 已存在，智能合并
            local_link = link_map[url]
            link_map[url] = _merge_single_link(local_link, remote_link)

    # 重新计算统计数据
    merged_records = list(link_map.values())
    merged_stats = _recalculate_link_statistics(merged_records)
    merged_links = [_to_public_link(link) for link in merged_records]
    logging.info(f"合并友链数据完成，共有 {len(merged_links)} 条友链")
    local_stats = _extract_stats(link_data)
    remote_stats = _extract_stats(remote_data)
    checked_times = [
        local_stats.get("checked", "") or local_stats.get("link_last_checked_time", ""),
        remote_stats.get("checked", "") or remote_stats.get("link_last_checked_time", ""),
        merged_stats.get("link_last_checked_time", ""),
    ]
    merged_stats["link_last_checked_time"] = max([item for item in checked_times if item] or [""])

    return {
        'statistical_data': merged_stats,
        'link_data': merged_links,
    }


def _merge_single_link(local, remote):
    """
    合并单条友链数据，优先选择更好的检测结果。

    优先级：
    1. 可达性：direct > proxy > api > none
    2. 延迟：取最小值
    3. 反链：任一为 true 则为 true
    4. 失败次数：取最小值
    """
    method_priority = {'direct': 4, 'proxy': 3, 'api': 2, 'disabled': 1, 'none': 0, '': 0}

    local_priority = _link_priority(local, method_priority)
    remote_priority = _link_priority(remote, method_priority)

    # 选择优先级更高的作为基础
    if remote_priority > local_priority:
        base = remote.copy()
        alt = local
    elif remote_priority < local_priority:
        base = local.copy()
        alt = remote
    else:
        # 优先级相同，选择延迟更低的
        local_latency = local.get('latency', 999)
        remote_latency = remote.get('latency', 999)
        if remote_latency >= 0 and (local_latency < 0 or remote_latency < local_latency):
            base = remote.copy()
            alt = local
        else:
            base = local.copy()
            alt = remote

    # 反链取并集
    local_backlink = local.get('backlink')
    remote_backlink = remote.get('backlink')
    if local_backlink is True or remote_backlink is True:
        base['backlink'] = True
    elif local_backlink is False and remote_backlink is False:
        base['backlink'] = False
    # 否则保持 base 的值

    unreachable_since_values = [
        value for value in (local.get("unreachable_since"), remote.get("unreachable_since"))
        if value
    ]
    base["unreachable_since"] = min(unreachable_since_values) if unreachable_since_values else ""

    # 最新文章时间取更新的一侧，天数取更小的一侧
    if remote.get("updated", "") > local.get("updated", ""):
        base["updated"] = remote.get("updated", "")
    elif local.get("updated"):
        base["updated"] = local.get("updated", "")
    stale_values = [value for value in (local.get("stale_days"), remote.get("stale_days")) if value is not None]
    base["stale_days"] = min(stale_values) if stale_values else None

    # 检测时间取最新
    local_checked = local.get('_checked', '')
    remote_checked = remote.get('_checked', '')
    if remote_checked > local_checked:
        base['_checked'] = remote_checked

    return base


def _link_priority(link, method_priority):
    """计算友链合并优先级，兼容新旧 link.json 字段。"""
    if link.get("rss"):
        return 10 + method_priority.get(link.get("_method", ""), 0)
    if link.get("ok"):
        return 5 + method_priority.get(link.get("_method", ""), 0)
    return method_priority.get(link.get("_method", ""), 0)


def _to_public_link(link):
    """转换为前端需要的精简友链状态结构。"""
    normalized = _normalize_merge_link(link)
    latency = normalize_latency(normalized.get("latency")) if normalized.get("ok") else -1
    return {
        "name": normalized.get("name", ""),
        "link": normalized.get("url", ""),
        "link_page": normalized.get("page", ""),
        "avatar": normalized.get("avatar", ""),
        "reachable": bool(normalized.get("ok")),
        "crawlable": bool(normalized.get("rss")),
        "latency": latency,
        "unreachable_days": _calculate_unreachable_days(normalized.get("unreachable_since")) if not normalized.get("ok") else None,
        "unreachable_since": normalized.get("unreachable_since", "") if not normalized.get("ok") else "",
        "has_backlink": normalized.get("backlink"),
        "updated": normalized.get("updated", ""),
        "stale_days": normalized.get("stale_days"),
    }


def _extract_links(payload):
    """读取新旧 link.json 列表字段。"""
    return payload.get("links") or payload.get("link_data") or []


def _extract_stats(payload):
    """读取新旧 link.json 统计字段。"""
    return payload.get("stats") or payload.get("statistical_data") or {}


def _normalize_merge_link(link):
    """把新旧单条友链结构统一为内部紧凑结构。"""
    ok = link.get("ok") if "ok" in link else link.get("reachable")
    rss = link.get("rss") if "rss" in link else link.get("crawlable", link.get("crawl_allowed"))
    return {
        "name": link.get("name", ""),
        "url": link.get("url") or link.get("link") or "",
        "page": link.get("page") or link.get("link_page") or link.get("linkpage", ""),
        "avatar": link.get("avatar", ""),
        "ok": bool(ok),
        "rss": bool(rss),
        "latency": link.get("latency", link.get("best_latency", -1)),
        "unreachable_since": link.get("unreachable_since", ""),
        "backlink": link.get("backlink") if "backlink" in link else link.get("has_backlink"),
        "updated": link.get("updated") or link.get("last_post_published", ""),
        "stale_days": link.get("stale_days", link.get("last_post_days_ago")),
        "_method": link.get("method") or link.get("best_method", ""),
        "_checked": link.get("checked_at", ""),
    }


def _calculate_unreachable_days(unreachable_since: str) -> int | None:
    """Calculate rounded-up unreachable days from a persisted start time."""
    if not unreachable_since:
        return None
    try:
        since = datetime.strptime(unreachable_since, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    elapsed_seconds = max(0, (datetime.now() - since).total_seconds())
    return max(1, ceil(elapsed_seconds / 86400))


def _recalculate_link_statistics(links):
    """重新计算合并后的友链统计数据。"""
    reachable = [link for link in links if link.get('ok')]
    crawl_allowed = [link for link in links if link.get('rss')]
    api_only = [link for link in links if link.get('_method') == 'api']
    has_backlink = [link for link in links if link.get('backlink') is True]
    checked_times = [link.get('_checked', '') for link in links if link.get('_checked')]

    return {
        'link_total_num': len(links),
        'link_reachable_num': len(reachable),
        'link_unreachable_num': len(links) - len(reachable),
        'crawl_allowed_num': len(crawl_allowed),
        'api_only_num': len(api_only),
        'has_author_link_num': len(has_backlink),
        'link_last_checked_time': max(checked_times) if checked_times else '',
    }


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
        logging.error(f"无法获取链接：{marge_json_url} ，出现的问题为：{e}", exc_info=True)
        return errors

    # 提取 marge_errors 中的 URL
    marge_urls = {item[1] for item in marge_errors}

    # 使用过滤器保留 errors 中在 marge_errors 中出现的 URL
    filtered_errors = [error for error in errors if error[1] in marge_urls]

    logging.info(f"合并错误信息完成，合并后共有 {len(filtered_errors)} 位朋友")
    return filtered_errors

def deal_with_large_data(result, future_tolerance_days=2):
    """Legacy wrapper around the refactored dataset trimming helper."""
    return _limit_large_dataset(result, future_tolerance_days=future_tolerance_days)


def merge_data_from_json_url(data, merge_json_url):
    """Correctly spelled wrapper for the legacy article merge helper."""
    return marge_data_from_json_url(data, merge_json_url)


def merge_errors_from_json_url(errors, merge_json_url):
    """Correctly spelled wrapper for the legacy error merge helper."""
    return marge_errors_from_json_url(errors, merge_json_url)
