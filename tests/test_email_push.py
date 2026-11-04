import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from friend_circle_lite.application import (
    EMAIL_PUSH_INITIALIZED_KEY,
    EMAIL_PUSH_LAST_SENT_KEY,
    FriendCircleLiteApplication,
)
from friend_circle_lite.config.models import ApplicationConfig, MailRuntime
from friend_circle_lite.domain.models import SHANGHAI_TZ
from friend_circle_lite.utils.cron import CronExpression, CronSyntaxError


class EmailPushTest(unittest.TestCase):
    def test_cron_expression_matches_minutes_and_ranges(self):
        daily = CronExpression.parse("0 8 * * *")
        self.assertTrue(daily.matches(datetime(2026, 11, 4, 8, 0)))
        self.assertFalse(daily.matches(datetime(2026, 11, 4, 8, 1)))
        self.assertFalse(daily.matches(datetime(2026, 11, 4, 9, 0)))

        stepped = CronExpression.parse("*/15 9-10 * * 1-5")
        self.assertTrue(stepped.matches(datetime(2026, 11, 4, 9, 45)))  # Wednesday
        self.assertFalse(stepped.matches(datetime(2026, 11, 7, 9, 45)))  # Saturday

        with self.assertRaises(CronSyntaxError):
            CronExpression.parse("0 8 * *")

    def test_cron_latest_occurrence_is_the_last_planned_minute(self):
        daily = CronExpression.parse("0 8 * * *")

        latest = daily.latest_occurrence(datetime(2026, 11, 4, 12, 22))

        self.assertEqual(latest, datetime(2026, 11, 4, 8, 0))

    def test_email_push_config_parses_cron_aliases_and_default_templates(self):
        config = ApplicationConfig.from_dict({
            "email_push": {"crontab": "30 7 * * *"},
            "rss_subscribe": {},
        })

        self.assertEqual(config.email_push.cron, "30 7 * * *")
        self.assertEqual(config.email_push.body_template, "./templates/rss_template.html")
        self.assertEqual(config.email_push.max_articles, 50)
        self.assertEqual(config.rss_subscribe.email_template, "./templates/article_notify.html")

    def test_email_push_due_waits_for_next_planned_minute_after_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ApplicationConfig.from_dict({
                "email_push": {"enable": True, "to_email": "me@example.com"},
                "runtime_paths": {"cache_file": str(Path(temp_dir) / "cache.sqlite3")},
            })
            app = FriendCircleLiteApplication(config)
            app.state_store.set(EMAIL_PUSH_INITIALIZED_KEY, "2026-11-04T06:00:00+08:00")

            due = app._email_push_due(now=datetime(2026, 11, 4, 12, 22, tzinfo=SHANGHAI_TZ))

        self.assertEqual(due, datetime(2026, 11, 4, 8, 0, tzinfo=SHANGHAI_TZ))

    def test_email_push_does_not_repeat_a_planned_minute(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ApplicationConfig.from_dict({
                "email_push": {"enable": True, "to_email": "me@example.com"},
                "runtime_paths": {"cache_file": str(Path(temp_dir) / "cache.sqlite3")},
            })
            app = FriendCircleLiteApplication(config)
            app.state_store.set(EMAIL_PUSH_INITIALIZED_KEY, "2026-11-03T00:00:00+08:00")
            app.state_store.set(EMAIL_PUSH_LAST_SENT_KEY, "2026-11-04T08:00:00+08:00")

            due = app._email_push_due(now=datetime(2026, 11, 4, 12, 22, tzinfo=SHANGHAI_TZ))

        self.assertIsNone(due)

    def test_email_push_sends_digest_and_records_planned_minute(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ApplicationConfig.from_dict({
                "email_push": {
                    "enable": True,
                    "to_email": "me@example.com",
                    "subject": "Daily digest",
                    "body_template": "./templates/rss_template.html",
                    "cron": "0 8 * * *",
                },
                "runtime_paths": {"cache_file": str(Path(temp_dir) / "cache.sqlite3")},
            })
            app = FriendCircleLiteApplication(config)
            app.latest_articles = [{
                "title": "Post",
                "created": "2026-11-04 07:00",
                "link": "https://site.example/post",
                "author": "Site",
                "avatar": "",
            }]
            app.latest_statistics = {
                "friends_num": 1,
                "active_num": 1,
                "error_num": 0,
                "article_num": 1,
            }
            mail_runtime = MailRuntime(
                sender_email="sender@example.com",
                smtp_server="smtp.example.com",
                port=465,
                password="secret",
                use_tls=True,
            )
            due = datetime(2026, 11, 4, 8, 0, tzinfo=SHANGHAI_TZ)

            with patch.object(app, "_email_push_due", return_value=due), \
                patch(
                    "friend_circle_lite.application.send_emails",
                    return_value={"sent_success": 1},
                ) as send:
                app.run_email_push_if_enabled(mail_runtime)

            self.assertEqual(app.state_store.get(EMAIL_PUSH_LAST_SENT_KEY), due.isoformat())
            send.assert_called_once()
            kwargs = send.call_args.kwargs
            self.assertEqual(kwargs["emails"], ["me@example.com"])
            self.assertEqual(kwargs["subject"], "Daily digest")
            self.assertEqual(kwargs["template_data"]["articles"], app.latest_articles)
            self.assertEqual(kwargs["template_data"]["shown"], 1)
            self.assertEqual(kwargs["template_data"]["omitted"], 0)
            self.assertIn("Post", kwargs["body"])

    def test_email_push_limits_articles_to_avoid_gmail_clipping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ApplicationConfig.from_dict({
                "email_push": {
                    "enable": True,
                    "to_email": "me@example.com",
                    "max_articles": 1,
                },
                "runtime_paths": {"cache_file": str(Path(temp_dir) / "cache.sqlite3")},
            })
            app = FriendCircleLiteApplication(config)
            app.latest_articles = [
                {"title": "First", "created": "2026-11-04 07:00", "link": "https://a", "author": "A", "avatar": ""},
                {"title": "Second", "created": "2026-11-04 06:00", "link": "https://b", "author": "B", "avatar": ""},
            ]
            app.latest_statistics = {"friends_num": 2, "active_num": 2, "error_num": 0, "article_num": 2}
            mail_runtime = MailRuntime(
                sender_email="sender@example.com",
                smtp_server="smtp.example.com",
                port=465,
                password="secret",
                use_tls=True,
            )
            due = datetime(2026, 11, 4, 8, 0, tzinfo=SHANGHAI_TZ)

            with patch.object(app, "_email_push_due", return_value=due), \
                patch(
                    "friend_circle_lite.application.send_emails",
                    return_value={"sent_success": 1},
                ) as send:
                app.run_email_push_if_enabled(mail_runtime)

            template_data = send.call_args.kwargs["template_data"]
            self.assertEqual([article["title"] for article in template_data["articles"]], ["First"])
            self.assertEqual(template_data["shown"], 1)
            self.assertEqual(template_data["total"], 2)
            self.assertEqual(template_data["omitted"], 1)
            self.assertIn("另有 1 篇", send.call_args.kwargs["body"])


if __name__ == "__main__":
    unittest.main()
