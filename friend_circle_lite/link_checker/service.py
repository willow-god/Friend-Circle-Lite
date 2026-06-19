"""友链可达性与 RSS 可抓取性检测。

检测策略：
1. 优先检查手动 RSS 或缓存 RSS，能解析文章则认为站点可达且可抓取。
2. RSS 不可用时自动探测常见 RSS 地址。
3. 仍找不到 RSS 时检查主页，主页可访问则只标记可达，不参与朋友圈抓取。
4. 主页不可访问时保留 API 兜底，用于判断站点是否可能可达。
5. 反链检测只在站点可达时执行。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote, urlparse, urlsplit, urlunsplit

import requests

from friend_circle_lite.config.models import LinkCheckConfig, ProxySettings
from friend_circle_lite.crawler.feed_service import FeedDiscoveryService, FeedParserService
from friend_circle_lite.crawler.http_client import WebFetchClient
from friend_circle_lite.domain.models import Article, CacheRecord, FeedEndpoint, LinkCheckRecord, LinkMethodStatus, Website, normalize_latency
from friend_circle_lite.storage.sqlite_store import LinkCheckStore


LINK_CHECK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 "
        "(Friend-Circle-Lite/2.0; +https://github.com/willow-god/Friend-Circle-Lite)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
    "X-Friend-Circle-Link-Check": "1.0",
}

RAW_HEADERS = {
    "User-Agent": LINK_CHECK_HEADERS["User-Agent"],
    "X-Friend-Circle-Link-Check": "1.0",
}


class LinkReachabilityService:
    """检查友链是否可达，以及是否可参与 RSS 抓取。"""

    def __init__(
        self,
        config: LinkCheckConfig,
        proxy_settings: ProxySettings,
        store: LinkCheckStore,
        feed_records: list[CacheRecord] | None = None,
        feed_parser=None,
        feed_discovery=None,
        fetcher: WebFetchClient | None = None,
    ):
        self.config = config
        self.proxy_settings = proxy_settings
        self.store = store
        self.feed_lookup = {record.name: record for record in (feed_records or [])}
        self.feed_parser = feed_parser
        self.feed_discovery = feed_discovery
        self.fetcher = fetcher
        self.feed_updates: dict[str, CacheRecord | None] = {}

    def check_websites(self, websites: list[Website]) -> list[LinkCheckRecord]:
        """检查一组友链，优先复用未过期缓存。"""
        cached_records = self.store.load_records([website.url for website in websites])
        records_by_url: dict[str, LinkCheckRecord] = {}
        websites_to_check: list[Website] = []
        backlink_refresh_records: list[tuple[Website, LinkCheckRecord]] = []

        for website in websites:
            cached = cached_records.get(website.url)
            if cached and self._can_reuse_cached_record(cached, website):
                linkpage_changed = not self._same_linkpage(cached.linkpage, website.linkpage)
                refreshed = self._refresh_cached_metadata(cached, website)
                records_by_url[website.url] = refreshed
                if self._should_refresh_backlink(refreshed, website, linkpage_changed):
                    backlink_refresh_records.append((website, refreshed))
            else:
                websites_to_check.append(website)

        total_count = len(websites)
        cached_count = total_count - len(websites_to_check)
        logging.info(
            f"[友链检测] 友链总数 {total_count} 个，缓存复用 {cached_count} 个，"
            f"本次实际检测 {len(websites_to_check)} 个，缓存有效期 {self.config.max_age_hours} 小时"
        )

        if websites_to_check:
            logging.info(
                f"[友链检测] 开始实际检测 {len(websites_to_check)} 个友链状态，"
                f"其余 {cached_count} 个复用缓存"
            )
            checked_records = self._check_fresh_websites(websites_to_check, cached_records)
            self.store.save_records(checked_records)
            for record in checked_records:
                records_by_url[record.url] = record
        else:
            logging.info(f"[友链检测] 全部 {total_count} 个友链状态缓存仍有效，本次不发起友链检测请求")

        if backlink_refresh_records:
            logging.info(f"[反链检测] 友链页地址变更，单独刷新 {len(backlink_refresh_records)} 个反链状态")
            self._refresh_backlinks_only(backlink_refresh_records)

        return [records_by_url.get(website.url) or LinkCheckRecord.unchecked(website) for website in websites]

    def _check_fresh_websites(self, websites: list[Website], cached_records: dict[str, LinkCheckRecord]) -> list[LinkCheckRecord]:
        records: list[LinkCheckRecord] = []
        with requests.Session() as session:
            self.feed_parser = self.feed_parser or FeedParserService(session, self.proxy_settings)
            self.feed_discovery = self.feed_discovery or FeedDiscoveryService(session, self.proxy_settings)
            self.fetcher = self.fetcher or WebFetchClient(session, self.proxy_settings)
            with ThreadPoolExecutor(max_workers=max(1, self.config.max_workers)) as executor:
                future_to_website = {
                    executor.submit(self._check_website, session, website, cached_records.get(website.url)): website
                    for website in websites
                }
                for future in as_completed(future_to_website):
                    website = future_to_website[future]
                    try:
                        records.append(future.result())
                    except Exception as exc:
                        logging.warning(f"[友链检测] 友链 {website.name} 检测失败: {exc}")
                        records.append(self._build_failed_record(website, cached_records.get(website.url)))
        return records

    def _check_website(self, session: requests.Session, website: Website, cached: LinkCheckRecord | None) -> LinkCheckRecord:
        record = self._check_rss_first(website, cached)
        if record is None:
            homepage = self._request_homepage(website.url)
            api = LinkMethodStatus()
            if not homepage.success:
                api = self._request_api(session, website.url)
                time.sleep(0.2)
            record = self._compose_non_rss_record(website, cached, homepage, api)

        if record.reachable and self.config.enable_backlink_check and self.config.author_url and website.linkpage:
            record.backlink_checked = True
            record.has_author_link = self._check_author_link_in_page(session, website.linkpage)
        elif not record.reachable:
            record.backlink_checked = bool(website.linkpage)
            record.has_author_link = False
        return record

    def _check_rss_first(self, website: Website, cached: LinkCheckRecord | None) -> LinkCheckRecord | None:
        configured = self.feed_lookup.get(website.name)
        if configured:
            endpoint = FeedEndpoint(url=configured.url, feed_type="specific", source=configured.source)
            latest_article = self._latest_feed_article(endpoint, website)
            if latest_article:
                return self._build_feed_record(website, endpoint, self._last_feed_latency(), latest_article)
            logging.warning(f"友链 {website.name} 的缓存 RSS 失效: {configured.url} ，开始重新探测")
            if configured.source == "cache":
                self.feed_updates[website.name] = None

        discovered = self.feed_discovery.discover(website.url) if self.feed_discovery else None
        latest_article = self._latest_feed_article(discovered, website) if discovered else None
        if discovered and latest_article:
            self.feed_updates[website.name] = CacheRecord(name=website.name, url=discovered.url, source="cache")
            return self._build_feed_record(website, discovered, self._last_feed_latency(), latest_article)
        return None

    def _latest_feed_article(self, endpoint: FeedEndpoint, website: Website) -> Article | None:
        articles = self.feed_parser.parse(endpoint.url, count=1, blog_url=website.url)
        return articles[0] if articles else None

    def _last_feed_latency(self) -> float:
        return normalize_latency(getattr(self.feed_parser, "last_latency", None))

    def _build_feed_record(self, website: Website, endpoint: FeedEndpoint, latency: float, latest_article: Article) -> LinkCheckRecord:
        method = "rss_cache" if endpoint.source == "cache" else "rss"
        last_post_published, last_post_days_ago = self._article_staleness(latest_article)
        return LinkCheckRecord(
            name=website.name,
            url=website.url,
            avatar=website.avatar,
            linkpage=website.linkpage,
            checked_at=self._now_text(),
            reachable=True,
            crawl_allowed=True,
            best_method=method,
            best_latency=latency,
            fail_count=0,
            rss_crawl_reason=f"allowed_by_{method}",
            last_post_published=last_post_published,
            last_post_days_ago=last_post_days_ago,
        )

    @staticmethod
    def _article_staleness(article: Article) -> tuple[str, int | None]:
        published = article.published or ""
        if not published:
            return "", None
        try:
            published_at = datetime.strptime(published, "%Y-%m-%d %H:%M")
        except ValueError:
            return published, None
        days_ago = max(0, int((datetime.now() - published_at).total_seconds() // 86400))
        return published, days_ago

    def _request_homepage(self, url: str) -> LinkMethodStatus:
        if not self._is_url(url):
            return LinkMethodStatus()
        result = self.fetcher.get(url, headers=LINK_CHECK_HEADERS, timeout=self.config.timeout, desc="主页检测")
        if result.response is None:
            return LinkMethodStatus(success=False, status_code=None, latency=result.latency)
        return LinkMethodStatus(success=result.success, status_code=result.response.status_code, latency=result.latency)

    def _request_api(self, session: requests.Session, url: str) -> LinkMethodStatus:
        if not self.config.status_api_url:
            return LinkMethodStatus()

        api_url = self.config.status_api_url.format(url=quote(url, safe=""))
        start_time = time.time()
        try:
            response = session.get(api_url, headers=RAW_HEADERS, timeout=30)
            latency = normalize_latency(time.time() - start_time)
        except requests.RequestException as exc:
            logging.warning(f"[API 检查] 请求失败: {url} ，错误: {exc}")
            return LinkMethodStatus(success=False, status_code=None, latency=normalize_latency(time.time() - start_time))

        try:
            payload = response.json()
            status_code = int(payload.get("data", 0))
            success = int(payload.get("code", 0)) == 200 and status_code == 200
            if success:
                logging.info(f"[API 检查] 成功访问: {url} ，状态码 200")
            else:
                logging.warning(f"[API 检查] 状态异常: {url} -> [{payload.get('code')}, {payload.get('data')}]")
            return LinkMethodStatus(success=success, status_code=status_code, latency=latency)
        except Exception as exc:
            logging.warning(f"[API 检查] 解析响应失败: {url} ，错误: {exc}")
            return LinkMethodStatus(success=False, status_code=response.status_code, latency=latency)

    def _compose_non_rss_record(
        self,
        website: Website,
        cached: LinkCheckRecord | None,
        homepage: LinkMethodStatus,
        api: LinkMethodStatus,
    ) -> LinkCheckRecord:
        reachable = homepage.success or api.success
        if homepage.success:
            best_method = "homepage"
            best_latency = homepage.latency
            reason = "reachable_without_rss"
        elif api.success:
            best_method = "api"
            best_latency = api.latency
            reason = "api_reachable_without_rss"
        else:
            best_method = "none"
            best_latency = -1
            reason = "blocked_unreachable"

        fail_count = 0 if reachable else ((cached.fail_count if cached else 0) + 1)
        return LinkCheckRecord(
            name=website.name,
            url=website.url,
            avatar=website.avatar,
            linkpage=website.linkpage,
            checked_at=self._now_text(),
            reachable=reachable,
            crawl_allowed=False,
            best_method=best_method,
            best_latency=best_latency,
            fail_count=fail_count,
            rss_crawl_reason=reason,
            direct=homepage,
            api=api,
        )

    @staticmethod
    def _first_measured_latency(*statuses: LinkMethodStatus) -> float:
        for status in statuses:
            if status.latency > 0:
                return normalize_latency(status.latency)
        return normalize_latency(None)

    def _check_author_link_in_page(self, session: requests.Session, linkpage_url: str) -> bool:
        fetcher = self.fetcher or WebFetchClient(session, self.proxy_settings)
        result = fetcher.get(linkpage_url, headers=RAW_HEADERS, timeout=self.config.timeout, desc="友链页面检测")
        response = result.response
        if response is None:
            return False

        author_url = self.config.author_url
        if not author_url.startswith(("http://", "https://")):
            author_url = "https://" + author_url

        variants = {
            author_url,
            author_url.replace("https://", "http://"),
            author_url.replace("https://", "//"),
            author_url.replace("https://", ""),
            self.config.author_url,
            "//" + self.config.author_url,
            "https://" + self.config.author_url,
            "http://" + self.config.author_url,
        }
        content = response.text
        for variant in variants:
            if (
                f'href="{variant}"' in content
                or f"href='{variant}'" in content
                or f'href="{variant}/"' in content
                or f"href='{variant}/'" in content
                or variant in content
            ):
                return True
        return False

    def _can_reuse_cached_record(self, cached: LinkCheckRecord, website: Website) -> bool:
        try:
            has_measured_latency = float(cached.best_latency) > 0
        except (TypeError, ValueError):
            has_measured_latency = False
        if not has_measured_latency:
            return False
        if cached.crawl_allowed and website.name not in self.feed_lookup:
            return False
        return self.store.is_fresh(cached, self.config.max_age_hours)

    @staticmethod
    def _refresh_cached_metadata(cached: LinkCheckRecord, website: Website) -> LinkCheckRecord:
        cached.name = website.name
        cached.avatar = website.avatar
        cached.linkpage = website.linkpage
        return cached

    def _should_refresh_backlink(self, record: LinkCheckRecord, website: Website, linkpage_changed: bool) -> bool:
        return bool(
            linkpage_changed
            and record.reachable
            and self.config.enable_backlink_check
            and self.config.author_url
            and website.linkpage
        )

    def _refresh_backlinks_only(self, items: list[tuple[Website, LinkCheckRecord]]) -> None:
        with requests.Session() as session:
            self.fetcher = self.fetcher or WebFetchClient(session, self.proxy_settings)
            for website, record in items:
                record.backlink_checked = True
                record.has_author_link = self._check_author_link_in_page(session, website.linkpage)
            self.store.save_records([record for _, record in items])

    def _build_failed_record(self, website: Website, cached: LinkCheckRecord | None) -> LinkCheckRecord:
        record = LinkCheckRecord.unchecked(website, self._now_text())
        record.fail_count = (cached.fail_count if cached else 0) + 1
        return record

    @staticmethod
    def _build_disabled_record(website: Website, checked_at: str) -> LinkCheckRecord:
        return LinkCheckRecord(
            name=website.name,
            url=website.url,
            avatar=website.avatar,
            linkpage=website.linkpage,
            checked_at=checked_at,
            reachable=True,
            crawl_allowed=True,
            best_method="disabled",
            best_latency=0.01,
            rss_crawl_reason="link_check_disabled",
        )

    @staticmethod
    def _is_url(path: str) -> bool:
        return urlparse(path).scheme in ("http", "https")

    @staticmethod
    def _same_linkpage(left: str, right: str) -> bool:
        return LinkReachabilityService._normalize_linkpage(left) == LinkReachabilityService._normalize_linkpage(right)

    @staticmethod
    def _normalize_linkpage(url: str) -> str:
        url = (url or "").strip()
        if not url:
            return ""
        try:
            parts = urlsplit(url)
            path = parts.path.rstrip("/") or "/"
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment))
        except Exception:
            return url.rstrip("/")

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 兼容旧类名。
LinkCheckService = LinkReachabilityService
