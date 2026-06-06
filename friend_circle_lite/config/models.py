"""Application configuration models.

This module converts the raw YAML structure into typed configuration objects so
that the rest of the application can depend on explicit fields instead of a
loosely typed nested dictionary.

The external YAML keys are preserved for backward compatibility. Internally,
snake_case names are used consistently.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_CACHE_FILE = "./temp/cache.sqlite3"
DEFAULT_ALL_JSON = "./all.json"
DEFAULT_ERRORS_JSON = "./errors.json"
DEFAULT_LINK_JSON = "./link.json"


@dataclass(slots=True)
class MergeSettings:
    """Options for merging local crawl results with remote data sources."""

    enable: bool = False
    remote_base_url: str = ""
    merge_article_data: bool = True
    merge_link_check_data: bool = True


@dataclass(slots=True)
class ProxySettings:
    """Proxy configuration for both link checking and RSS crawling."""

    proxy_url: str = ""


@dataclass(slots=True)
class SpiderSettings:
    """Crawler settings controlling source list and output density."""

    enable: bool = True
    json_url: str = ""
    article_count: int = 5


@dataclass(slots=True)
class LinkCheckConfig:
    """Settings for friend link reachability checks."""

    enable: bool = True
    max_age_hours: int = 24
    timeout: int = 15
    max_workers: int = 10
    status_api_url: str = "https://v2.xxapi.cn/api/status?url={url}"
    enable_backlink_check: bool = False
    author_url: str = ""


@dataclass(slots=True)
class EmailPushConfig:
    """Reserved configuration for the not-yet-implemented email push feature."""

    enable: bool = False
    to_email: str = ""
    subject: str = ""
    body_template: str = ""


@dataclass(slots=True)
class WebsiteInfo:
    """Display metadata for outbound notifications."""

    title: str = ""


@dataclass(slots=True)
class RssSubscribeConfig:
    """Configuration for GitHub issue based email subscriptions."""

    enable: bool = False
    github_username: str = ""
    github_repo: str = ""
    your_blog_url: str = ""
    email_template: str = ""
    website_info: WebsiteInfo = field(default_factory=WebsiteInfo)


@dataclass(slots=True)
class SmtpConfig:
    """SMTP connection settings used by all mail sending features."""

    email: str = ""
    server: str = ""
    port: int = 0
    use_tls: bool = True


@dataclass(slots=True)
class RuntimePaths:
    """Filesystem locations used by the runtime."""

    cache_file: str = DEFAULT_CACHE_FILE
    all_json_file: str = DEFAULT_ALL_JSON
    errors_json_file: str = DEFAULT_ERRORS_JSON
    link_json_file: str = DEFAULT_LINK_JSON


@dataclass(slots=True)
class ApplicationConfig:
    """Root application configuration assembled from the YAML file."""

    spider_settings: SpiderSettings
    proxy_settings: ProxySettings
    merge_settings: MergeSettings
    link_check: LinkCheckConfig
    email_push: EmailPushConfig
    rss_subscribe: RssSubscribeConfig
    smtp: SmtpConfig
    specific_rss: list[dict]
    runtime_paths: RuntimePaths = field(default_factory=RuntimePaths)
    future_article_tolerance_days: int = 2

    @classmethod
    def from_dict(cls, data: dict) -> "ApplicationConfig":
        """Create a typed config object from the raw YAML dictionary."""
        spider_raw = data.get("spider_settings", {})
        proxy_raw = data.get("proxy_settings", {})
        merge_raw = data.get("merge_settings", {})
        link_check_raw = data.get("link_check", {})
        email_push_raw = data.get("email_push", {})
        rss_subscribe_raw = data.get("rss_subscribe", {})
        website_info_raw = rss_subscribe_raw.get("website_info", {})
        smtp_raw = data.get("smtp", {})
        runtime_raw = data.get("runtime_paths", {})

        return cls(
            spider_settings=SpiderSettings(
                enable=bool(spider_raw.get("enable", True)),
                json_url=str(spider_raw.get("json_url", "")).strip(),
                article_count=int(spider_raw.get("article_count", 5)),
            ),
            proxy_settings=ProxySettings(
                proxy_url=os.getenv("PROXY_URL") or str(proxy_raw.get("proxy_url", "")).strip(),
            ),
            merge_settings=MergeSettings(
                enable=bool(merge_raw.get("enable", False)),
                remote_base_url=str(merge_raw.get("remote_base_url", "")).strip(),
                merge_article_data=bool(merge_raw.get("merge_article_data", True)),
                merge_link_check_data=bool(merge_raw.get("merge_link_check_data", True)),
            ),
            link_check=LinkCheckConfig(
                enable=bool(link_check_raw.get("enable", True)),
                max_age_hours=int(link_check_raw.get("max_age_hours", 24)),
                timeout=int(link_check_raw.get("timeout", 15)),
                max_workers=int(link_check_raw.get("max_workers", 10)),
                status_api_url=str(link_check_raw.get("status_api_url", "https://v2.xxapi.cn/api/status?url={url}")).strip(),
                enable_backlink_check=bool(link_check_raw.get("enable_backlink_check", False)),
                author_url=str(link_check_raw.get("author_url", "")).strip(),
            ),
            email_push=EmailPushConfig(
                enable=bool(email_push_raw.get("enable", False)),
                to_email=str(email_push_raw.get("to_email", "")).strip(),
                subject=str(email_push_raw.get("subject", "")).strip(),
                body_template=str(email_push_raw.get("body_template", "")).strip(),
            ),
            rss_subscribe=RssSubscribeConfig(
                enable=bool(rss_subscribe_raw.get("enable", False)),
                github_username=str(rss_subscribe_raw.get("github_username", "")).strip(),
                github_repo=str(rss_subscribe_raw.get("github_repo", "")).strip(),
                your_blog_url=str(rss_subscribe_raw.get("your_blog_url", "")).strip(),
                email_template=str(rss_subscribe_raw.get("email_template", "")).strip(),
                website_info=WebsiteInfo(
                    title=str(website_info_raw.get("title", "")).strip(),
                ),
            ),
            smtp=SmtpConfig(
                email=str(smtp_raw.get("email", "")).strip(),
                server=str(smtp_raw.get("server", "")).strip(),
                port=int(smtp_raw.get("port", 0) or 0),
                use_tls=bool(smtp_raw.get("use_tls", True)),
            ),
            specific_rss=list(data.get("specific_RSS", []) or []),
            runtime_paths=RuntimePaths(
                cache_file=str(runtime_raw.get("cache_file", DEFAULT_CACHE_FILE)).strip() or DEFAULT_CACHE_FILE,
                all_json_file=str(runtime_raw.get("all_json_file", DEFAULT_ALL_JSON)).strip() or DEFAULT_ALL_JSON,
                errors_json_file=str(runtime_raw.get("errors_json_file", DEFAULT_ERRORS_JSON)).strip() or DEFAULT_ERRORS_JSON,
                link_json_file=str(runtime_raw.get("link_json_file", DEFAULT_LINK_JSON)).strip() or DEFAULT_LINK_JSON,
            ),
        )


@dataclass(slots=True)
class MailRuntime:
    """Runtime SMTP credentials resolved from configuration and environment."""

    sender_email: str
    smtp_server: str
    port: int
    password: str
    use_tls: bool

    @property
    def is_ready(self) -> bool:
        """Whether enough information is available to send email."""
        return bool(self.sender_email and self.smtp_server and self.port and self.password)
