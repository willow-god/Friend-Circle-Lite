"""Top-level application orchestration.

This module keeps the main script very small by moving the end-to-end workflow
into focused orchestration methods.
"""

from __future__ import annotations

import logging
import os
import sys

from friend_circle_lite.config.models import ApplicationConfig, MailRuntime
from friend_circle_lite.config.printer import print_startup_config
from friend_circle_lite.crawler.single_site_legacy import get_latest_articles_from_link
from friend_circle_lite.notifications.github import extract_emails_from_issues
from friend_circle_lite.notifications.mail import send_emails
from friend_circle_lite.outputs.legacy_api import (
    deal_with_large_data,
    fetch_and_process_data,
    merge_data_from_json_url,
    merge_errors_from_json_url,
    merge_link_data_from_json_url,
)
from friend_circle_lite.utils.json import write_json


class FriendCircleLiteApplication:
    """Application service coordinating crawl and notification workflows."""

    def __init__(self, config: ApplicationConfig):
        self.config = config

    def run(self) -> None:
        """Execute the enabled application features in a stable order."""
        print_startup_config(self.config)
        self.run_crawler_if_enabled()
        mail_runtime = self.prepare_mail_runtime()
        self.run_email_push_if_enabled(mail_runtime)
        self.run_rss_subscription_if_enabled(mail_runtime)

    def run_crawler_if_enabled(self) -> None:
        """Run the article crawl and persist public output files when enabled."""
        spider_settings = self.config.spider_settings
        if not spider_settings.enable:
            logging.info("⏭️ 爬虫未启用，跳过抓取流程")
            return

        logging.info("✅ 爬虫已启用")
        logging.info(
            f"📥 正在从 {spider_settings.json_url} 获取数据，每个博客获取 {spider_settings.article_count} 篇文章"
        )

        crawl_result = fetch_and_process_data(
            json_url=spider_settings.json_url,
            specific_RSS=self.config.specific_rss,
            count=spider_settings.article_count,
            cache_file=self.config.runtime_paths.cache_file,
            link_check_config=self.config.link_check,
            proxy_settings=self.config.proxy_settings,
        )
        if crawl_result is None:
            logging.error("❌ 抓取流程失败，未生成任何输出文件")
            return

        result, lost_friends, link_payload = crawl_result
        result, lost_friends, link_payload = self._merge_remote_results_if_enabled(result, lost_friends, link_payload)

        article_count = len(result.get("article_data", []))
        logging.info(f"📦 数据获取完毕，共有 {article_count} 篇文章，正在处理数据")

        result = deal_with_large_data(
            result,
            future_tolerance_days=self.config.future_article_tolerance_days,
        )
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
        """Keep the reserved email push entrypoint behavior unchanged."""
        if self.config.email_push.enable and mail_runtime.is_ready:
            logging.info("📧 邮件推送已启用")
            logging.info("⚠️ 抱歉，目前尚未实现邮件推送功能")

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
                template_path=self.config.rss_subscribe.email_template,
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
        logging.info(f"🔀 合并功能开启，从 {remote_url} 获取外部数据")

        if merge_settings.merge_article_data:
            result = merge_data_from_json_url(result, f"{remote_url}/all.json")
            lost_friends = merge_errors_from_json_url(lost_friends, f"{remote_url}/errors.json")

        if merge_settings.merge_link_check_data:
            link_payload = merge_link_data_from_json_url(link_payload, f"{remote_url}/link.json")

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
        logging.info(f"🔎 正在从 GitHub 获取订阅邮箱：{github_api_url}")
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
