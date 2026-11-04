"""Merge local crawl outputs with optionally configured remote data sources."""

from __future__ import annotations

import logging

import requests

from friend_circle_lite.crawler.http_client import DEFAULT_TIMEOUT, HEADERS_JSON
from friend_circle_lite.domain.models import calculate_elapsed_days, normalize_latency


def merge_article_data(data: dict, remote_json_url: str) -> dict:
    """Merge remote articles into `all.json`, de-duplicating by link."""
    try:
        response = requests.get(remote_json_url, headers=HEADERS_JSON, timeout=DEFAULT_TIMEOUT)
        remote_data = response.json()
    except Exception as exc:
        logging.error(f"无法获取链接：{remote_json_url} ，出现的问题为：{exc}", exc_info=True)
        return data

    if "article_data" in remote_data:
        logging.info(
            f"开始合并文章数据，原数据共有 {len(data['article_data'])} 篇文章，"
            f"第三方数据共有 {len(remote_data['article_data'])} 篇文章"
        )
        data["article_data"].extend(remote_data["article_data"])
        data["article_data"] = list({article["link"]: article for article in data["article_data"]}.values())
        logging.info(f"合并文章数据完成，现在共有 {len(data['article_data'])} 篇文章")
    return data


def merge_error_data(errors: list, remote_json_url: str) -> list:
    """Keep only errors that also appear in the remote `errors.json`."""
    try:
        response = requests.get(remote_json_url, timeout=10)
        remote_errors = response.json()
    except Exception as exc:
        logging.error(f"无法获取链接：{remote_json_url} ，出现的问题为：{exc}", exc_info=True)
        return errors

    remote_urls = {item[1] for item in remote_errors}
    filtered_errors = [error for error in errors if error[1] in remote_urls]
    logging.info(f"合并错误信息完成，合并后共有 {len(filtered_errors)} 位朋友")
    return filtered_errors


def merge_link_data(link_data: dict, remote_json_url: str) -> dict:
    """Merge a remote `link.json` using best reachability, latency, and backlink."""
    try:
        response = requests.get(remote_json_url, headers=HEADERS_JSON, timeout=DEFAULT_TIMEOUT)
        remote_data = response.json()
    except Exception as exc:
        logging.warning(f"无法获取友链数据：{remote_json_url} ，跳过友链数据合并。错误：{exc}")
        return link_data

    if not _extract_links(remote_data):
        logging.warning("远程数据不包含可用友链字段，跳过友链数据合并")
        return link_data

    local_links = [_normalize_merge_link(link) for link in _extract_links(link_data)]
    remote_links = [_normalize_merge_link(link) for link in _extract_links(remote_data)]

    logging.info(f"开始合并友链数据，本地 {len(local_links)} 条，远程 {len(remote_links)} 条")

    link_map = {link["url"]: link for link in local_links}
    for remote_link in remote_links:
        url = remote_link["url"]
        if url not in link_map:
            link_map[url] = remote_link
        else:
            link_map[url] = _merge_single_link(link_map[url], remote_link)

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
        "statistical_data": merged_stats,
        "link_data": merged_links,
    }


def _merge_single_link(local: dict, remote: dict) -> dict:
    """Merge one friend link, preferring the better check result."""
    method_priority = {"direct": 4, "proxy": 3, "api": 2, "disabled": 1, "none": 0, "": 0}

    local_priority = _link_priority(local, method_priority)
    remote_priority = _link_priority(remote, method_priority)

    if remote_priority > local_priority:
        base = remote.copy()
    elif remote_priority < local_priority:
        base = local.copy()
    else:
        local_latency = local.get("latency", 999)
        remote_latency = remote.get("latency", 999)
        if remote_latency >= 0 and (local_latency < 0 or remote_latency < local_latency):
            base = remote.copy()
        else:
            base = local.copy()

    local_backlink = local.get("backlink")
    remote_backlink = remote.get("backlink")
    if local_backlink is True or remote_backlink is True:
        base["backlink"] = True
    elif local_backlink is False and remote_backlink is False:
        base["backlink"] = False

    unreachable_since_values = [
        value for value in (local.get("unreachable_since"), remote.get("unreachable_since"))
        if value
    ]
    base["unreachable_since"] = min(unreachable_since_values) if unreachable_since_values else ""

    if remote.get("updated", "") > local.get("updated", ""):
        base["updated"] = remote.get("updated", "")
    elif local.get("updated"):
        base["updated"] = local.get("updated", "")
    stale_values = [
        value for value in (local.get("stale_days"), remote.get("stale_days"))
        if value is not None
    ]
    base["stale_days"] = min(stale_values) if stale_values else None

    local_checked = local.get("_checked", "")
    remote_checked = remote.get("_checked", "")
    if remote_checked > local_checked:
        base["_checked"] = remote_checked

    return base


def _link_priority(link: dict, method_priority: dict[str, int]) -> int:
    """Compute merge priority, accepting both old and new `link.json` fields."""
    if link.get("rss"):
        return 10 + method_priority.get(link.get("_method", ""), 0)
    if link.get("ok"):
        return 5 + method_priority.get(link.get("_method", ""), 0)
    return method_priority.get(link.get("_method", ""), 0)


def _to_public_link(link: dict) -> dict:
    """Convert an internal link record to the compact frontend structure."""
    normalized = _normalize_merge_link(link)
    reachable = normalized.get("ok")
    return {
        "name": normalized.get("name", ""),
        "link": normalized.get("url", ""),
        "link_page": normalized.get("page", ""),
        "avatar": normalized.get("avatar", ""),
        "reachable": bool(reachable),
        "crawlable": bool(normalized.get("rss")),
        "latency": normalize_latency(normalized.get("latency")) if reachable else -1,
        "unreachable_days": (
            calculate_elapsed_days(normalized.get("unreachable_since")) if not reachable else None
        ),
        "unreachable_since": normalized.get("unreachable_since", "") if not reachable else "",
        "has_backlink": normalized.get("backlink"),
        "updated": normalized.get("updated", ""),
        "stale_days": normalized.get("stale_days"),
    }


def _extract_links(payload: dict) -> list:
    """Read the link list from either the new or the legacy `link.json` shape."""
    return payload.get("links") or payload.get("link_data") or []


def _extract_stats(payload: dict) -> dict:
    """Read statistics from either the new or the legacy `link.json` shape."""
    return payload.get("stats") or payload.get("statistical_data") or {}


def _normalize_merge_link(link: dict) -> dict:
    """Normalize old and new single-link structures into one internal shape."""
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


def _recalculate_link_statistics(links: list[dict]) -> dict:
    """Recalculate friend-link statistics after merging."""
    reachable = [link for link in links if link.get("ok")]
    crawl_allowed = [link for link in links if link.get("rss")]
    api_only = [link for link in links if link.get("_method") == "api"]
    has_backlink = [link for link in links if link.get("backlink") is True]
    checked_times = [link.get("_checked", "") for link in links if link.get("_checked")]

    return {
        "link_total_num": len(links),
        "link_reachable_num": len(reachable),
        "link_unreachable_num": len(links) - len(reachable),
        "crawl_allowed_num": len(crawl_allowed),
        "api_only_num": len(api_only),
        "has_author_link_num": len(has_backlink),
        "link_last_checked_time": max(checked_times) if checked_times else "",
    }
