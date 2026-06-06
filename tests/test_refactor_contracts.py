import unittest
from unittest.mock import patch

from friend_circle_lite.all_friends import deal_with_large_data, merge_link_data_from_json_url
from friend_circle_lite.app_config import ApplicationConfig
from friend_circle_lite.models import LinkCheckRecord, LinkMethodStatus, Website


class RefactorContractsTest(unittest.TestCase):
    def test_config_keeps_existing_yaml_keys(self):
        config = ApplicationConfig.from_dict({
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
        self.assertEqual(config.spider_settings.article_count, 3)
        self.assertEqual(config.proxy_settings.proxy_url, "https://proxy.example/")
        self.assertTrue(config.merge_settings.enable)
        self.assertFalse(config.merge_settings.merge_article_data)
        self.assertFalse(config.link_check.enable)
        self.assertEqual(config.link_check.author_url, "example.com")
        self.assertEqual(config.runtime_paths.cache_file, "./tmp/state.sqlite3")
        self.assertEqual(config.specific_rss[0]["name"], "Manual")

    def test_website_and_link_record_public_shapes_are_stable(self):
        website = Website.from_friend_item(["Alice", "https://alice.example", "https://alice.example/links", "avatar.png"])
        self.assertEqual(website.to_error_payload(), ["Alice", "https://alice.example", "avatar.png"])

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
            "link": "https://alice.example",
            "link_page": "https://alice.example/links",
            "avatar": "avatar.png",
            "reachable": True,
            "crawlable": True,
            "method": "proxy",
            "latency": 1.2,
            "fail_count": 0,
            "checked_at": "2026-06-06 12:00:00",
            "has_backlink": True,
            "reason": "allowed_by_proxy",
        })

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

        self.assertEqual(merged["link_data"][0]["method"], "proxy")
        self.assertEqual(merged["link_data"][0]["latency"], 1.0)
        self.assertEqual(merged["link_data"][0]["fail_count"], 0)
        self.assertTrue(merged["link_data"][0]["has_backlink"])
        self.assertEqual(merged["statistical_data"]["link_total_num"], 1)


if __name__ == "__main__":
    unittest.main()
