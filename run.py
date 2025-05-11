import logging
import json
import sys
import os

from friend_circle_lite.get_info import (
    fetch_and_process_data,
    marge_data_from_json_url,
    marge_errors_from_json_url,
    deal_with_large_data
)
from friend_circle_lite.get_conf import load_config
from rss_subscribe.push_article_update import (
    get_latest_articles_from_link,
    extract_emails_from_issues
)
from push_rss_update.send_email import send_emails

# ========== 日志设置 ==========
logging.basicConfig(
    level=logging.INFO,
    format='😋 %(levelname)s: %(message)s'
)

# ========== 加载配置 ==========
config = load_config("./conf.yaml")

# ========== 爬虫模块 ==========
if config["spider_settings"]["enable"]:
    logging.info("✅ 爬虫已启用")

    json_url = config['spider_settings']['json_url']
    article_count = config['spider_settings']['article_count']
    specific_rss = config['specific_RSS']

    logging.info(f"📥 正在从 {json_url} 获取数据，每个博客获取 {article_count} 篇文章")
    result, lost_friends = fetch_and_process_data(
        json_url=json_url,
        specific_RSS=specific_rss,
        count=article_count
    ) # type: ignore

    if config["spider_settings"]["merge_result"]["enable"]:
        merge_url = config['spider_settings']["merge_result"]['merge_json_url']
        logging.info(f"🔀 合并功能开启，从 {merge_url} 获取外部数据")

        result = marge_data_from_json_url(result, f"{merge_url}/all.json")
        lost_friends = marge_errors_from_json_url(lost_friends, f"{merge_url}/errors.json")

    article_count = len(result.get("article_data", []))
    logging.info(f"📦 数据获取完毕，共有 {article_count} 位好友的动态，正在处理数据")

    result = deal_with_large_data(result)

    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(lost_friends, f, ensure_ascii=False, indent=2)

# ========== 推送准备 ==========
if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    logging.info("📨 推送功能已启用，正在准备中...")

    smtp_conf = config["smtp"]
    sender_email = smtp_conf["email"]
    server = smtp_conf["server"]
    port = smtp_conf["port"]
    use_tls = smtp_conf["use_tls"]
    password = os.getenv("SMTP_PWD")

    logging.info(f"📡 SMTP 服务器：{server}:{port}")
    if not password:
        logging.error("❌ 环境变量 SMTP_PWD 未设置，无法发送邮件")
        sys.exit(1)
    else:
        logging.info(f"🔐 密码(部分)：{password[:3]}*****")

# ========== 邮件推送（待实现）==========
if config["email_push"]["enable"]:
    logging.info("📧 邮件推送已启用")
    logging.info("⚠️ 抱歉，目前尚未实现邮件推送功能")

# ========== RSS 订阅推送 ==========
if config["rss_subscribe"]["enable"]:
    logging.info("📰 RSS 订阅推送已启用")

    smtp_conf = config["smtp"]
    sender_email = smtp_conf["email"]
    server = smtp_conf["server"]
    port = smtp_conf["port"]
    use_tls = smtp_conf["use_tls"]
    password = os.getenv("SMTP_PWD")

    # 获取 GitHub 仓库信息
    fcl_repo = os.getenv('FCL_REPO')
    if fcl_repo:
        github_username, github_repo = fcl_repo.split('/')
    else:
        github_username = str(config["rss_subscribe"]["github_username"]).strip()
        github_repo = str(config["rss_subscribe"]["github_repo"]).strip()

    logging.info(f"👤 GitHub 用户名：{github_username}")
    logging.info(f"📁 GitHub 仓库：{github_repo}")

    your_blog_url = config["rss_subscribe"]["your_blog_url"]
    email_template = config["rss_subscribe"]["email_template"]
    website_title = config["rss_subscribe"]["website_info"]["title"]

    latest_articles = get_latest_articles_from_link(
        url=your_blog_url,
        count=5,
        last_articles_path="./rss_subscribe/last_articles.json"
    )

    if not latest_articles:
        logging.info("📭 无新文章，无需推送")
    else:
        logging.info(f"🆕 获取到的最新文章：{latest_articles}")

        github_api_url = (
            f"https://api.github.com/repos/{github_username}/{github_repo}/issues"
            f"?state=closed&label=subscribed&per_page=200"
        )
        logging.info(f"🔎 正在从 GitHub 获取订阅邮箱：{github_api_url}")
        email_list = extract_emails_from_issues(github_api_url)

        if not email_list:
            logging.info("⚠️ 无订阅邮箱，请检查格式或是否有订阅者")
            sys.exit(0)

        logging.info(f"📬 获取到邮箱列表：{email_list}")

        for article in latest_articles:
            template_data = {
                "title": article["title"],
                "summary": article["summary"],
                "published": article["published"],
                "link": article["link"],
                "website_title": website_title,
                "github_issue_url": (
                    f"https://github.com/{github_username}/{github_repo}"
                    "/issues?q=is%3Aissue+is%3Aclosed"
                ),
            }

            send_emails(
                emails=email_list["emails"],
                sender_email=sender_email,
                smtp_server=server,
                port=port,
                password=password,
                subject=f"{website_title} の最新文章：{article['title']}",
                body=(
                    f"📄 文章标题：{article['title']}\n"
                    f"🔗 链接：{article['link']}\n"
                    f"📝 简介：{article['summary']}\n"
                    f"🕒 发布时间：{article['published']}"
                ),
                template_path=email_template,
                template_data=template_data,
                use_tls=use_tls
            )
