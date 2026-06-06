"""启动时打印关键配置。

本文件只负责把当前生效配置输出到日志，方便在 GitHub Action 或本地运行时确认：
- 爬虫数据源与文章数量；
- 代理、友链可达性检测、数据合并参数；
- 邮件与 RSS 订阅开关；
- debug 诊断开关。
"""

from __future__ import annotations

import logging


def print_startup_config(config) -> None:
    """打印启动配置，避免把配置解析细节散落在主流程中。"""
    logging.info("=" * 60)
    logging.info("Friend-Circle-Lite 启动配置")
    logging.info("=" * 60)

    logging.info("爬虫配置:")
    logging.info(f"  - 启用状态: {'已启用' if config.spider_settings.enable else '已禁用'}")
    if config.spider_settings.enable:
        logging.info(f"  - 数据源: {config.spider_settings.json_url} ")
        logging.info(f"  - 每站文章数: {config.spider_settings.article_count}")

    logging.info("代理配置:")
    if config.proxy_settings.proxy_url:
        logging.info("  - 代理状态: 已配置（日志不显示具体地址）")
        logging.info("  - 建议: 使用仓库环境变量 PROXY_URL 覆盖，避免代理地址出现在配置文件中")
        logging.info("  - 用途: 友链检测 + RSS 抓取")
    else:
        logging.info("  - 代理状态: 未配置")

    logging.info("友链检测配置:")
    logging.info("  - 启用状态: 始终启用（友圈抓取依赖此检测结果）")
    logging.info(f"  - 缓存时间: {config.link_check.max_age_hours} 小时")
    logging.info(f"  - 超时时间: {config.link_check.timeout} 秒")
    logging.info(f"  - 并发数: {config.link_check.max_workers}")
    logging.info(f"  - 状态 API: {config.link_check.status_api_url} ")
    logging.info(f"  - 反链检测: {'已启用' if config.link_check.enable_backlink_check else '已禁用'}")
    if config.link_check.enable_backlink_check:
        logging.info(f"  - 站点域名: {config.link_check.author_url} ")

    logging.info("数据合并配置:")
    logging.info(f"  - 启用状态: {'已启用' if config.merge_settings.enable else '已禁用'}")
    if config.merge_settings.enable:
        logging.info(f"  - 远程数据源: {config.merge_settings.remote_base_url} ")
        logging.info(f"  - 合并文章数据: {'是' if config.merge_settings.merge_article_data else '否'}")
        logging.info(f"  - 合并友链数据: {'是' if config.merge_settings.merge_link_check_data else '否'}")

    logging.info("邮件推送配置:")
    logging.info(f"  - 启用状态: {'已启用' if config.email_push.enable else '已禁用'}")

    logging.info("RSS 订阅配置:")
    logging.info(f"  - 启用状态: {'已启用' if config.rss_subscribe.enable else '已禁用'}")

    logging.info("调试配置:")
    logging.info(f"  - SQLite 全量输出: {'已启用' if config.debug else '已禁用'}")

    logging.info("=" * 60)
