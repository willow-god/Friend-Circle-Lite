"""Configuration printer for startup diagnostics."""

import logging


def print_startup_config(config):
    """Print all configuration settings at startup for debugging."""
    logging.info("=" * 60)
    logging.info("🚀 Friend-Circle-Lite 启动配置")
    logging.info("=" * 60)

    # Spider settings
    logging.info("📡 爬虫配置:")
    logging.info(f"  - 启用状态: {'✅ 已启用' if config.spider_settings.enable else '❌ 已禁用'}")
    if config.spider_settings.enable:
        logging.info(f"  - 数据源: {config.spider_settings.json_url}")
        logging.info(f"  - 每站文章数: {config.spider_settings.article_count}")

    # Proxy settings
    logging.info("🔀 代理配置:")
    if config.proxy_settings.proxy_url:
        logging.info(f"  - 代理地址: {config.proxy_settings.proxy_url}")
        logging.info(f"  - 用途: 友链检测 + RSS 抓取")
    else:
        logging.info(f"  - 代理状态: ❌ 未配置")

    # Link check settings
    logging.info("🔍 友链检测配置:")
    logging.info(f"  - 启用状态: {'✅ 已启用' if config.link_check.enable else '❌ 已禁用'}")
    if config.link_check.enable:
        logging.info(f"  - 缓存时间: {config.link_check.max_age_hours} 小时")
        logging.info(f"  - 超时时间: {config.link_check.timeout} 秒")
        logging.info(f"  - 并发数: {config.link_check.max_workers}")
        logging.info(f"  - 反链检测: {'✅ 已启用' if config.link_check.enable_backlink_check else '❌ 已禁用'}")
        if config.link_check.enable_backlink_check:
            logging.info(f"  - 站点域名: {config.link_check.author_url}")

    # Merge settings
    logging.info("🔗 数据合并配置:")
    logging.info(f"  - 启用状态: {'✅ 已启用' if config.merge_settings.enable else '❌ 已禁用'}")
    if config.merge_settings.enable:
        logging.info(f"  - 远程数据源: {config.merge_settings.remote_base_url}")
        logging.info(f"  - 合并文章数据: {'✅ 是' if config.merge_settings.merge_article_data else '❌ 否'}")
        logging.info(f"  - 合并友链数据: {'✅ 是' if config.merge_settings.merge_link_check_data else '❌ 否'}")

    # Email push settings
    logging.info("📧 邮件推送配置:")
    logging.info(f"  - 启用状态: {'✅ 已启用' if config.email_push.enable else '❌ 已禁用'}")

    # RSS subscribe settings
    logging.info("📮 RSS 订阅配置:")
    logging.info(f"  - 启用状态: {'✅ 已启用' if config.rss_subscribe.enable else '❌ 已禁用'}")

    logging.info("=" * 60)
