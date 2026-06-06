"""Friend link reachability checks used before RSS crawling."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote, urlparse

import requests

from friend_circle_lite.app_config import LinkCheckConfig, ProxySettings
from friend_circle_lite.cache_store import LinkCheckStore
from friend_circle_lite.models import LinkCheckRecord, LinkMethodStatus, Website


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


class LinkCheckService:
    """Check friend homepage reachability and cache results."""

    def __init__(self, config: LinkCheckConfig, proxy_settings: ProxySettings, store: LinkCheckStore):
        self.config = config
        self.proxy_settings = proxy_settings
        self.store = store

    def check_websites(self, websites: list[Website]) -> list[LinkCheckRecord]:
        if not self.config.enable:
            now = self._now_text()
            return [self._build_disabled_record(website, now) for website in websites]

        cached_records = self.store.load_records([website.url for website in websites])
        records_by_url: dict[str, LinkCheckRecord] = {}
        websites_to_check: list[Website] = []

        for website in websites:
            cached = cached_records.get(website.url)
            if cached and self._can_reuse_cached_record(cached, website):
                records_by_url[website.url] = self._refresh_cached_metadata(cached, website)
            else:
                websites_to_check.append(website)

        if websites_to_check:
            logging.info(f"🔎 开始检测 {len(websites_to_check)} 个友链可达性")
            checked_records = self._check_fresh_websites(websites_to_check, cached_records)
            self.store.save_records(checked_records)
            for record in checked_records:
                records_by_url[record.url] = record
        else:
            logging.info("🔎 友链可达性检测缓存仍有效，本次复用缓存结果")

        return [records_by_url.get(website.url) or LinkCheckRecord.unchecked(website) for website in websites]

    def _check_fresh_websites(self, websites: list[Website], cached_records: dict[str, LinkCheckRecord]) -> list[LinkCheckRecord]:
        records: list[LinkCheckRecord] = []
        with requests.Session() as session:
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
                        logging.warning(f"友链 {website.name} 检测失败: {exc}")
                        records.append(self._build_failed_record(website, cached_records.get(website.url)))
        return records

    def _check_website(self, session: requests.Session, website: Website, cached: LinkCheckRecord | None) -> LinkCheckRecord:
        direct = self._request_method(session, website.url, "直接访问")
        proxy = LinkMethodStatus()
        api = LinkMethodStatus()

        if not direct.success:
            proxy_url = self._build_proxy_url(website.url)
            if proxy_url:
                proxy = self._request_method(session, proxy_url, "代理访问")

        if not direct.success and not proxy.success:
            api = self._request_api(session, website.url)
            time.sleep(0.2)

        record = self._compose_record(website, cached, direct, proxy, api)
        if record.reachable and self.config.enable_backlink_check and self.config.author_url and website.linkpage:
            record.backlink_checked = True
            record.has_author_link = self._check_author_link_in_page(session, website.linkpage)
        return record

    def _request_method(self, session: requests.Session, url: str, desc: str) -> LinkMethodStatus:
        if not self._is_url(url):
            return LinkMethodStatus()

        response, latency = self._request_url(session, url, headers=LINK_CHECK_HEADERS, desc=desc)
        if response is None:
            return LinkMethodStatus(success=False, status_code=None, latency=latency)
        success = response.status_code == 200
        if success:
            logging.info(f"[{desc}] 成功访问: {url}，延迟 {latency} 秒")
        else:
            logging.warning(f"[{desc}] 状态码异常: {url} -> {response.status_code}")
        return LinkMethodStatus(success=success, status_code=response.status_code, latency=latency)

    def _request_api(self, session: requests.Session, url: str) -> LinkMethodStatus:
        if not self.config.status_api_url:
            return LinkMethodStatus()

        api_url = self.config.status_api_url.format(url=quote(url, safe=""))
        response, latency = self._request_url(session, api_url, headers=RAW_HEADERS, desc="API 检查", timeout=30)
        if response is None:
            return LinkMethodStatus(success=False, status_code=None, latency=latency)

        try:
            payload = response.json()
            status_code = int(payload.get("data", 0))
            success = int(payload.get("code", 0)) == 200 and status_code == 200
            if success:
                logging.info(f"[API] 成功访问: {url}，状态码 200")
            else:
                logging.warning(f"[API] 状态异常: {url} -> [{payload.get('code')}, {payload.get('data')}]")
            return LinkMethodStatus(success=success, status_code=status_code, latency=latency)
        except Exception as exc:
            logging.warning(f"[API] 解析响应失败: {url}，错误: {exc}")
            return LinkMethodStatus(success=False, status_code=response.status_code, latency=latency)

    def _compose_record(
        self,
        website: Website,
        cached: LinkCheckRecord | None,
        direct: LinkMethodStatus,
        proxy: LinkMethodStatus,
        api: LinkMethodStatus,
    ) -> LinkCheckRecord:
        reachable = direct.success or proxy.success or api.success
        crawl_allowed = direct.success or proxy.success
        if direct.success:
            best_method = "direct"
            best_latency = direct.latency
            reason = "allowed_by_direct"
        elif proxy.success:
            best_method = "proxy"
            best_latency = proxy.latency
            reason = "allowed_by_proxy"
        elif api.success:
            best_method = "api"
            best_latency = api.latency
            reason = "blocked_api_only"
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
            crawl_allowed=crawl_allowed,
            best_method=best_method,
            best_latency=best_latency,
            fail_count=fail_count,
            rss_crawl_reason=reason,
            direct=direct,
            proxy=proxy,
            api=api,
        )

    def _check_author_link_in_page(self, session: requests.Session, linkpage_url: str) -> bool:
        response, _ = self._request_url(session, linkpage_url, headers=RAW_HEADERS, desc="友链页面检测")
        if not response:
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

    def _request_url(
        self,
        session: requests.Session,
        url: str,
        headers: dict[str, str],
        desc: str,
        timeout: int | None = None,
    ) -> tuple[requests.Response | None, float]:
        try:
            start_time = time.time()
            response = session.get(url, headers=headers, timeout=timeout or self.config.timeout)
            return response, round(time.time() - start_time, 2)
        except requests.RequestException as exc:
            logging.warning(f"[{desc}] 请求失败: {url}，错误: {exc}")
            return None, -1

    def _can_reuse_cached_record(self, cached: LinkCheckRecord, website: Website) -> bool:
        if self.config.enable_backlink_check and cached.linkpage != website.linkpage:
            return False
        return self.store.is_fresh(cached, self.config.max_age_hours)

    @staticmethod
    def _refresh_cached_metadata(cached: LinkCheckRecord, website: Website) -> LinkCheckRecord:
        cached.name = website.name
        cached.avatar = website.avatar
        cached.linkpage = website.linkpage
        return cached

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
            best_latency=-1,
            rss_crawl_reason="link_check_disabled",
        )

    def _build_proxy_url(self, url: str) -> str:
        if not self.proxy_settings.proxy_url:
            return ""
        if "{}" in self.proxy_settings.proxy_url:
            return self.proxy_settings.proxy_url.format(url)
        if "{url}" in self.proxy_settings.proxy_url:
            return self.proxy_settings.proxy_url.format(url=url)
        return f"{self.proxy_settings.proxy_url}{url}"

    @staticmethod
    def _is_url(path: str) -> bool:
        return urlparse(path).scheme in ("http", "https")

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
