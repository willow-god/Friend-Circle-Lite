from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
import schedule
import time
import logging
import os
import json
import random
from threading import Lock, Thread

from friend_circle_lite.get_info import fetch_and_process_data, sort_articles_by_time
from friend_circle_lite.get_conf import load_config

app = FastAPI()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置日志记录
log_file = "grab.log"
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

data_lock = Lock()

def fetch_articles():
    logging.info("开始抓取文章...")
    try:
        config = load_config("./conf.yaml")
        if config["spider_settings"]["enable"]:
            json_url = config['spider_settings']['json_url']
            article_count = config['spider_settings']['article_count']
            logging.info(f"正在从 {json_url} 中获取，每个博客获取 {article_count} 篇文章")
            result, errors = fetch_and_process_data(json_url=json_url, count=article_count)
            sorted_result = sort_articles_by_time(result)
            with open("all.json", "w", encoding="utf-8") as f:
                json.dump(sorted_result, f, ensure_ascii=False, indent=2)
            with open("errors.json", "w", encoding="utf-8") as f:
                json.dump(errors, f, ensure_ascii=False, indent=2)
            logging.info("文章抓取成功")
        else:
            logging.warning("抓取设置在配置中被禁用。")
    except Exception as e:
        logging.error(f"抓取文章时出错: {e}")

@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open('./static/deploy-home.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>File not found</h1>", status_code=404)

@app.get('/all')
async def get_all_articles():
    try:
        with open('all.json', 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        return JSONResponse(content=articles_data)
    except FileNotFoundError:
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse(content={"error": "Failed to decode JSON"}, status_code=500)

@app.get('/errors')
async def get_error_friends():
    try:
        with open('errors.json', 'r', encoding='utf-8') as f:
            errors_data = json.load(f)
        return JSONResponse(content=errors_data)
    except FileNotFoundError:
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse(content={"error": "Failed to decode JSON"}, status_code=500)

@app.get('/random')
async def get_random_article():
    try:
        with open('all.json', 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        if articles_data.get("article_data"):
            random_article = random.choice(articles_data["article_data"])
            return JSONResponse(content=random_article)
        else:
            return JSONResponse(content={"error": "No articles available"}, status_code=404)
    except FileNotFoundError:
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse(content={"error": "Failed to decode JSON"}, status_code=500)

def schedule_tasks():
    schedule.every(4).hours.do(fetch_articles)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # 清空日志文件
    if os.path.exists(log_file):
        with open(log_file, 'w'):
            pass

    fetch_articles()  # 启动时立即抓取一次

    # 启动调度任务线程
    task_thread = Thread(target=schedule_tasks)
    task_thread.start()

    # 启动FastAPI应用
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=1223)
