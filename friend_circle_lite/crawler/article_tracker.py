"""文章更新追踪。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from friend_circle_lite.domain.models import Article
from friend_circle_lite.storage.article_tracking_store import ArticleTrackingStore


class LatestArticleTracker:
    """Track whether a website published new posts since the last crawl."""

    def __init__(self, storage_path: str | Path, max_tracked_articles: int = 10):
        self.store = ArticleTrackingStore(storage_path, max_tracked_articles)

    def diff_and_persist(self, latest_articles: list[Article]) -> list[dict] | None:
        """Return newly seen articles and update the local storage.

        Returns None if:
        - This is the first run (no previous data exists)
        - No new articles are found
        - New articles exist but are not newer than the most recent tracked article
        """
        previous_articles = self.store.load_articles()

        # First run: no previous data exists, skip sending to prevent sending old articles
        if not previous_articles:
            logging.info("[文章追踪] 首次运行：跳过推送以防止发送旧文章")
            self.store.save_articles(latest_articles)
            return None

        previous_latest_date = self._get_latest_date(previous_articles)

        new_articles = [
            article for article in latest_articles
            if self._is_truly_new_article(article, previous_articles)
        ]

        if not new_articles:
            self.store.save_articles(latest_articles)
            return None

        truly_new_articles = []
        for article in new_articles:
            if not article.published:
                continue
            try:
                article_date = datetime.strptime(article.published, "%Y-%m-%d %H:%M")
                if previous_latest_date is None or article_date > previous_latest_date:
                    truly_new_articles.append(article)
            except Exception as exc:
                logging.warning(f"[文章追踪] 解析文章日期失败: {article.title}, 日期: {article.published}, 错误: {exc}")

        self.store.save_articles(latest_articles)

        if truly_new_articles:
            logging.info(f"[文章追踪] 发现 {len(truly_new_articles)} 篇新文章（日期比之前更新）")
            return [article.to_tracking_dict() for article in truly_new_articles]

        logging.info(f"[文章追踪] 发现 {len(new_articles)} 篇新文章，但日期不够新，跳过推送")
        return None

    @staticmethod
    def _is_truly_new_article(article: Article, previous_articles: list[Article]) -> bool:
        """Check if an article is truly new by comparing link, title, and published date.

        An article is considered new only if its link, title, and published date
        do not match any previous article (empty values are skipped).
        """
        for prev in previous_articles:
            if article.link and article.link == prev.link:
                return False
            if article.title and article.title == prev.title:
                return False
            if article.published and article.published == prev.published:
                return False
        return True

    @staticmethod
    def _get_latest_date(articles: list[Article]) -> datetime | None:
        """Find the latest publish date from a list of articles."""
        latest_date = None
        for article in articles:
            if not article.published:
                continue
            try:
                article_date = datetime.strptime(article.published, "%Y-%m-%d %H:%M")
                if latest_date is None or article_date > latest_date:
                    latest_date = article_date
            except Exception:
                continue
        return latest_date
