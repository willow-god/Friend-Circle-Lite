"""Article payload post-processing before `all.json` is written."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


PUBLISHED_TIME_FORMAT = "%Y-%m-%d %H:%M"


def sort_articles_by_time(data: dict, future_tolerance_days: int = 2) -> dict:
    """Sort article payloads by time and remove far-future timestamps."""
    for article in data.get("article_data", []):
        if not article.get("created"):
            article["created"] = "2024-01-01 00:00"
            logging.warning(f"[数据处理] 文章 {article['title']} 未包含时间信息，已设置为默认时间 2024-01-01 00:00")

    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    max_allowed_time = now + timedelta(days=future_tolerance_days)
    filtered_articles = []
    removed_count = 0

    for article in data.get("article_data", []):
        article_time = datetime.strptime(article["created"], PUBLISHED_TIME_FORMAT)
        if article_time > max_allowed_time:
            removed_count += 1
            logging.warning(
                f"[数据处理] 文章 {article['title']} 的时间 {article['created']} 超出当前时间 {future_tolerance_days} 天以上，已跳过显示"
            )
            continue
        filtered_articles.append(article)

    filtered_articles.sort(key=lambda item: datetime.strptime(item["created"], PUBLISHED_TIME_FORMAT), reverse=True)
    data["article_data"] = filtered_articles
    if removed_count:
        logging.info(f"[数据处理] 已过滤 {removed_count} 篇未来时间异常的文章")
    return data


def finalize_article_data(result: dict, future_tolerance_days: int = 2) -> dict:
    """Keep the existing data trimming strategy for very large datasets."""
    result = sort_articles_by_time(result, future_tolerance_days=future_tolerance_days)
    article_data = result.get("article_data", [])
    result["statistical_data"]["article_num"] = len(article_data)

    max_articles = 150
    if len(article_data) > max_articles:
        logging.info(f"[数据处理] 数据量较大，开始裁剪，当前 {len(article_data)} 篇，基础保留 {max_articles} 篇")
        top_authors = {article["author"] for article in article_data[:max_articles]}
        filtered_articles = article_data[:max_articles] + [
            article for article in article_data[max_articles:]
            if article["author"] in top_authors
        ]
        result["article_data"] = filtered_articles
        result["statistical_data"]["article_num"] = len(filtered_articles)
        logging.info(f"[数据处理] 数据裁剪完成，保留 {len(filtered_articles)} 篇文章")

    return result
