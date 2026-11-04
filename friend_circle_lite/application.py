"""Application service coordinating crawl and notification workflows."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from friend_circle_lite.config.models import (
    DEFAULT_EMAIL_PUSH_TEMPLATE,
    DEFAULT_RSS_SUBSCRIBE_TEMPLATE,
    ApplicationConfig,
    MailRuntime,
)
from friend_circle_lite.config.printer import print_startup_config
from friend_circle_lite.crawler.latest_articles import get_latest_articles_from_link
from friend_circle_lite.crawler.service import FriendCircleCrawlService
from friend_circle_lite.domain.models import SHANGHAI_TZ
from friend_circle_lite.notifications.github import extract_emails_from_issues
from friend_circle_lite.notifications.mail import send_emails
from friend_circle_lite.outputs.json_io import write_json
from friend_circle_lite.outputs.merge import merge_article_data, merge_error_data, merge_link_data
from friend_circle_lite.outputs.processing import finalize_article_data
from friend_circle_lite.storage.diagnostics import SQLiteDebugDumper
from friend_circle_lite.storage.state_store import StateStore
from friend_circle_lite.utils.cron import CronExpression, CronSyntaxError


EMAIL_PUSH_INITIALIZED_KEY = "email_push_initialized_at"
EMAIL_PUSH_LAST_SENT_KEY = "email_push_last_sent_at"


class FriendCircleLiteApplication:
    """Application service coordinating crawl and notification workflows."""

    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.state_store = StateStore(config.runtime_paths.cache_file)
        self.latest_articles: list[dict] = []
        self.latest_statistics: dict = {}

    def run(self) -> None:
        """Execute the enabled application features in a stable order."""
        try:
            print_startup_config(self.config)
            self.run_crawler_if_enabled()
            mail_runtime = self.prepare_mail_runtime()
            self.run_email_push_if_enabled(mail_runtime)
            self.run_rss_subscription_if_enabled(mail_runtime)
        finally:
            self.dump_sqlite_debug_if_enabled()

    def dump_sqlite_debug_if_enabled(self) -> None:
        """在 debug 开启时输出 SQLite 全量缓存数据，便于排查 Action 问题。"""
        if not self.config.debug:
            return
        SQLiteDebugDumper(self.config.runtime_paths.cache_file).run()

    def run_crawler_if_enabled(self) -> None:
        """Run the article crawl and persist public output files when enabled."""
        spider_settings = self.config.spider_settings
        if not spider_settings.enable:
            logging.info("[爬虫入口] 爬虫未启用，跳过抓取流程")
            return

        logging.info("[爬虫入口] 爬虫已启用")
        logging.info(
            f"[爬虫入口] 正在从 {spider_settings.json_url} 获取友链原始数据，"
            f"每站最多 {spider_settings.article_count} 篇文章"
        )

        crawl_result = FriendCircleCrawlService(
            json_url=spider_settings.json_url,
            count=spider_settings.article_count,
            specific_rss=self.config.specific_rss,
            cache_file=self.config.runtime_paths.cache_file,
            link_check_config=self.config.link_check,
            proxy_settings=self.config.proxy_settings,
        ).run()
        if crawl_result is None:
            logging.error("[爬虫入口] 抓取流程失败，未生成任何输出文件")
            return

        result, lost_friends, link_payload = crawl_result
        result, lost_friends, link_payload = self._merge_remote_results_if_enabled(
            result, lost_friends, link_payload
        )

        article_count = len(result.get("article_data", []))
        logging.info(f"[爬虫入口] 数据获取完毕，共有 {article_count} 篇文章，正在处理输出文件")

        result = finalize_article_data(
            result,
            future_tolerance_days=self.config.future_article_tolerance_days,
        )
        self.latest_articles = list(result.get("article_data", []))
        self.latest_statistics = dict(result.get("statistical_data", {}))
        write_json(self.config.runtime_paths.all_json_file, result)
        write_json(self.config.runtime_paths.errors_json_file, lost_friends)
        write_json(self.config.runtime_paths.link_json_file, link_payload)

    def prepare_mail_runtime(self) -> MailRuntime:
        """Build SMTP runtime credentials from config and environment variables."""
        if not (self.config.email_push.enable or self.config.rss_subscribe.enable):
            return MailRuntime(sender_email="", smtp_server="", port=0, password="", use_tls=False)

        logging.info("📨 推送功能已启用，正在准备中...")
        smtp_conf = self.config.smtp
        mail_runtime = MailRuntime(
            sender_email=smtp_conf.email,
            smtp_server=smtp_conf.server,
            port=smtp_conf.port,
            password=os.getenv("SMTP_PWD", ""),
            use_tls=smtp_conf.use_tls,
        )

        logging.info(f"📡 SMTP 服务器：{mail_runtime.smtp_server}:{mail_runtime.port}")
        if mail_runtime.is_ready:
            logging.info(f"🔐 密码(部分)：{mail_runtime.password[:3]}*****")
        else:
            logging.error("❌ SMTP 信息不完整或环境变量 SMTP_PWD 未设置，无法发送邮件")
        return mail_runtime

    def run_email_push_if_enabled(self, mail_runtime: MailRuntime) -> None:
        """Send the fetched friend-circle articles to the configured mailbox.

        The push is driven by a five-field cron expression rather than the
        workflow's own schedule: the first run at or after a planned minute
        sends the digest, and the sent minute is persisted so later runs do not
        repeat it.
        """
        email_push = self.config.email_push
        if not email_push.enable:
            return
        if not mail_runtime.is_ready:
            logging.info("⏭️ 邮件推送未执行，因为 SMTP 尚未就绪")
            return

        to_email = email_push.to_email.strip()
        if not to_email or "@" not in to_email:
            logging.error("❌ 邮件推送已启用，但 to_email 未配置或格式不正确")
            return

        due_at = self._email_push_due()
        if due_at is None:
            return
        if not self.latest_articles:
            logging.info("📭 本轮没有抓取到文章，跳过邮件推送")
            return

        subject = email_push.subject
        template_path = self._resolve_template_path(email_push.body_template, DEFAULT_EMAIL_PUSH_TEMPLATE)
        if not template_path.is_file():
            logging.warning(f"⚠️ 邮件模板不存在，将仅发送纯文本：{template_path}")

        logging.info(f"📧 正在推送邮件到 {to_email}，计划时间 {due_at:%Y-%m-%d %H:%M}")
        summary = send_emails(
            emails=[to_email],
            sender_email=mail_runtime.sender_email,
            smtp_server=mail_runtime.smtp_server,
            port=mail_runtime.port,
            password=mail_runtime.password,
            subject=subject,
            body=self._build_email_push_text_body(subject, due_at),
            template_path=str(template_path),
            template_data=self._build_email_push_template_data(subject, due_at),
            use_tls=mail_runtime.use_tls,
        )
        if summary and summary.get("sent_success"):
            self.state_store.set(EMAIL_PUSH_LAST_SENT_KEY, due_at.isoformat())
            logging.info(f"✅ 邮件推送完成：{len(self.latest_articles)} 篇文章已发送到 {to_email}")
        else:
            logging.error("❌ 邮件推送失败，将在下次运行重试")

    def _email_push_due(self, now: datetime | None = None) -> datetime | None:
        """Return the planned minute that should trigger this run, if any."""
        try:
            cron = CronExpression.parse(self.config.email_push.cron)
        except CronSyntaxError as exc:
            logging.error(f"❌ 邮件推送 cron 配置无效：{exc}")
            return None

        now = now or datetime.now(SHANGHAI_TZ)
        initialized_at = self._parse_state_datetime(self.state_store.get(EMAIL_PUSH_INITIALIZED_KEY))
        if initialized_at is None:
            self.state_store.set(EMAIL_PUSH_INITIALIZED_KEY, now.isoformat())
            logging.info("📧 首次观察邮件推送，已建立时间基线；将在下一个计划时间后的首次运行推送")
            return None

        last_sent_at = self._parse_state_datetime(self.state_store.get(EMAIL_PUSH_LAST_SENT_KEY))
        baseline = last_sent_at or initialized_at
        due_at = cron.latest_occurrence(now)
        if due_at is None:
            logging.info("📧 未找到有效的计划时间，跳过本次邮件推送")
            return None
        if due_at <= baseline:
            logging.info(
                f"📧 未到计划时间（最近计划 {due_at:%Y-%m-%d %H:%M}，"
                f"上次推送/基线 {baseline:%Y-%m-%d %H:%M}），跳过"
            )
            return None
        return due_at

    def _build_email_push_template_data(self, subject: str, due_at: datetime) -> dict:
        """Assemble the variables exposed to the email template."""
        return {
            "subject": subject,
            "generated_at": datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M"),
            "due_at": due_at.strftime("%Y-%m-%d %H:%M"),
            "total": len(self.latest_articles),
            "articles": self.latest_articles,
            "statistical_data": self.latest_statistics,
        }

    def _build_email_push_text_body(self, subject: str, due_at: datetime) -> str:
        """Build the plain-text fallback for the digest email."""
        lines = [
            subject,
            f"计划时间：{due_at:%Y-%m-%d %H:%M}",
            f"文章数量：{len(self.latest_articles)}",
            "",
        ]
        for article in self.latest_articles:
            lines.append(
                f"- {article.get('title') or '无标题'}"
                f"（{article.get('author') or '未知作者'} · {article.get('created') or '未知时间'}）"
            )
            if article.get("link"):
                lines.append(f"  {article['link']}")
        return "\n".join(lines)

    @staticmethod
    def _resolve_template_path(configured: str, default: str) -> Path:
        """Resolve a template path, also accepting a bare or stale filename."""
        candidate = Path(configured or default)
        if candidate.is_file():
            return candidate
        fallback = Path("./templates") / candidate.name
        if fallback.is_file():
            return fallback
        return candidate

    @staticmethod
    def _parse_state_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
        return parsed

    def run_rss_subscription_if_enabled(self, mail_runtime: MailRuntime) -> None:
        """Send subscription emails for newly discovered posts when enabled."""
        if not self.config.rss_subscribe.enable:
            return
        if not mail_runtime.is_ready:
            logging.info("⏭️ RSS 订阅推送未执行，因为 SMTP 尚未就绪")
            return

        logging.info("📰 RSS 订阅推送已启用")
        github_username, github_repo = self._resolve_github_repo()
        logging.info(f"👤 GitHub 用户名：{github_username}")
        logging.info(f"📁 GitHub 仓库：{github_repo}")

        latest_articles = get_latest_articles_from_link(
            url=self.config.rss_subscribe.your_blog_url,
            count=10,
            last_articles_path=self.config.runtime_paths.cache_file,
        )
        if not latest_articles:
            logging.info("📭 无新文章，无需推送")
            return

        logging.info(f"🆕 获取到的最新文章：{latest_articles}")
        email_list = self._load_subscriber_emails(github_username, github_repo)
        if not email_list:
            logging.info("⚠️ 无订阅邮箱，请检查格式或是否有订阅者")
            sys.exit(0)

        logging.info(f"📬 获取到邮箱列表：{email_list}")
        template_path = self._resolve_template_path(
            self.config.rss_subscribe.email_template,
            DEFAULT_RSS_SUBSCRIBE_TEMPLATE,
        )
        if not template_path.is_file():
            logging.warning(f"⚠️ 订阅邮件模板不存在，将仅发送纯文本：{template_path}")
        for article in latest_articles:
            template_data = self._build_email_template_data(article, github_username, github_repo)
            send_emails(
                emails=email_list["emails"],
                sender_email=mail_runtime.sender_email,
                smtp_server=mail_runtime.smtp_server,
                port=mail_runtime.port,
                password=mail_runtime.password,
                subject=f"{self.config.rss_subscribe.website_info.title} の最新文章：{article['title']}",
                body=self._build_plaintext_mail_body(article),
                template_path=str(template_path),
                template_data=template_data,
                use_tls=mail_runtime.use_tls,
            )

    def _merge_remote_results_if_enabled(
        self, result: dict, lost_friends: list[list[str]], link_payload: dict
    ) -> tuple[dict, list[list[str]], dict]:
        """Merge remote outputs when the merge option is enabled."""
        merge_settings = self.config.merge_settings
        if not merge_settings.enable:
            return result, lost_friends, link_payload

        remote_url = merge_settings.remote_base_url
        logging.info(f"[数据合并] 合并功能开启，从 {remote_url} 获取外部数据")

        if merge_settings.merge_article_data:
            result = merge_article_data(result, f"{remote_url}/all.json")
            lost_friends = merge_error_data(lost_friends, f"{remote_url}/errors.json")

        if merge_settings.merge_link_check_data:
            link_payload = merge_link_data(link_payload, f"{remote_url}/link.json")

        return result, lost_friends, link_payload

    def _resolve_github_repo(self) -> tuple[str, str]:
        """Resolve repository coordinates from env override or config."""
        fcl_repo = os.getenv("FCL_REPO")
        if fcl_repo:
            return tuple(fcl_repo.split("/", 1))
        return self.config.rss_subscribe.github_username, self.config.rss_subscribe.github_repo

    @staticmethod
    def _load_subscriber_emails(github_username: str, github_repo: str) -> dict | None:
        """Load subscriber emails from GitHub closed issues."""
        github_api_url = (
            f"https://api.github.com/repos/{github_username}/{github_repo}/issues"
            f"?state=closed&label=subscribed&per_page=200"
        )
        logging.info(f"[订阅邮箱] 正在从 GitHub 获取订阅邮箱：{github_api_url}")
        return extract_emails_from_issues(github_api_url)

    def _build_email_template_data(self, article: dict, github_username: str, github_repo: str) -> dict[str, str]:
        """Assemble template variables for one outbound notification email."""
        return {
            "title": article["title"],
            "summary": article["summary"],
            "published": article["published"],
            "link": article["link"],
            "website_title": self.config.rss_subscribe.website_info.title,
            "github_issue_url": (
                f"https://github.com/{github_username}/{github_repo}"
                "/issues?q=is%3Aissue+is%3Aclosed"
            ),
        }

    @staticmethod
    def _build_plaintext_mail_body(article: dict) -> str:
        """Build the plain-text fallback body for one notification email."""
        return (
            f"📄 文章标题：{article['title']}\n"
            f"🔗 链接：{article['link']}\n"
            f"📝 简介：{article['summary']}\n"
            f"🕒 发布时间：{article['published']}"
        )
