from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
import json
import random

app = FastAPI()

# 设置静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/main", StaticFiles(directory="main"), name="main")

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 返回图标图片
@app.get("/favicon.ico", response_class=HTMLResponse)
async def favicon():
    return FileResponse('static/favicon.ico')

# 返回背景图片
@app.get("/bg-light.webp", response_class=HTMLResponse)
async def bg_light():
    return FileResponse('static/bg-light.webp')
    
# 返回背景图片
@app.get("/bg-dark.webp", response_class=HTMLResponse)
async def bg_dark():
    return FileResponse('static/bg-dark.webp')

# 返回资源文件
# 返回 CSS 文件
@app.get("/fclite.css", response_class=HTMLResponse)
async def get_fclite_css():
    return FileResponse('./main/fclite.css')

# 返回 JS 文件
@app.get("/fclite.js", response_class=HTMLResponse)
async def get_fclite_js():
    return FileResponse('./main/fclite.js')

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse('./static/index.html')

@app.get('/all.json')
async def get_all_articles():
    try:
        with open('./all.json', 'r', encoding='utf-8') as f:
            articles_data = json.load(f)
        return JSONResponse(content=articles_data)
    except FileNotFoundError:
        return JSONResponse(content={"error": "File not found"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse(content={"error": "Failed to decode JSON"}, status_code=500)

@app.get('/errors.json')
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
