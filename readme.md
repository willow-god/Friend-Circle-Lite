---

# Friend-Circle-Lite

友链朋友圈简单版，实现了[友链朋友圈](https://github.com/Rock-Candy-Tea/hexo-circle-of-friends)的基本功能，能够定时爬取rss文章并输出有序内容，为了匹配，输入格式与友链朋友圈的json格式一致，暂不支持从友链页面自动爬取。

## 功能介绍

- **友链朋友圈**: 爬取所有友链的文章，结果放置在根目录的all.json文件中。
- **邮件推送**: 作者可以通过邮箱订阅所有rss的更新（未来开发）。
- **RSS 订阅**: 基于 GitHub issue 的博客更新邮件订阅功能，游客可以通过简单的提交issue进行邮箱订阅站点更新，支持删除。

## 使用方法

1. **Fork 本仓库:**
   点击页面右上角的 Fork 按钮，将本仓库复制到你自己的 GitHub 账号下。

2. **配置 Secrets:**
   在你 Fork 的仓库中，依次进入 `Settings` -> `Secrets` -> `New repository secret`，添加以下 Secrets：
   - `PAT_TOKEN`: GitHub 的个人访问令牌，用于访问 GitHub API。
   - `SMTP_PWD`: SMTP 服务器的密码，用于发送电子邮件。

3. **启用 GitHub Actions:**
   GitHub Actions 已经配置好在仓库的 `.github/workflows/*.yml` 文件中，当代码推送或定时触发时将自动执行。
   其中，每个action功能如下：
   - `friend_circle_lite.yml`实现核心功能，爬取并发送邮箱；
   - `deal_subscribe_issue.yml`处理固定格式的issue，打上固定标签，评论，并关闭issue；

4. **设置issue格式：**
   这个我已经设置好了，你只需要检查issue部分是否有对应格式即可。

5. **定制配置:**
   如果需要修改爬虫设置或邮件模板等配置，可以修改仓库中的 `config.yaml` 文件：

   - **爬虫相关配置**
     使用 `requests` 库实现友链文章的爬取，并将结果存储到根目录下的 `all.json` 文件中。
     ```yaml
     spider_settings:
       enable: true
       json_url: "https://blog.qyliu.top/friend.json"
       article_count: 5
     ```

   - **邮箱推送功能配置**
     暂未实现，预留用于将每天的友链文章更新推送给指定邮箱。
     ```yaml
     email_push:
       enable: false
       to_email: recipient@example.com
       subject: "今天的 RSS 订阅更新"
       body_template: "rss_template.html"
     ```

   - **邮箱 issue 订阅功能配置**
     通过 GitHub issue 实现向提取的所有邮箱推送博客更新的功能。
     ```yaml
     rss_subscribe:
       enable: true
       github_username: willow-god
       github_repo: Friend-Circle-Lite
       your_blog_url: https://blog.qyliu.top/
     ```

   - **SMTP 配置**
     使用配置中的相关信息实现邮件发送功能。
     ```yaml
     smtp:
       email: 3162475700@qq.com
       server: smtp.qq.com
       port: 587
       use_tls: true
     ```

6. **贡献与定制:**
   欢迎对仓库进行贡献或根据需要进行定制。

## 问题与贡献

如果遇到任何问题或有建议，请[提交一个 issue](https://github.com/willow-god/Friend-Circle-Lite/issues)。欢迎贡献代码！

