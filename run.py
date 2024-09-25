# 引入 check_feed 和 parse_feed 函数
from friend_circle_lite.get_info import fetch_and_process_data, sort_articles_by_time, marge_data_from_json_url, marge_errors_from_json_url
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
    specific_RSS = config['specific_RSS']
    print("正在从 {json_url} 中获取，每个博客获取 {article_count} 篇文章".format(json_url=json_url, article_count=article_count))
    result, lost_friends = fetch_and_process_data(json_url=json_url, specific_RSS=specific_RSS, count=article_count)
    if config["spider_settings"]["merge_result"]["enable"]:
        marge_json_url = config['spider_settings']["merge_result"]['merge_json_url']
        print("合并数据功能开启，从 {marge_json_url} 中获取境外数据并合并".format(marge_json_url=marge_json_url + "/all.json"))
        result = marge_data_from_json_url(result, marge_json_url + "/all.json")
        lost_friends = marge_errors_from_json_url(lost_friends, marge_json_url + "/errors.json")
        
    sorted_result = sort_articles_by_time(result)
    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(sorted_result, f, ensure_ascii=False, indent=2)
    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(lost_friends, f, ensure_ascii=False, indent=2)

if config["email_push"]["enable"] or config["rss_subscribe"]["enable"]:
    print("获取smtp配置信息")
    email_settings = config["smtp"]
    email = email_settings["email"]
    server = email_settings["server"]
    port = email_settings["port"]
    use_tls = email_settings["use_tls"]
    password = os.getenv("SMTP_PWD")
    print("密码检测是否存在：", password[:2], "****", password[-2:])

if config["email_push"]["enable"]:
    print("邮件推送已启用")
    
if config["rss_subscribe"]["enable"]:
    print("RSS通过issue订阅已启用")
    # 获取并强制转换为字符串
    github_username = str(config["rss_subscribe"]["github_username"]).strip()
    github_repo = str(config["rss_subscribe"]["github_repo"]).strip()
    your_blog_url = config["rss_subscribe"]["your_blog_url"]
    email_template = config["rss_subscribe"]["email_template"]
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
        github_api_url = "https://api.github.com/repos/" + github_username + "/" + github_repo + "/issues" + "?state=closed&label=subscribed&per_page=200"
        print("正在从 {github_api_url} 中获取订阅信息".format(github_api_url=github_api_url))
        email_list = extract_emails_from_issues(github_api_url)
        if email_list == None:
            print("无邮箱列表")
            sys.exit(0)
        else:
            print("获取到的邮箱列表为：", email_list)
        # 循环latest_articles，发送邮件
        for article in latest_articles:
            template_data = {
                "title": article["title"],
                "summary": article["summary"],
                "published": article["published"],
                "link": article["link"]
            }
            
            send_emails(
                emails=email_list["emails"],
                sender_email=email,
                smtp_server=server,
                port=port,
                password=password,
                subject="清羽飞扬の最新文章：" + article["title"],
                body="文章链接：" + article["link"] + "\n" + "文章内容：" + article["summary"] + "\n" + "发布时间：" + article["published"],
                template_path=email_template,
                template_data=template_data,
                use_tls=use_tls
            )
