import unittest

from friend_circle_lite.crawler.feed_parser import FeedParserService
from friend_circle_lite.outputs.processing import finalize_article_data


class ArticleFilteringTest(unittest.TestCase):
    def test_feed_parser_discards_articles_without_title(self):
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Test</title>
        <item><title>Valid post</title><link>https://site.example/valid</link>
            <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
        <item><title>   </title><link>https://site.example/blank</link>
            <pubDate>Tue, 02 Jun 2026 10:00:00 GMT</pubDate></item>
        <item><title></title><link>https://site.example/empty</link>
            <pubDate>Wed, 03 Jun 2026 10:00:00 GMT</pubDate></item>
        </channel></rss>"""

        class Response:
            status_code = 200
            text = rss
            encoding = "utf-8"

        class Fetcher:
            def get(self, *args, **kwargs):
                return type("Result", (), {"response": Response(), "latency": 0.1})()

        parser = FeedParserService(session=None)
        parser.fetcher = Fetcher()

        articles = parser.parse("https://site.example/feed.xml", count=10)

        self.assertEqual([article.title for article in articles], ["Valid post"])
        self.assertEqual(articles[0].link, "https://site.example/valid")

    def test_article_processing_discards_articles_without_title(self):
        payload = {
            "statistical_data": {"article_num": 3},
            "article_data": [
                {"title": "", "created": "2026-06-03 10:00", "link": "https://a", "author": "A", "avatar": ""},
                {"created": "2026-06-02 10:00", "link": "https://b", "author": "B", "avatar": ""},
                {"title": "Kept", "created": "2026-06-01 10:00", "link": "https://c", "author": "C", "avatar": ""},
            ],
        }

        result = finalize_article_data(payload)

        self.assertEqual([article["title"] for article in result["article_data"]], ["Kept"])
        self.assertEqual(result["statistical_data"]["article_num"], 1)


if __name__ == "__main__":
    unittest.main()
