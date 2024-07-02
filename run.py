# 引入 check_feed 和 parse_feed 函数
from friend_circle_lite.get_info import fetch_and_process_data, sort_articles_by_time
from friend_circle_lite.get_conf import load_config
import json

# 爬虫部分内容
config = load_config("./conf.yml")
if config["spider_settings"]["enable"]:
    print("爬虫已启用")
    json_url = config['spider_settings']['json_url']
    article_count = config['spider_settings']['article_count']
    print("正在从 {json_url} 中获取，每个博客获取 {article_count} 篇文章".format(json_url=json_url, article_count=article_count))
    result = fetch_and_process_data(json_url=json_url, count=article_count)
    sorted_result = sort_articles_by_time(result)
    with open("all.json", "w", encoding="utf-8") as f:
        json.dump(sorted_result, f, ensure_ascii=False, indent=2)