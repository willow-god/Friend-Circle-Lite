"""High-level crawler orchestration.

This module contains the system-level services that coordinate website loading,
RSS discovery, parsing, cache updates, result aggregation, and legacy output
formatting.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from friend_circle_lite import HEADERS_JSON, timeout
from friend_circle_lite.config.models import LinkCheckConfig, ProxySettings
from friend_circle_lite.crawler.feed_service import FeedDiscoveryService, FeedParserService
from friend_circle_lite.domain.models import Article, CacheRecord, CacheUpdate, CrawlResult, CrawlStatistics, FeedEndpoint, LinkCheckRecord, Website
from friend_circle_lite.link_checker.service import LinkReachabilityService
from friend_circle_lite.storage.sqlite_store import FeedCacheStore, LinkCheckStore


class FeedResolver:
    """Resolve which feed endpoint should be used for a website.

    Resolution order is kept compatible with the previous implementation:
    manual configuration first, then cache, and finally automatic discovery.
    """

    def __init__(self, discovery_service: FeedDiscoveryService, configured_feeds: list[CacheRecord]):
        self.discovery_service = discovery_service
        self.feed_lookup = {item.name: item for item in configured_feeds}

    def resolve(self, website: Website) -> FeedEndpoint | None:
        configured = self.feed_lookup.get(website.name)
        if configured:
            if configured.source == 'manual':
                logging.info(f"[RSS 解析] {website.name} 使用预设 RSS 源：{configured.url}")
            elif configured.source == 'cache':
                logging.info(f"[RSS 解析] {website.name} 使用缓存 RSS 源：{configured.url}")
            else:
                logging.info(f"[RSS 解析] {website.name} 使用 RSS 源：{configured.url} ，来源: {configured.source}")
            return FeedEndpoint(url=configured.url, feed_type="specific", source=configured.source)

        discovered = self.discovery_service.discover(website.url)
        if discovered:
            logging.info(f"[RSS 探测] {website.name} 自动探测到 RSS：{discovered.url}")
        return discovered


class SingleSiteCrawler:
    """Crawl one website and produce a normalized result."""

    def __init__(self, parser_service: FeedParserService, resolver: FeedResolver):
        self.parser_service = parser_service
        self.resolver = resolver

    def crawl(self, website: Website, count: int) -> CrawlResult:
        """Crawl one website while preserving legacy cache repair behavior."""
        endpoint = self.resolver.resolve(website)
        cache_update = CacheUpdate(action="none", name=website.name)

        if endpoint and endpoint.source == "auto":
            cache_update = CacheUpdate(action="set", name=website.name, url=endpoint.url, reason="auto_discovered")

        articles = self._parse_articles(endpoint, website, count)
        parse_error = endpoint is not None and not articles

        if parse_error and endpoint and endpoint.source in ("cache", "unknown"):
            logging.warning(f"[RSS 抓取] {website.name} 缓存 RSS 本次抓取失败，将等待下次友链检测刷新 RSS 缓存")

        status = "active" if articles else "error"
        if not articles:
            if endpoint is None:
                logging.warning(f"[RSS 抓取] {website.name} 的博客 {website.url} 未找到有效 RSS")
            else:
                logging.warning(f"[RSS 抓取] {website.name} 的 RSS {endpoint.url} 未解析出文章")

        return CrawlResult(
            website=website,
            status=status,
            articles=articles,
            feed_url=endpoint.url if endpoint else None,
            feed_type=endpoint.feed_type if endpoint else "none",
            source_used=endpoint.source if endpoint else "none",
            cache_update=cache_update,
        )

    def _parse_articles(self, endpoint: FeedEndpoint | None, website: Website, count: int) -> list[Article]:
        if endpoint is None:
            return []

        articles = self.parser_service.parse(endpoint.url, count=count, blog_url=website.url)
        for article in articles:
            article.author = website.name
            article.avatar = website.avatar
            logging.info(f"[RSS 抓取] {website.name} 发布了新文章：{article.title}，时间：{article.published}，链接：{article.link}")
        return articles


class FriendCircleCrawlService:
    """System-level orchestrator for crawling all configured websites."""

    def __init__(
        self,
        json_url: str,
        count: int,
        specific_rss: list[dict] | None = None,
        cache_file: str | None = None,
        link_check_config: LinkCheckConfig | None = None,
        proxy_settings: ProxySettings | None = None,
    ):
        self.json_url = json_url
        self.count = count
        self.specific_rss = specific_rss or []
        self.cache_store = FeedCacheStore(cache_file)
        self.link_check_config = link_check_config or LinkCheckConfig()
        self.proxy_settings = proxy_settings or ProxySettings()
        self.link_check_store = LinkCheckStore(cache_file)

    def run(self) -> tuple[dict, list[list[str]]] | None:
        """Fetch website list, crawl all websites, and build public outputs."""
        session = requests.Session()
        websites = self._load_websites(session)
        if websites is None:
            return None

        cache_records = self.cache_store.load_records()
        manual_records = self._build_manual_records()
        merged_records = self._merge_feed_records(cache_records, manual_records)
        manual_names = {record.name for record in manual_records}

        link_check_records = self._check_links(websites, merged_records, manual_names)
        link_check_map = {record.url: record for record in link_check_records}

        cache_records = self.cache_store.load_records()
        merged_records = self._merge_feed_records(cache_records, manual_records)
        feed_names = {record.name for record in merged_records}
        crawlable_websites = [
            website for website in websites
            if link_check_map.get(website.url, LinkCheckRecord.unchecked(website)).crawl_allowed
            and website.name in feed_names
        ]
        skipped_count = len(websites) - len(crawlable_websites)
        logging.info(
            f"[朋友圈抓取] 友链总数 {len(websites)} 个，可进入 RSS 抓取 {len(crawlable_websites)} 个，"
            f"跳过 {skipped_count} 个不可抓取或无 RSS 缓存站点"
        )

        discovery_service = FeedDiscoveryService(session, self.proxy_settings)
        parser_service = FeedParserService(session, self.proxy_settings)
        resolver = FeedResolver(discovery_service=discovery_service, configured_feeds=merged_records)
        crawler = SingleSiteCrawler(parser_service=parser_service, resolver=resolver)

        crawl_results: list[CrawlResult] = []
        logging.info(f"[朋友圈抓取] 开始抓取 {len(crawlable_websites)} 个可抓取站点，每站最多 {self.count} 篇文章")
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_website = {
                executor.submit(crawler.crawl, website, self.count): website
                for website in crawlable_websites
            }
            for future in as_completed(future_to_website):
                website = future_to_website[future]
                try:
                    crawl_results.append(future.result())
                except Exception as exc:
                    logging.error(f"[朋友圈抓取] 处理 {website.to_error_payload()} 时发生错误: {exc}", exc_info=True)
                    crawl_results.append(CrawlResult(website=website, status="error"))

        self._apply_cache_updates(cache_records, crawl_results, manual_names)

        active_results = [result for result in crawl_results if result.status == "active"]
        unreachable_results = [record for record in link_check_records if not record.reachable]
        crawl_error_results = [result.website.to_error_payload() for result in crawl_results if result.status != "active"]
        error_results = [[record.name, record.url, record.avatar] for record in unreachable_results]
        all_articles = [article.to_public_dict() for result in active_results for article in result.articles]

        statistics = CrawlStatistics.create(
            friends_num=len(websites),
            active_num=len(active_results),
            error_num=len(websites) - len(active_results),
            article_num=len(all_articles),
        )
        stats_payload = statistics.to_dict()
        result = {
            "statistical_data": stats_payload,
            "article_data": all_articles,
        }
        link_payload = self._build_link_payload(link_check_records)
        logging.info(
            f"[数据汇总] 处理完成：友链总数 {len(websites)} 个，成功抓取文章站点 {len(active_results)} 个，"
            f"RSS 抓取失败 {len(crawl_error_results)} 个，友链不可达 {len(unreachable_results)} 个。"
        )
        return result, error_results, link_payload

    def _check_links(self, websites: list[Website], feed_records: list[CacheRecord], manual_names: set[str]) -> list[LinkCheckRecord]:
        service = LinkReachabilityService(
            config=self.link_check_config,
            proxy_settings=self.proxy_settings,
            store=self.link_check_store,
            feed_records=feed_records,
        )
        records = service.check_websites(websites)
        if service.feed_updates:
            self._apply_feed_updates_from_link_check(service.feed_updates, manual_names)
        return records

    def _apply_feed_updates_from_link_check(self, updates: dict[str, CacheRecord | None], manual_names: set[str]) -> None:
        """保存可达性检测阶段发现或失效的 RSS 缓存。"""
        cache_map = {record.name: record for record in self.cache_store.load_records()}
        changed = False
        for name, record in updates.items():
            if name in manual_names:
                continue
            if record is None:
                if name in cache_map:
                    cache_map.pop(name)
                    changed = True
                    logging.info(f"[RSS 缓存] 可达性检测删除失效 RSS 缓存: {name}")
            else:
                cache_map[name] = record
                changed = True
                logging.info(f"[RSS 缓存] 可达性检测保存 RSS 缓存: {name} -> {record.url}")
        if changed:
            self.cache_store.save_records(list(cache_map.values()))

    @staticmethod
    def _build_link_statistics(records: list[LinkCheckRecord]) -> dict[str, int | str]:
        reachable = [record for record in records if record.reachable]
        crawl_allowed = [record for record in records if record.crawl_allowed]
        api_only = [record for record in records if record.best_method == "api"]
        has_author_link = [record for record in records if record.has_author_link]
        checked_times = [record.checked_at for record in records if record.checked_at]
        return {
            "link_total_num": len(records),
            "link_reachable_num": len(reachable),
            "link_unreachable_num": len(records) - len(reachable),
            "crawl_allowed_num": len(crawl_allowed),
            "api_only_num": len(api_only),
            "has_author_link_num": len(has_author_link),
            "link_last_checked_time": max(checked_times) if checked_times else "",
        }

    @staticmethod
    def _build_link_payload(records: list[LinkCheckRecord]) -> dict[str, object]:
        return {
            "statistical_data": FriendCircleCrawlService._build_link_statistics(records),
            "link_data": [record.to_link_dict() for record in records],
        }

    @staticmethod
    def _build_friend_data(
        websites: list[Website],
        crawl_results: list[CrawlResult],
        link_check_map: dict[str, LinkCheckRecord],
    ) -> list[dict[str, object]]:
        crawl_result_map = {result.website.url: result for result in crawl_results}
        friend_data: list[dict[str, object]] = []
        for website in websites:
            link_record = link_check_map.get(website.url) or LinkCheckRecord.unchecked(website)
            crawl_result = crawl_result_map.get(website.url)
            friend_data.append({
                "name": website.name,
                "url": website.url,
                "avatar": website.avatar,
                "linkpage": website.linkpage,
                "reachable": link_record.reachable,
                "crawl_allowed": link_record.crawl_allowed,
                "best_method": link_record.best_method,
                "best_latency": link_record.best_latency,
                "unreachable_since": link_record.unreachable_since,
                "unreachable_days": link_record.unreachable_days,
                "backlink_checked": link_record.backlink_checked,
                "has_author_link": link_record.has_author_link,
                "rss_crawl_reason": link_record.rss_crawl_reason,
                "feed_status": crawl_result.status if crawl_result else "skipped",
                "feed_url": crawl_result.feed_url if crawl_result else None,
                "feed_type": crawl_result.feed_type if crawl_result else "none",
                "article_count": len(crawl_result.articles) if crawl_result else 0,
            })
        return friend_data

    def _load_websites(self, session: requests.Session) -> list[Website] | None:
        try:
            response = session.get(self.json_url, headers=HEADERS_JSON, timeout=timeout)
            response.raise_for_status()
            friends_data = response.json()
        except Exception as exc:
            logging.error(f"无法获取链接：{self.json_url} ：{exc}", exc_info=True)
            return None

        website_map: dict[str, Website] = {}
        for friend in friends_data.get("friends", []):
            try:
                website = Website.from_friend_item(friend)
                website_map[website.url] = website
            except Exception:
                logging.warning(f"发现格式异常的友链数据，已跳过: {friend!r}")
        return list(website_map.values())

    def _build_manual_records(self) -> list[CacheRecord]:
        manual_records: list[CacheRecord] = []
        for item in self.specific_rss:
            if isinstance(item, dict) and item.get("name") and item.get("url"):
                manual_records.append(CacheRecord(name=item["name"], url=item["url"], source="manual"))
        return manual_records

    @staticmethod
    def _merge_feed_records(cache_records: list[CacheRecord], manual_records: list[CacheRecord]) -> list[CacheRecord]:
        merged = {record.name: record for record in cache_records}
        for record in manual_records:
            merged[record.name] = record
        return list(merged.values())

    def _apply_cache_updates(self, cache_records: list[CacheRecord], crawl_results: list[CrawlResult], manual_names: set[str]) -> None:
        cache_map = {record.name: record for record in cache_records}
        unique_updates: dict[str, CacheUpdate] = {}

        for result in crawl_results:
            update = result.cache_update
            if not update.name or update.action == "none" or update.name in manual_names:
                continue
            if update.action == "set" and update.url:
                unique_updates[update.name] = update
            elif update.action == "delete":
                unique_updates[update.name] = update

        for name, update in unique_updates.items():
            if update.action == "set" and update.url:
                cache_map[name] = CacheRecord(name=name, url=update.url, source="cache")
                if update.reason == "auto_discovered":
                    logging.info(f"💾 缓存新增：{name} -> {update.url} (自动探测)")
                elif update.reason == "repair_cache":
                    logging.info(f"💾 缓存修复：{name} -> {update.url} (重新探测)")
                else:
                    logging.info(f"💾 缓存更新：{name} -> {update.url} ({update.reason})")
            elif update.action == "delete" and name in cache_map:
                cache_map.pop(name)
                logging.info(f"🗑️ 缓存删除：{name} (RSS 源失效)")

        self.cache_store.save_records(list(cache_map.values()))


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
        article_time = datetime.strptime(article["created"], "%Y-%m-%d %H:%M")
        if article_time > max_allowed_time:
            removed_count += 1
            logging.warning(
                f"[数据处理] 文章 {article['title']} 的时间 {article['created']} 超出当前时间 {future_tolerance_days} 天以上，已跳过显示"
            )
            continue
        filtered_articles.append(article)

    filtered_articles.sort(key=lambda item: datetime.strptime(item["created"], "%Y-%m-%d %H:%M"), reverse=True)
    data["article_data"] = filtered_articles
    if removed_count:
        logging.info(f"[数据处理] 已过滤 {removed_count} 篇未来时间异常的文章")
    return data


def limit_large_dataset(result: dict, future_tolerance_days: int = 2) -> dict:
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


# Backward-compatible class names kept for legacy imports.
WebsiteFeedResolver = FeedResolver
WebsiteCrawler = SingleSiteCrawler
FriendCircleCrawler = FriendCircleCrawlService
