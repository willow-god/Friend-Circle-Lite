"""Render the two email templates with sample data for local preview.

Usage:
    python scripts/render_email_preview.py
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "docs" / "email-preview"

ARTICLES = [
    {
        "title": "在秋日的午后，整理我的数字花园",
        "author": "清羽飞扬",
        "created": "2026-11-04 07:00",
        "link": "https://blog.example.com/digital-garden",
    },
    {
        "title": "关于「慢下来」这件事",
        "author": "无名小栈",
        "created": "2026-11-03 21:40",
        "link": "https://slow.example.com/slow-down",
    },
    {
        "title": "用 Python 写一个轻量的 RSS 聚合器",
        "author": "代码与咖啡",
        "created": "2026-11-03 16:10",
        "link": "https://code.example.com/rss-reader",
    },
    {
        "title": "城市散步：从旧书店到江边",
        "author": "山间来信",
        "created": "2026-11-03 09:25",
        "link": "https://mountain.example.com/walk",
    },
    {
        "title": "十一月读书清单",
        "author": "纸上花园",
        "created": "2026-11-02 22:05",
        "link": "https://paper.example.com/reading-list",
    },
    {
        "title": "一次失败的露营",
        "author": "野生观察",
        "created": "2026-11-02 18:30",
        "link": "https://wild.example.com/camping",
    },
    {
        "title": "给博客换一套字体",
        "author": "设计手记",
        "created": "2026-11-02 11:15",
        "link": "https://design.example.com/typeface",
    },
    {
        "title": "深夜电台：雨声与爵士",
        "author": "夜航船",
        "created": "2026-11-01 23:50",
        "link": "https://night.example.com/radio",
    },
]

DIGEST_DATA = {
    "subject": "今天的 RSS 订阅更新",
    "generated_at": "2026-11-04 08:22",
    "due_at": "2026-11-04 08:00",
    "total": len(ARTICLES),
    "shown": len(ARTICLES),
    "omitted": 0,
    "articles": ARTICLES,
    "statistical_data": {
        "friends_num": 18,
        "active_num": 14,
        "error_num": 4,
    },
}

ARTICLE_DATA = {
    "website_title": "清羽飞扬",
    "title": "在秋日的午后，整理我的数字花园",
    "summary": (
        "把散落在各处的笔记、书签与未完成的草稿重新收拢，像整理一座久未打理的院子。"
        "这篇记录了我最近使用的目录结构、标签习惯，以及一些关于「留下什么」的思考。"
    ),
    "published": "2026-11-04 07:00",
    "link": "https://blog.example.com/digital-garden",
    "github_issue_url": "https://github.com/willow-god/Friend-Circle-Lite/issues?q=is%3Aissue+is%3Aclosed",
}

GALLERY_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>邮件模板预览 · Friend-Circle-Lite</title>
    <style>
        :root {
            --paper: #f4f1ea;
            --card: #fffdfa;
            --ink: #3f3a33;
            --muted: #8a7d6e;
            --sage: #5d704b;
            --line: #e2d8c8;
            --tan: #c89b6d;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 48px 24px 72px;
            background: var(--paper);
            color: var(--ink);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
        }
        .page { width: min(1320px, 100%); margin: 0 auto; }
        .eyebrow {
            margin: 0 0 12px;
            color: var(--sage);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: .2em;
            text-transform: uppercase;
        }
        h1 {
            margin: 0;
            font-family: Georgia, "Times New Roman", "Songti SC", SimSun, serif;
            font-size: clamp(2.4rem, 6vw, 4rem);
            font-weight: 400;
            letter-spacing: -.03em;
        }
        .intro { max-width: 680px; margin: 18px 0 0; color: var(--muted); font-size: 15px; line-height: 1.9; }
        .rule { width: 54px; height: 3px; margin-top: 28px; background: var(--tan); border-radius: 999px; transform: rotate(-2deg); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 32px; margin-top: 48px; align-items: start; }
        .panel { background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 22px; box-shadow: 8px 8px 0 rgba(139,157,119,.12); }
        .panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
        .panel h2 { margin: 0; font-family: Georgia, "Songti SC", SimSun, serif; font-size: 22px; font-weight: 400; }
        .panel a { color: var(--sage); font-size: 12px; text-decoration: none; border-bottom: 1px dashed currentColor; padding-bottom: 2px; }
        iframe { width: 100%; height: 880px; border: 1px solid var(--line); border-radius: 12px; background: #fff; }
        .note { margin-top: 14px; color: var(--muted); font-size: 12px; line-height: 1.8; }
        footer { margin-top: 56px; color: var(--muted); font-size: 12px; }
        @media (max-width: 760px) {
            body { padding: 32px 14px 56px; }
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <main class="page">
        <p class="eyebrow">Email templates preview</p>
        <h1>邮件模板预览</h1>
        <p class="intro">
            两套邮件模板都使用表格布局、内联样式和系统字体，避免外部图片与脚本，适配常见邮箱客户端。
            下面展示的是用示例数据渲染后的实际效果。
        </p>
        <div class="rule" aria-hidden="true"></div>

        <div class="grid">
            <section class="panel">
                <div class="panel-head">
                    <h2>友圈摘要</h2>
                    <a href="./rss_template.html" target="_blank">单独打开 ↗</a>
                </div>
                <iframe src="./rss_template.html" title="友圈摘要邮件预览"></iframe>
                <p class="note">email_push 使用：文章列表、统计数据、计划时间与生成时间。</p>
            </section>

            <section class="panel">
                <div class="panel-head">
                    <h2>单篇通知</h2>
                    <a href="./article_notify.html" target="_blank">单独打开 ↗</a>
                </div>
                <iframe src="./article_notify.html" title="单篇通知邮件预览"></iframe>
                <p class="note">rss_subscribe 使用：标题、摘要、发布时间、阅读按钮与退订入口。</p>
            </section>
        </div>

        <footer>Generated by <code>scripts/render_email_preview.py</code> · Friend-Circle-Lite</footer>
    </main>
</body>
</html>
"""


def main() -> None:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUTPUT_DIR / "rss_template.html").write_text(
        env.get_template("rss_template.html").render(DIGEST_DATA),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "article_notify.html").write_text(
        env.get_template("article_notify.html").render(ARTICLE_DATA),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "index.html").write_text(GALLERY_TEMPLATE, encoding="utf-8")

    print(f"预览已生成：{OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
