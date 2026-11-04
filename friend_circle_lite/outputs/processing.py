"""Public article payload post-processing.

This is the last gate before `all.json` is written: titleless articles are
discarded, timestamps are normalized, future-dated entries are removed, and
very large datasets are trimmed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


DEFAULT_PUBLISHED_TIME = "2024-01-01 00:00"
MAX_ARTICLES_BEFORE_TRIMMING = 150
PUBLISHED_TIME_FORMAT = "%Y-%m-%d %H:%M"


def _drop_untitled_articles(articles: list[dict]) -> list[dict]:
    """Discard articles whose title is missing or blank."""
    kept: list[dict] = []
    for article in articles:
        title = str(article.get("title") or "").strip()
        if not title:
            logging.warning(
                f"[数据处理] 丢弃无标题文章（链接：{article.get('link') or '未知'}）"
            )
            continue
        article["title"] = title
        kept.append(article)
    dropped_count = len(articles) - len(kept)
    if dropped_count:
        logging.info(f"[数据处理] 共丢弃 {dropped_count} 篇无标题文章")
    return kept


def sort_articles_by_time(data: dict, future_tolerance_days: int = 2) -> dict:
    """Discard invalid articles, then sort the rest by publish time."""
    articles = _drop_untitled_articles(list(data.get("article_data", [])))

    for article in articles:
        if not article.get("created"):
            article["created"] = DEFAULT_PUBLISHED_TIME
            logging.warning(
                f"[数据处理] 文章 {article['title']} 未包含时间信息，已设置为默认时间 {DEFAULT_PUBLISHED_TIME}"
            )

    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    max_allowed_time = now + timedelta(days=future_tolerance_days)
    filtered_articles: list[dict] = []
    future_count = 0
    invalid_time_count = 0

    for article in articles:
        try:
            article_time = datetime.strptime(article["created"], PUBLISHED_TIME_FORMAT)
        except (TypeError, ValueError):
            invalid_time_count += 1
            logging.warning(
                f"[数据处理] 文章 {article['title']} 的时间格式异常：{article.get('created')!r}，已跳过"
            )
            continue
        if article_time > max_allowed_time:
            future_count += 1
            logging.warning(
                f"[数据处理] 文章 {article['title']} 的时间 {article['created']} 超出当前时间 {future_tolerance_days} 天以上，已跳过显示"
            )
            continue
        filtered_articles.append(article)

    filtered_articles.sort(
        key=lambda item: datetime.strptime(item["created"], PUBLISHED_TIME_FORMAT),
        reverse=True,
    )
    data["article_data"] = filtered_articles
    if future_count:
        logging.info(f"[数据处理] 已过滤 {future_count} 篇未来时间异常的文章")
    if invalid_time_count:
        logging.info(f"[数据处理] 已过滤 {invalid_time_count} 篇时间格式异常的文章")
    return data


def finalize_article_data(result: dict, future_tolerance_days: int = 2) -> dict:
    """Sort, validate, and trim the article payload before writing `all.json`."""
    result = sort_articles_by_time(result, future_tolerance_days=future_tolerance_days)
    article_data = result.get("article_data", [])
    result["statistical_data"]["article_num"] = len(article_data)

    if len(article_data) > MAX_ARTICLES_BEFORE_TRIMMING:
        logging.info(
            f"[数据处理] 数据量较大，开始裁剪，当前 {len(article_data)} 篇，"
            f"基础保留 {MAX_ARTICLES_BEFORE_TRIMMING} 篇"
        )
        top_authors = {
            article.get("author")
            for article in article_data[:MAX_ARTICLES_BEFORE_TRIMMING]
        }
        filtered_articles = article_data[:MAX_ARTICLES_BEFORE_TRIMMING] + [
            article for article in article_data[MAX_ARTICLES_BEFORE_TRIMMING:]
            if article.get("author") in top_authors
        ]
        result["article_data"] = filtered_articles
        result["statistical_data"]["article_num"] = len(filtered_articles)
        logging.info(f"[数据处理] 数据裁剪完成，保留 {len(filtered_articles)} 篇文章")

    return result
