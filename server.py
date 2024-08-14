from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
import json
import random

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
        with open('./all.json', 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        return JSONResponse(content=articles_data)
    except FileNotFoundError:
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse(content={"error": "Failed to decode JSON"}, status_code=500)

@app.get('/errors')
async def get_error_friends():
    try:
        with open('./errors.json', 'r', encoding='utf-8') as f:
            errors_data = json.load(f)
        return JSONResponse(content=errors_data)
    except FileNotFoundError:
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse(content={"error": "Failed to decode JSON"}, status_code=500)

@app.get('/random')
async def get_random_article():
    try:
        with open('./all.json', 'r', encoding='utf-8') as f:
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

if __name__ == '__main__':
    # 启动FastAPI应用
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=1223)
