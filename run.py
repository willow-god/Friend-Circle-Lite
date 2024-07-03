# 引入 check_feed 和 parse_feed 函数
from friend_circle_lite.get_info import fetch_and_process_data, sort_articles_by_time
from friend_circle_lite.get_conf import load_config
from rss_subscribe.push_article_update import get_latest_articles_from_link, extract_emails_from_issues
from push_rss_update.send_email import send_emails

import json
import sys
import os

# 爬虫部分内容
config = load_config("./conf.yaml")
if config["spider_settings"]["enable"]:
    print("爬虫已启用")
    json_url = config['spider_settings']['json_url']
    article_count = config['spider_settings']['article_count']
    print("正在从 {json_url} 中获取，每个博客获取 {article_count} 篇文章".format(json_url=json_url, article_count=article_count))
    result = fetch_and_process_data(json_url=json_url, count=article_count)
    sorted_result = sort_articles_by_time(result)
    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(sorted_result, f, ensure_ascii=False, indent=2)

if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    print("获取smtp配置信息")
    email_settings = config["smtp"]
    email = email_settings["email"]
    server = email_settings["server"]
    port = email_settings["port"]
    use_tls = email_settings["use_tls"]
    password = os.getenv("SMTP_PWD")

if config["email_push"]["enable"]:
    print("邮件推送已启用")
    
if config["rss_subscribe"]["enable"]:
    print("RSS通过issue订阅已启用")
    github_username = config["rss_subscribe"]["github_username"]
    github_repo = config["rss_subscribe"]["github_repo"]
    your_blog_url = config["rss_subscribe"]["your_blog_url"]
    github_api_url = "https://api.github.com/repos/" + github_username + "/" + github_repo + "/issues" + "?state=closed"
    print("正在从 {github_api_url} 中获取订阅信息".format(github_api_url=github_api_url))
    email_list = extract_emails_from_issues(github_api_url)
    if email_list == None:
        print("无邮箱列表")
        sys.exit()
    print("获取到的邮箱列表为：", email_list)
    # 获取最近更新的文章
    latest_articles = get_latest_articles_from_link(
        url=your_blog_url,
        count=5,
        last_articles_path="./rss_subscribe/last_articles.json"
        )
    print("最新文章为：", latest_articles)
    if latest_articles == None:
        print("没有新文章")
    else:
        send_emails(
            emails=email_list["email"],
            sender_email=email,
            smtp_server=server,
            port=port,
            password=password,
            subject="最新文章推送",
            body="最新文章为：\n" + "\n".join([article["title"] + " " + article["link"] for article in latest_articles]),
            use_tls=use_tls
        )
    
    
