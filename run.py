import logging
import sys
import os

from friend_circle_lite.all_friends import fetch_and_process_data, marge_data_from_json_url, marge_errors_from_json_url, deal_with_large_data
from friend_circle_lite.utils.json import write_json
from friend_circle_lite.utils.config import load_config
from friend_circle_lite.utils.mail import send_emails
from friend_circle_lite.single_friend import get_latest_articles_from_link
from friend_circle_lite.utils.github import extract_emails_from_issues

FUTURE_ARTICLE_TOLERANCE_DAYS = 2

# ========== 日志设置 ==========
logging.basicConfig(
    level=logging.INFO,
    format='😋 %(levelname)s: %(message)s'
)

# ========== 加载环境变量 ==========
# if os.getenv("GITHUB_TOKEN") is None:
#     from dotenv import load_dotenv
#     load_dotenv()

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
        json_url        = json_url,             # 包含朋友信息的 JSON 文件的 URL。
        specific_RSS    = specific_rss,         # 包含特定 RSS 源的字典列表 [{name, url}]（来自 YAML）。
        count           = article_count,        # 获取每个博客的最大文章数。
        cache_file      = "./temp/cache.json"   # 缓存文件路径。
    )

    if config["spider_settings"]["merge_result"]["enable"]:

        merge_url = config['spider_settings']["merge_result"]['merge_json_url']
        logging.info(f"🔀 合并功能开启，从 {merge_url} 获取外部数据")
        result = marge_data_from_json_url(result, f"{merge_url}/all.json")
        lost_friends = marge_errors_from_json_url(lost_friends, f"{merge_url}/errors.json")

    article_count = len(result.get("article_data", []))
    logging.info(f"📦 数据获取完毕，共有 {article_count} 篇文章，正在处理数据")

    future_tolerance_days = FUTURE_ARTICLE_TOLERANCE_DAYS
    result = deal_with_large_data(result, future_tolerance_days=future_tolerance_days)

    write_json("./all.json", result)
    write_json("./errors.json", lost_friends)

# ========== 邮箱推送准备 ==========
SMTP_isReady = False

sender_email = ""
server = ""
port = 0
use_tls = False
password = ""

if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    logging.info("📨 推送功能已启用，正在准备中...")

    smtp_conf = config["smtp"]
    sender_email = smtp_conf["email"]
    server = smtp_conf["server"]
    port = smtp_conf["port"]
    use_tls = smtp_conf["use_tls"]
    password = os.getenv("SMTP_PWD")

    logging.info(f"📡 SMTP 服务器：{server}:{port}")
    if not password or not sender_email or not server or not port:
        logging.error("❌ 环境变量 SMTP_PWD 未设置，无法发送邮件")
    else:
        logging.info(f"🔐 密码(部分)：{password[:3]}*****")
        SMTP_isReady = True

# ========== 邮件推送（待实现）==========
if config["email_push"]["enable"] and SMTP_isReady:
    logging.info("📧 邮件推送已启用")
    logging.info("⚠️ 抱歉，目前尚未实现邮件推送功能")

# ========== RSS 订阅推送 ==========
if config["rss_subscribe"]["enable"] and SMTP_isReady:
    logging.info("📰 RSS 订阅推送已启用")

    # 获取 GitHub 仓库信息
    fcl_repo = os.getenv('FCL_REPO') # 仓库内置
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
        last_articles_path="./temp/newest_posts.json" # 存储上一次的文章
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

# ========== 友链状态检测 ==========
if config.get("check_links", {}).get("enable", False):
    from friend_circle_lite.check_links import check_and_save

    check_links_conf = config["check_links"]
    # 兼容原 check-flink-main 的环境变量配置
    source_url = os.getenv("SOURCE_URL") or check_links_conf.get("source_url")
    author_url = os.getenv("AUTHOR_URL") or check_links_conf.get("author_url", "")
    proxy_url = os.getenv("PROXY_URL") or check_links_conf.get("proxy_url", "")
    max_workers = check_links_conf.get("max_workers", 10)
    result_file = check_links_conf.get("result_file", "./result.json")
    specific_linkpage = check_links_conf.get("specific_linkpage", [])

    logging.info("🔍 友链状态检测已启用")
    check_and_save(
        source_url=source_url,
        author_url=author_url,
        proxy_url=proxy_url,
        max_workers=max_workers,
        result_file=result_file,
        specific_linkpage=specific_linkpage,
    )
