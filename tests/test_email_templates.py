import unittest

from jinja2 import Environment, FileSystemLoader


class EmailTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = Environment(loader=FileSystemLoader("templates"))

    def test_digest_template_renders_articles_and_stats(self):
        html = self.env.get_template("rss_template.html").render({
            "subject": "今天的 RSS 订阅更新",
            "generated_at": "2026-11-04 08:22",
            "due_at": "2026-11-04 08:00",
            "total": 2,
            "shown": 2,
            "omitted": 0,
            "articles": [
                {
                    "title": "<b>第一篇</b>",
                    "author": "友链 A",
                    "created": "2026-11-04 07:00",
                    "link": "https://a.example/post?x=1&y=2",
                },
                {
                    "title": "第二篇",
                    "author": "友链 B",
                    "created": "2026-11-03 21:00",
                    "link": "https://b.example/post",
                },
            ],
            "statistical_data": {
                "friends_num": 12,
                "active_num": 9,
                "error_num": 3,
            },
        })

        self.assertIn("今天的 RSS 订阅更新", html)
        self.assertIn("第一篇", html)
        self.assertNotIn("<b>第一篇</b>", html)
        self.assertIn("https://a.example/post?x=1&amp;y=2", html)
        self.assertIn("12", html)
        self.assertIn("02", html)  # 第二篇文章的序号
        self.assertIn('role="presentation"', html)
        self.assertIn('width="600"', html)
        self.assertIn("bgcolor=", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<img", html.lower())
        self.assertNotIn("display:flex", html)
        self.assertNotIn("position:absolute", html)
        self.assertNotIn("@import", html)
        self.assertNotIn("background-image", html)
        self.assertNotIn("url(", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)

    def test_article_template_renders_single_article(self):
        html = self.env.get_template("article_notify.html").render({
            "website_title": "示例博客",
            "title": "秋日书简 <script>alert(1)</script>",
            "summary": "这是一段 <b>摘要</b> 内容。",
            "published": "2026-11-04 07:00",
            "link": "https://blog.example/post",
            "github_issue_url": "https://github.com/example/repo/issues?q=is%3Aissue",
        })

        self.assertIn("示例博客", html)
        self.assertIn("秋日书简", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<img", html.lower())
        self.assertIn("这是一段 摘要 内容。", html)
        self.assertIn("https://blog.example/post", html)
        self.assertIn("取消订阅", html)
        self.assertIn("阅读全文", html)
        self.assertIn('role="presentation"', html)
        self.assertIn('width="600"', html)
        self.assertIn("bgcolor=", html)
        self.assertNotIn("display:flex", html)
        self.assertNotIn("position:absolute", html)
        self.assertNotIn("@import", html)
        self.assertNotIn("background-image", html)
        self.assertNotIn("url(", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)


if __name__ == "__main__":
    unittest.main()
