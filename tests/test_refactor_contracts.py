import unittest
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import requests

from friend_circle_lite.config.models import ProxySettings
from friend_circle_lite.config.printer import print_startup_config
from friend_circle_lite.crawler.http_client import WebFetchClient
from friend_circle_lite.crawler.service import FeedResolver, FriendCircleCrawlService, SingleSiteCrawler
from friend_circle_lite.all_friends import deal_with_large_data, merge_link_data_from_json_url
from friend_circle_lite.app_config import ApplicationConfig
from friend_circle_lite.cli import FriendCircleLiteApplication
from friend_circle_lite.link_checker.service import LinkReachabilityService
from friend_circle_lite.models import Article, CacheRecord, FeedEndpoint, LinkCheckRecord, LinkMethodStatus, Website
from friend_circle_lite.outputs.legacy_api import _to_public_link
from friend_circle_lite.storage.diagnostics import SQLiteDebugDumper


class RefactorContractsTest(unittest.TestCase):
    def test_github_action_schedule_uses_22_minute_offset(self):
        workflow = Path(".github/workflows/friend_circle_lite.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "22 */4 * * *"', workflow)
        self.assertNotIn('cron: "0 */4 * * *"', workflow)

    def test_github_actions_opt_into_node24_runtime(self):
        workflow_paths = [
            Path(".github/workflows/friend_circle_lite.yml"),
            Path(".github/workflows/deal_subscribe_issue.yml"),
        ]

        for workflow_path in workflow_paths:
            with self.subTest(workflow=str(workflow_path)):
                workflow = workflow_path.read_text(encoding="utf-8")
                self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true", workflow)

    def test_static_index_is_standalone_dashboard_with_view_switch(self):
        html = Path("static/index.html").read_text(encoding="utf-8")

        self.assertIn('data-view="links"', html)
        self.assertIn('data-view="articles"', html)
        self.assertIn('["first24", "前 24 条"]', html)
        link_config_start = html.index("links:", html.index("viewConfig"))
        self.assertIn('defaultFilter: "unreachable"', html[link_config_start:html.index("articles:", link_config_start)])
        self.assertLess(
            html.index('["unreachable", "不可达"]', link_config_start),
            html.index('["all", "全部"]', link_config_start),
        )
        article_config_start = html.index("articles:", html.index("viewConfig"))
        self.assertLess(
            html.index('["first24", "前 24 条"]', article_config_start),
            html.index('["all", "全部"]', article_config_start),
        )
        self.assertIn("scrollbar-width: thin", html)
        self.assertIn("::-webkit-scrollbar", html)
        self.assertIn(".dashboard {\n        display: grid;\n        align-items: start;", html)
        self.assertIn(".content-grid {\n        display: grid;\n        align-items: start;", html)
        self.assertIn("align-self: start", html)
        self.assertIn("-webkit-line-clamp: 2", html)
        self.assertIn("article-avatar-mark", html)
        self.assertIn("article.avatar", html)
        self.assertIn("https://github.com/willow-god/Friend-Circle-Lite", html)
        self.assertIn("poem-background", html)
        self.assertIn("icon-badge", html)
        self.assertIn("title=", html)
        self.assertIn("Promise.all", html)
        self.assertIn("link.json", html)
        self.assertIn("all.json", html)
        self.assertNotIn("fclite.js", html)
        self.assertNotIn("fclite.css", html)

    def test_link_check_uses_cached_rss_without_homepage_request(self):
        class Store:
            def load_records(self, urls):
                return {}

            def save_records(self, records):
                return True

        class Parser:
            def parse(self, feed_url, count=1, blog_url=""):
                return [Article(title="Post", author="Site", link="https://site.example/post", published="2026-06-07 10:00")]

        class Fetcher:
            calls = []

            def get(self, *args, **kwargs):
                self.calls.append(args[0])
                raise AssertionError("主页不应该在 RSS 可解析时被请求")

        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({"link_check": {"enable": True}}).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            feed_records=[CacheRecord(name="Site", url="https://site.example/rss.xml", source="cache")],
            feed_parser=Parser(),
            fetcher=Fetcher(),
        )

        records = service.check_websites([Website(name="Site", url="https://site.example", avatar="avatar.png")])

        self.assertTrue(records[0].reachable)
        self.assertTrue(records[0].crawl_allowed)
        self.assertEqual(records[0].best_method, "rss_cache")

    def test_link_check_logs_total_cached_and_actual_check_counts(self):
        class Store:
            def load_records(self, urls):
                return {
                    "https://cached.example/": LinkCheckRecord(
                        name="Cached",
                        url="https://cached.example/",
                        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        reachable=True,
                        crawl_allowed=False,
                        best_method="homepage",
                        best_latency=0.2,
                    )
                }

            def save_records(self, records):
                return True

            def is_fresh(self, record, max_age_hours):
                return True

        class Discovery:
            def discover(self, website_url):
                return None

        class Response:
            status_code = 200

        class Fetcher:
            def get(self, *args, **kwargs):
                return type("Result", (), {"response": Response(), "latency": 0.1, "success": True})()

        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({"link_check": {"max_age_hours": 24}}).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            feed_parser=type("Parser", (), {"parse": lambda self, *args, **kwargs: [], "last_latency": 0.01})(),
            feed_discovery=Discovery(),
            fetcher=Fetcher(),
        )

        with patch("logging.info") as info:
            service.check_websites([
                Website(name="Cached", url="https://cached.example/", avatar="cached.png"),
                Website(name="Fresh", url="https://fresh.example/", avatar="fresh.png"),
            ])

        messages = "\n".join(str(call.args[0]) for call in info.call_args_list)
        self.assertIn("[友链检测]", messages)
        self.assertIn("友链总数 2 个", messages)
        self.assertIn("缓存复用 1 个", messages)
        self.assertIn("本次实际检测 1 个", messages)

    def test_crawler_entry_logs_source_and_article_limit_with_module_label(self):
        config = ApplicationConfig.from_dict({
            "spider_settings": {
                "enable": True,
                "json_url": "https://example.com/friends.json",
                "article_count": 3,
            },
            "runtime_paths": {
                "all_json_file": "./tmp/all.json",
                "errors_json_file": "./tmp/errors.json",
                "link_json_file": "./tmp/link.json",
            },
        })
        payload = ({"statistical_data": {}, "article_data": []}, [], {"statistical_data": {}, "link_data": []})

        with patch("friend_circle_lite.cli.fetch_and_process_data", return_value=payload), \
            patch("friend_circle_lite.cli.write_json"), \
            patch("logging.info") as info:
            FriendCircleLiteApplication(config).run_crawler_if_enabled()

        messages = "\n".join(str(call.args[0]) for call in info.call_args_list)
        self.assertIn("[爬虫入口]", messages)
        self.assertIn("https://example.com/friends.json", messages)
        self.assertIn("每站最多 3 篇文章", messages)

    def test_link_check_reuses_cached_linkpage_when_only_trailing_slash_differs(self):
        class Store:
            def load_records(self, urls):
                return {
                    "https://wcowin.work/": LinkCheckRecord(
                        name="Wcowin",
                        url="https://wcowin.work/",
                        linkpage="https://wcowin.work/link/",
                        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        reachable=True,
                        crawl_allowed=False,
                        best_method="homepage",
                        best_latency=0.2,
                    )
                }

            def save_records(self, records):
                raise AssertionError("只差末尾斜杠时不应该重新检测并写入缓存")

            def is_fresh(self, record, max_age_hours):
                return True

        class Fetcher:
            def get(self, *args, **kwargs):
                raise AssertionError("只差末尾斜杠时不应该重新请求网站")

        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({
                "link_check": {
                    "enable_backlink_check": True,
                    "author_url": "blog.liushen.fun",
                }
            }).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            fetcher=Fetcher(),
        )

        records = service.check_websites([
            Website(
                name="Wcowin",
                url="https://wcowin.work/",
                avatar="avatar.png",
                linkpage="https://wcowin.work/link",
            )
        ])

        self.assertEqual(len(records), 1)
        self.assertTrue(records[0].reachable)
        self.assertFalse(records[0].crawl_allowed)

    def test_linkpage_change_refreshes_backlink_only(self):
        saved_records = []

        class Store:
            def load_records(self, urls):
                return {
                    "https://site.example/": LinkCheckRecord(
                        name="Site",
                        url="https://site.example/",
                        linkpage="https://site.example/old-links/",
                        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        reachable=True,
                        crawl_allowed=False,
                        best_method="homepage",
                        best_latency=0.2,
                        backlink_checked=True,
                        has_author_link=False,
                    )
                }

            def save_records(self, records):
                saved_records.extend(records)
                return True

            def is_fresh(self, record, max_age_hours):
                return True

        class Response:
            status_code = 200
            text = '<a href="https://blog.liushen.fun/">清羽飞扬</a>'

        class Fetcher:
            calls = []

            def get(self, url, *args, **kwargs):
                self.calls.append(url)
                if url != "https://site.example/new-links/":
                    raise AssertionError("反链页变化时只应请求新的友链页")
                return type("Result", (), {"response": Response(), "latency": 0.2, "success": True})()

        fetcher = Fetcher()
        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({
                "link_check": {
                    "enable_backlink_check": True,
                    "author_url": "blog.liushen.fun",
                }
            }).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            fetcher=fetcher,
        )

        records = service.check_websites([
            Website(
                name="Site",
                url="https://site.example/",
                avatar="avatar.png",
                linkpage="https://site.example/new-links/",
            )
        ])

        self.assertEqual(fetcher.calls, ["https://site.example/new-links/"])
        self.assertEqual(len(saved_records), 1)
        self.assertTrue(records[0].has_author_link)
        self.assertEqual(records[0].linkpage, "https://site.example/new-links/")

    def test_link_check_revalidates_legacy_crawlable_cache_without_rss_method(self):
        class Store:
            def load_records(self, urls):
                return {
                    "https://site.example": LinkCheckRecord(
                        name="Site",
                        url="https://site.example",
                        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        reachable=True,
                        crawl_allowed=True,
                        best_method="direct",
                    )
                }

            def save_records(self, records):
                return True

            def is_fresh(self, record, max_age_hours):
                return True

        class Parser:
            def parse(self, feed_url, count=1, blog_url=""):
                return [Article(title="Post", author="Site", link="https://site.example/post", published="2026-06-07 10:00")]

        class Discovery:
            calls = 0

            def discover(self, website_url):
                self.calls += 1
                return FeedEndpoint(url="https://site.example/rss.xml", feed_type="specific", source="auto")

        discovery = Discovery()
        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({"link_check": {"max_age_hours": 24}}).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            feed_records=[],
            feed_parser=Parser(),
            feed_discovery=discovery,
        )

        records = service.check_websites([Website(name="Site", url="https://site.example", avatar="avatar.png")])

        self.assertEqual(discovery.calls, 1)
        self.assertTrue(records[0].crawl_allowed)
        self.assertEqual(records[0].best_method, "rss")

    def test_link_check_revalidates_fresh_cache_without_measured_latency(self):
        saved_records = []

        class Store:
            def load_records(self, urls):
                return {
                    "https://site.example/": LinkCheckRecord(
                        name="Site",
                        url="https://site.example/",
                        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        reachable=True,
                        crawl_allowed=True,
                        best_method="rss_cache",
                        best_latency=-1,
                    )
                }

            def save_records(self, records):
                saved_records.extend(records)
                return True

            def is_fresh(self, record, max_age_hours):
                return True

        class Parser:
            last_latency = 0.23

            def parse(self, feed_url, count=1, blog_url=""):
                return [Article(title="Post", author="Site", link="https://site.example/post", published="2026-06-07 10:00")]

        class Discovery:
            calls = 0

            def discover(self, website_url):
                self.calls += 1
                return FeedEndpoint(url="https://site.example/rss.xml", feed_type="specific", source="auto")

        discovery = Discovery()
        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({"link_check": {"max_age_hours": 24}}).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            feed_records=[],
            feed_parser=Parser(),
            feed_discovery=discovery,
        )

        records = service.check_websites([Website(name="Site", url="https://site.example", avatar="avatar.png")])

        self.assertEqual(discovery.calls, 1)
        self.assertEqual(len(saved_records), 1)
        self.assertEqual(records[0].best_latency, 0.23)
        self.assertGreater(records[0].to_link_dict()["latency"], 0)

    def test_link_check_revalidates_fresh_homepage_cache_without_measured_latency(self):
        saved_records = []

        class Store:
            def load_records(self, urls):
                return {
                    "https://site.example/": LinkCheckRecord(
                        name="Site",
                        url="https://site.example/",
                        checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        reachable=True,
                        crawl_allowed=False,
                        best_method="homepage",
                        best_latency=-1,
                    )
                }

            def save_records(self, records):
                saved_records.extend(records)
                return True

            def is_fresh(self, record, max_age_hours):
                return True

        class Discovery:
            def discover(self, website_url):
                return None

        class Response:
            status_code = 200

        class Fetcher:
            calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                return type("Result", (), {"response": Response(), "latency": 0.31, "success": True})()

        fetcher = Fetcher()
        service = LinkReachabilityService(
            config=ApplicationConfig.from_dict({"link_check": {"max_age_hours": 24}}).link_check,
            proxy_settings=ProxySettings(),
            store=Store(),
            feed_parser=type("Parser", (), {"parse": lambda self, *args, **kwargs: [], "last_latency": 0.01})(),
            feed_discovery=Discovery(),
            fetcher=fetcher,
        )

        records = service.check_websites([Website(name="Site", url="https://site.example", avatar="avatar.png")])

        self.assertEqual(fetcher.calls, 1)
        self.assertEqual(len(saved_records), 1)
        self.assertEqual(records[0].best_latency, 0.31)

    def test_article_crawl_does_not_rediscover_invalid_cached_rss(self):
        class Parser:
            def parse(self, feed_url, count=1, blog_url=""):
                return []

        class Discovery:
            calls = 0

            def discover(self, website_url):
                self.calls += 1
                return FeedEndpoint(url="https://site.example/new-rss.xml", feed_type="specific", source="auto")

        discovery = Discovery()
        resolver = FeedResolver(
            discovery_service=discovery,
            configured_feeds=[CacheRecord(name="Site", url="https://site.example/rss.xml", source="cache")],
        )
        crawler = SingleSiteCrawler(parser_service=Parser(), resolver=resolver)

        result = crawler.crawl(Website(name="Site", url="https://site.example", avatar="avatar.png"), count=1)

        self.assertEqual(discovery.calls, 0)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.cache_update.action, "none")

    def test_web_fetch_client_falls_back_to_proxy_url(self):
        calls = []

        class Response:
            status_code = 200
            text = "ok"

        class Session:
            def get(self, url, headers=None, timeout=None):
                calls.append(url)
                if len(calls) == 1:
                    raise requests.RequestException("direct failed")
                return Response()

        client = WebFetchClient(Session(), ProxySettings(proxy_url="https://proxy.example/{url}"))

        result = client.get("https://site.example/feed.xml", desc="RSS")

        self.assertTrue(result.success)
        self.assertTrue(result.used_proxy)
        self.assertEqual(calls, [
            "https://site.example/feed.xml",
            "https://proxy.example/https://site.example/feed.xml",
        ])

    def test_web_fetch_client_records_positive_latency_for_request_exception(self):
        class Session:
            def get(self, url, headers=None, timeout=None):
                raise requests.RequestException("direct failed")

        client = WebFetchClient(Session(), ProxySettings())

        with patch("time.time", side_effect=[10.0, 10.0]):
            result = client.get("https://site.example/feed.xml", desc="RSS")

        self.assertFalse(result.success)
        self.assertGreater(result.latency, 0)
        self.assertNotEqual(result.latency, 0.0)

    def test_web_fetch_client_does_not_log_proxy_service_url(self):
        class Session:
            def __init__(self):
                self.calls = 0

            def get(self, url, headers=None, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise requests.RequestException("direct failed")
                raise requests.RequestException("HTTPSConnectionPool(host='proxy.example', port=443)")

        client = WebFetchClient(Session(), ProxySettings(proxy_url="https://proxy.example/"))

        with patch("logging.warning") as warning:
            client.get("https://site.example/feed.xml", desc="RSS")

        messages = "\n".join(str(call.args[0]) for call in warning.call_args_list)
        self.assertNotIn("https://proxy.example", messages)
        self.assertNotIn("proxy.example", messages)
        self.assertIn("https://site.example/feed.xml", messages)

    def test_startup_config_does_not_log_proxy_service_url(self):
        config = ApplicationConfig.from_dict({
            "proxy_settings": {"proxy_url": "https://proxy.example/"},
        })

        with patch("logging.info") as info:
            print_startup_config(config)

        messages = "\n".join(str(call.args[0]) for call in info.call_args_list)
        self.assertNotIn("https://proxy.example", messages)
        self.assertIn("代理", messages)

    def test_config_keeps_existing_yaml_keys(self):
        config = ApplicationConfig.from_dict({
            "debug": True,
            "spider_settings": {
                "enable": True,
                "json_url": "https://example.com/friends.json",
                "article_count": 3,
            },
            "proxy_settings": {"proxy_url": "https://proxy.example/"},
            "merge_settings": {
                "enable": True,
                "remote_base_url": "https://remote.example",
                "merge_article_data": False,
                "merge_link_check_data": True,
            },
            "link_check": {
                "enable": False,
                "max_age_hours": 6,
                "timeout": 9,
                "max_workers": 2,
                "status_api_url": "https://status.example?url={url}",
                "enable_backlink_check": True,
                "author_url": "example.com",
            },
            "runtime_paths": {
                "cache_file": "./tmp/state.sqlite3",
                "all_json_file": "./public/all.json",
                "errors_json_file": "./public/errors.json",
                "link_json_file": "./public/link.json",
            },
            "specific_RSS": [{"name": "Manual", "url": "https://example.com/feed.xml"}],
        })

        self.assertEqual(config.spider_settings.json_url, "https://example.com/friends.json")
        self.assertTrue(config.debug)
        self.assertEqual(config.spider_settings.article_count, 3)
        self.assertEqual(config.proxy_settings.proxy_url, "https://proxy.example/")
        self.assertTrue(config.merge_settings.enable)
        self.assertFalse(config.merge_settings.merge_article_data)
        self.assertTrue(config.link_check.enable)
        self.assertEqual(config.link_check.author_url, "example.com")
        self.assertEqual(config.runtime_paths.cache_file, "./tmp/state.sqlite3")
        self.assertEqual(config.specific_rss[0]["name"], "Manual")

    def test_debug_env_enables_sqlite_dump(self):
        with patch.dict("os.environ", {"FCL_DEBUG": "1"}):
            config = ApplicationConfig.from_dict({})

        self.assertTrue(config.debug)

    def test_debug_string_false_stays_disabled(self):
        config = ApplicationConfig.from_dict({"debug": "false"})

        self.assertFalse(config.debug)

    def test_website_and_link_record_public_shapes_are_stable(self):
        website = Website.from_friend_item(["Alice", "https://alice.example", "https://alice.example/links", "avatar.png"])
        self.assertEqual(website.to_error_payload(), ["Alice", "https://alice.example/", "avatar.png"])

        record = LinkCheckRecord(
            name=website.name,
            url=website.url,
            avatar=website.avatar,
            linkpage=website.linkpage,
            checked_at="2026-06-06 12:00:00",
            reachable=True,
            crawl_allowed=True,
            best_method="proxy",
            best_latency=1.2,
            fail_count=0,
            backlink_checked=True,
            has_author_link=True,
            rss_crawl_reason="allowed_by_proxy",
            direct=LinkMethodStatus(False, 403, 2.0),
            proxy=LinkMethodStatus(True, 200, 1.2),
        )

        self.assertEqual(record.to_link_dict(), {
            "name": "Alice",
            "link": "https://alice.example/",
            "link_page": "https://alice.example/links",
            "avatar": "avatar.png",
            "reachable": True,
            "crawlable": True,
            "latency": 1.2,
            "fail_count": 0,
            "has_backlink": True,
        })

    def test_public_link_never_uses_zero_latency_as_unknown_fallback(self):
        public_link = _to_public_link({
            "name": "Legacy",
            "url": "https://legacy.example/",
            "reachable": False,
            "crawl_allowed": False,
            "best_latency": -1,
        })

        self.assertGreater(public_link["latency"], 0)
        self.assertNotEqual(public_link["latency"], 0.0)

    def test_homepage_url_normalization_adds_trailing_slash_to_paths(self):
        website = Website.from_friend_item(["PathSite", "https://example.com/blog", "avatar.png"])

        self.assertEqual(website.url, "https://example.com/blog/")

    def test_load_websites_deduplicates_by_normalized_homepage_url(self):
        service = FriendCircleCrawlService(json_url="https://example.com/friends.json", count=1)

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "friends": [
                        ["Wcowin", "https://wcowin.work", "https://wcowin.work/link", "old.png"],
                        ["Wcowin", "https://wcowin.work/", "https://wcowin.work/link/", "new.png"],
                    ]
                }

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        websites = service._load_websites(Session())

        self.assertEqual(len(websites), 1)
        self.assertEqual(websites[0].url, "https://wcowin.work/")
        self.assertEqual(websites[0].avatar, "new.png")

    def test_large_data_sorting_keeps_public_article_schema(self):
        payload = {
            "statistical_data": {"article_num": 0},
            "article_data": [
                {"title": "Old", "created": "2024-01-01 00:00", "link": "https://old", "author": "A", "avatar": "a.png"},
                {"title": "New", "created": "2024-01-02 00:00", "link": "https://new", "author": "B", "avatar": "b.png"},
            ],
        }

        result = deal_with_large_data(payload)

        self.assertEqual([article["title"] for article in result["article_data"]], ["New", "Old"])
        self.assertEqual(result["statistical_data"]["article_num"], 2)
        self.assertEqual(set(result["article_data"][0].keys()), {"title", "created", "link", "author", "avatar"})

    def test_link_merge_keeps_best_reachability_shape(self):
        local = {
            "statistical_data": {},
            "link_data": [{
                "name": "Site",
                "link": "https://site.example",
                "link_page": "",
                "avatar": "",
                "reachable": True,
                "crawlable": False,
                "method": "api",
                "latency": 3.0,
                "fail_count": 2,
                "checked_at": "2026-06-05 12:00:00",
                "has_backlink": None,
                "reason": "blocked_api_only",
            }],
        }
        remote = {
            "statistical_data": {},
            "link_data": [{
                "name": "Site",
                "link": "https://site.example",
                "link_page": "",
                "avatar": "",
                "reachable": True,
                "crawlable": True,
                "method": "proxy",
                "latency": 1.0,
                "fail_count": 0,
                "checked_at": "2026-06-06 12:00:00",
                "has_backlink": True,
                "reason": "allowed_by_proxy",
            }],
        }

        class Response:
            def json(self):
                return remote

        with patch("requests.get", return_value=Response()):
            merged = merge_link_data_from_json_url(local, "https://remote.example/link.json")

        self.assertNotIn("method", merged["link_data"][0])
        self.assertNotIn("checked_at", merged["link_data"][0])
        self.assertNotIn("reason", merged["link_data"][0])
        self.assertEqual(merged["link_data"][0]["latency"], 1.0)
        self.assertEqual(merged["link_data"][0]["fail_count"], 0)
        self.assertTrue(merged["link_data"][0]["has_backlink"])
        self.assertEqual(merged["statistical_data"]["link_total_num"], 1)

    def test_all_json_statistics_do_not_include_link_statistics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FriendCircleCrawlService(
                json_url="https://example.com/friends.json",
                count=1,
                cache_file=str(Path(temp_dir) / "cache.sqlite3"),
            )
            website = Website(name="Site", url="https://site.example", avatar="avatar.png")

            def load_websites(_session):
                return [website]

            def check_links(_websites, _feed_records, _manual_names):
                return [
                    LinkCheckRecord(
                        name="Site",
                        url="https://site.example",
                        avatar="avatar.png",
                        checked_at="2026-06-07 12:00:00",
                        reachable=False,
                        crawl_allowed=False,
                    )
                ]

            service._load_websites = load_websites
            service._check_links = check_links

            all_payload, _errors, link_payload = service.run()

        self.assertEqual(set(all_payload["statistical_data"].keys()), {
            "friends_num",
            "active_num",
            "error_num",
            "article_num",
            "last_updated_time",
        })
        self.assertIn("link_total_num", link_payload["statistical_data"])

    def test_crawl_filter_uses_crawl_allowed_and_feed_cache_not_best_method(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FriendCircleCrawlService(
                json_url="https://example.com/friends.json",
                count=1,
                specific_rss=[{"name": "WithRSS", "url": "https://with.example/rss.xml"}],
                cache_file=str(Path(temp_dir) / "cache.sqlite3"),
            )
            websites = [
                Website(name="WithRSS", url="https://with.example", avatar="with.png"),
                Website(name="NoRSS", url="https://no.example", avatar="no.png"),
            ]

            def load_websites(_session):
                return websites

            def check_links(_websites, _feed_records, _manual_names):
                return [
                    LinkCheckRecord(
                        name="WithRSS",
                        url="https://with.example",
                        avatar="with.png",
                        checked_at="2026-06-07 12:00:00",
                        reachable=True,
                        crawl_allowed=True,
                        best_method="homepage",
                    ),
                    LinkCheckRecord(
                        name="NoRSS",
                        url="https://no.example",
                        avatar="no.png",
                        checked_at="2026-06-07 12:00:00",
                        reachable=True,
                        crawl_allowed=True,
                        best_method="rss",
                    ),
                ]

            crawled_names = []

            def crawl(_crawler, website, count):
                crawled_names.append(website.name)
                return type("Result", (), {
                    "website": website,
                    "status": "active",
                    "articles": [
                        Article(
                            title=f"{website.name} Post",
                            author=website.name,
                            link=f"{website.url}/post",
                            published="2026-06-07 10:00",
                            avatar=website.avatar,
                        )
                    ],
                    "feed_url": "https://with.example/rss.xml",
                    "feed_type": "specific",
                    "source_used": "manual",
                    "cache_update": type("Update", (), {"name": None, "action": "none", "url": None})(),
                })()

            service._load_websites = load_websites
            service._check_links = check_links

            with patch("friend_circle_lite.crawler.service.SingleSiteCrawler.crawl", crawl):
                service.run()

        self.assertEqual(crawled_names, ["WithRSS"])

    def test_sqlite_debug_dumper_prints_all_rows_and_cleans_extra_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cache.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE feed_cache (
                        name TEXT PRIMARY KEY,
                        url TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'cache',
                        old_column TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO feed_cache(name, url, source, old_column) VALUES (?, ?, ?, ?)",
                    ("Site", "https://site.example/rss.xml", "cache", "legacy"),
                )
                connection.commit()

            output = SQLiteDebugDumper(db_path).run()

            self.assertIn("feed_cache", output)
            self.assertIn("https://site.example/rss.xml", output)
            self.assertIn("old_column", output)
            with closing(sqlite3.connect(db_path)) as connection:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(feed_cache)").fetchall()]
            self.assertEqual(columns, ["name", "url", "source"])

    def test_sqlite_debug_dumper_rebuilds_tables_with_missing_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cache.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE link_check_state (
                        url TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        reachable INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO link_check_state(url, name, reachable) VALUES (?, ?, ?)",
                    ("https://site.example", "Site", 1),
                )
                connection.commit()

            output = SQLiteDebugDumper(db_path).run()

            self.assertIn("缺少当前字段", output)
            with closing(sqlite3.connect(db_path)) as connection:
                row = connection.execute(
                    "SELECT url, name, checked_at, crawl_allowed, best_method FROM link_check_state"
                ).fetchone()
            self.assertEqual(row, ("https://site.example", "Site", "", 0, "none"))


if __name__ == "__main__":
    unittest.main()
