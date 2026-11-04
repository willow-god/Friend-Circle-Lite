# 邮件模板预览（仅展示）

本目录由 `scripts/render_email_preview.py` 生成，**仅用于预览两套邮件模板的渲染效果**。

- 这里的 HTML 不参与实际邮件发送；
- 不会被 GitHub Actions 发布到 `page` 分支；
- 文件中的站点名、作者、文章链接和 GitHub issue 地址都是演示数据，请勿直接用于生产环境。

## 实际使用的模板

- 友圈摘要：`templates/rss_template.html`
- 单篇通知：`templates/article_notify.html`

模板通过 `conf.yaml` 配置：

```yaml
email_push:
  body_template: "./templates/rss_template.html"

rss_subscribe:
  email_template: "./templates/article_notify.html"
```

修改模板后，可以重新生成预览：

```bash
python scripts/render_email_preview.py
```

然后打开 `docs/email-preview/index.html` 查看效果。

## 自定义预览数据

预览中的示例站点名、作者和 issue 地址位于 `scripts/render_email_preview.py` 顶部的 `ARTICLES` / `ARTICLE_DATA` 中，按需修改即可。

实际发送邮件时，订阅通知里的 GitHub issue 地址不是预览里写死的值，而是由 `GITHUB_REPOSITORY` / `FCL_REPO` 解析当前仓库后动态拼接的。
