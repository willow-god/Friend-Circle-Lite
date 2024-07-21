from flask import Flask, jsonify
from flask_apscheduler import APScheduler
from threading import Lock
import logging
import os

from friend_circle_lite.get_info import fetch_and_process_data, sort_articles_by_time
from friend_circle_lite.get_conf import load_config

app = Flask(__name__)

# 配置APScheduler
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# 配置日志记录
log_file = "grab.log"
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 全局变量
articles_data = []
data_lock = Lock()

def fetch_articles():
    global articles_data
    logging.info("开始抓取文章...")
    config = load_config("./conf.yaml")
    if config["spider_settings"]["enable"]:
        json_url = config['spider_settings']['json_url']
        article_count = config['spider_settings']['article_count']
        logging.info(f"正在从 {json_url} 中获取，每个博客获取 {article_count} 篇文章")
        try:
            result = fetch_and_process_data(json_url=json_url, count=article_count)
            sorted_result = sort_articles_by_time(result)
            with data_lock:
                articles_data = sorted_result
            logging.info("文章抓取成功")
        except Exception as e:
            logging.error(f"抓取文章时出错: {e}")

# 每四个小时抓取一次文章
scheduler.add_job(id='Fetch_Articles_Job', func=fetch_articles, trigger='interval', hours=4)

@app.route('/all', methods=['GET'])
def get_all_articles():
    with data_lock:
        return jsonify(articles_data)

if __name__ == '__main__':
    # 清空日志文件
    if os.path.exists(log_file):
        with open(log_file, 'w'):
            pass

    fetch_articles()  # 启动时立即抓取一次
    app.run(port=1223)
