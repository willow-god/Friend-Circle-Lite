---

# Friend-Circle-Lite

[前端展示](https://fc.liushen.fun) | [详细文档](https://blog.qyliu.top/posts/4dc716ec/)

友链朋友圈简单版，实现了[友链朋友圈](https://github.com/Rock-Candy-Tea/hexo-circle-of-friends)的基本功能，能够定时爬取rss文章并输出有序内容，为了较好的兼容性，输入格式与友链朋友圈的json格式一致，为了轻量化，暂不支持从友链页面自动爬取，下面会附带`hexo-theme-butterfly`主题的解决方案，其他主题可以类比。

## 开发进度

### 2024-07-25

* 自部署正在开发中，仅供测试
* 添加`/errors.json`，用于获取丢失友链数据，提高自定义程度
* 添加`/index.xml`接口的爬取，提高兼容性

## 展示页面

* [清羽飞扬の友链朋友圈](https://blog.qyliu.top/fcircle-lite/)

* [❖星港◎Star☆ 的友链朋友圈](https://blog.starsharbor.com/fcircle/)
* 欢迎更多

## 项目介绍

- **爬取文章**: 爬取所有友链的文章，结果放置在根目录的all.json文件中，方便读取并部署到前端。
- **邮箱推送更新(对作者推送所有友链更新)**: 作者可以通过邮箱订阅所有rss的更新（未来开发）。
- **issue邮箱订阅(对访客实时推送最新文章邮件)**: 基于`GitHub issue`的博客更新邮件订阅功能，游客可以通过简单的提交`issue`进行邮箱订阅站点更新，删除对应`issue`即可取消订阅。

## 特点介绍

* **轻量化**：对比原版友链朋友圈的功能，该友圈功能简洁，去掉了设置和fastAPI的臃肿，仅保留关键内容。
* **无数据库**：因为内容较少，我采用`json`直接存储文章信息，减少数据库操作，提升`action`运行效率。
* **部署简单**：原版友链朋友圈由于功能多，导致部署较为麻烦，本方案仅需简单的部署action即可使用，vercel仅用于部署前端静态页面和实时获取最新内容。
* **文件占用**：对比原版`4MB`的`bundle.js`文件大小，本项目仅需要`5.50KB`的`fclite.min.js`文件即可轻量的展示到前端。

## 功能概览

* 文章爬取
* 暗色适配
* 显示作者所有文章
* 获取丢失友链数据
* 随机钓鱼
* 邮箱推送
* 美观邮箱模板

## 使用方法

### 前置工作

1. **Fork 本仓库:**
   点击页面右上角的 Fork 按钮，将本仓库复制到你自己的`GitHub`账号下。

2. **配置 Secrets:**
   在你 Fork 的仓库中，依次进入 `Settings` -> `Secrets` -> `New repository secret`，添加以下 Secrets：
   - `PAT_TOKEN`: GitHub 的个人访问令牌，用于访问 GitHub API。
   - `SMTP_PWD`: SMTP 服务器的密码，用于发送电子邮件。

   ![](./static/1.png)
   
2. **配置action权限：**
   
   在设置中，点击`action`，拉到最下面，勾选`Read and write permissions`选项并保存，确保action有读写权限。
   
3. **启用 GitHub Actions:**
   GitHub Actions 已经配置好在仓库的 `.github/workflows/*.yml` 文件中，当到一定时间时将自动执行，也可以手动运行。
   其中，每个action功能如下：
   
   - `friend_circle_lite.yml`实现核心功能，爬取并发送邮箱；
   - `deal_subscribe_issue.yml`处理固定格式的issue，打上固定标签，评论，并关闭issue；
   
4. **设置issue格式：**
   这个我已经设置好了，你只需要检查issue部分是否有对应格式即可，可以自行修改对应参数以进行自定义。

### 配置选项

1. 如果需要修改爬虫设置或邮件模板等配置，需要修改仓库中的 `config.yaml` 文件：

   - **爬虫相关配置**
     使用 `requests` 库实现友链文章的爬取，并将结果存储到根目录下的 `all.json` 文件中。
     
     ```yaml
     spider_settings:
       enable: true
       json_url: "https://blog.qyliu.top/friend.json"
       article_count: 5
     ```
     
     `enable`：开启或关闭，默认开启；
     
     `json_url`：友链朋友圈通用爬取格式第一种（下方有配置方法）;
     
     `article_count`：每个作者留存文章个数。
     
   - **邮箱推送功能配置**
     暂未实现，预留用于将每天的友链文章更新推送给指定邮箱。
     
     ```yaml
     email_push:
       enable: false
       to_email: recipient@example.com
       subject: "今天的 RSS 订阅更新"
       body_template: "rss_template.html"
     ```
     
     **暂未实现**：该部分暂未实现，由于感觉用处不大，保留接口后期酌情更新。
     
   - **邮箱 issue 订阅功能配置**
     通过 GitHub issue 实现向提取的所有邮箱推送博客更新的功能。
     
     ```yaml
     rss_subscribe:
       enable: true
       github_username: willow-god
       github_repo: Friend-Circle-Lite
       your_blog_url: https://blog.qyliu.top/
     ```
     
     `enable`：开启或关闭，默认开启，如果没有配置请关闭。
     
     `github_username`：github用户名，用来拼接github api地址
     
     `github_repo`：仓库名称，作用同上。
     
     `your_blog_url`：用来定时检测是否有最新文章。
     
   - **SMTP 配置**
     使用配置中的相关信息实现邮件发送功能。
     
     ```yaml
     smtp:
       email: 3162475700@qq.com
       server: smtp.qq.com
       port: 587
       use_tls: true
     ```
     
     `email`：发件人邮箱地址
     
     `server`：`SMTP` 服务器地址
     
     `port`：`SMTP` 端口号
     
     `use_tls`：是否使用 `tls` 加密
     
     这部分配置较为复杂，请自行学习使用。

2. **贡献与定制:**
   欢迎对仓库进行贡献或根据需要进行定制。

### 友圈json生成

1. 将以下文件放置到博客根目录：

   ```javascript
   const YML = require('yamljs')
   const fs = require('fs')
   
   let friends = [],
       data_f = YML.parse(fs.readFileSync('source/_data/link.yml').toString().replace(/(?<=rss:)\s*\n/g, ' ""\n'));
   
   data_f.forEach((entry, index) => {
       let lastIndex = 2;
       if (index < lastIndex) {
           const filteredLinkList = entry.link_list.filter(linkItem => !blacklist.includes(linkItem.name));
           friends = friends.concat(filteredLinkList);
       }
   });
   
   // 根据规定的格式构建 JSON 数据
   const friendData = {
       friends: friends.map(item => {
           return [item.name, item.link, item.avatar];
       })
   };
   
   // 将 JSON 对象转换为字符串
   const friendJSON = JSON.stringify(friendData, null, 2);
   
   // 写入 friend.json 文件
   fs.writeFileSync('./source/friend.json', friendJSON);
   
   console.log('friend.json 文件已生成。');
   ```

2. 在根目录下运行：

   ```bash
   node link.js
   ```

   你将会在source文件中发现文件`friend.json`，即为对应格式文件，下面正常hexo三件套即可放置到网站根目录。

3. (可选)添加运行命令到脚本中方便执行，在根目录下创建：

   ```bash
   @echo off
   E:
   cd E:\Programming\HTML_Language\willow-God\blog
   node link.js && hexo g && hexo algolia && hexo d
   ```

   地址改成自己的，上传时仅需双击即可完成。

   如果是github action，可以在hexo g脚本前添加即可完整构建，注意需要安装yaml包才可解析yml文件。

## 部署到网页

首先，将该项目部署到vercel，部署到vercel的目的主要是利用vercel检测仓库并实时刷新的功能，及时获取all.json文件内容。任意平台均可。

部署完成后，你将获得一个地址，建议自行绑定域名。

在前端页面的md文件中写入：

```html
<div id="friend-circle-lite-root"></div>
<script>
    if (typeof UserConfig === 'undefined') {
        var UserConfig = {
            // 填写你的fc Lite地址
            private_api_url: 'https://fc.liushen.fun/',
            // 点击加载更多时，一次最多加载几篇文章，默认20
            page_turning_number: 20,
            // 头像加载失败时，默认头像地址
            error_img: 'https://pic.imgdb.cn/item/6695daa4d9c307b7e953ee3d.jpg', // https://cdn.qyliu.top/i/2024/03/22/65fcea97b3ca6.png
        }
    }
</script>
<link rel="stylesheet" href="https://fastly.jsdelivr.net/gh/willow-god/Friend-Circle-Lite/main/fclite.min.css">
<script src="https://fastly.jsdelivr.net/gh/willow-god/Friend-Circle-Lite/main/fclite.min.js"></script>
```

其中第一个地址填入你自己的地址即可，**注意**尾部带`/`，不要遗漏。

然后你就可以在前端页面看到我们的结果了。效果图如上展示网站，其中两个文件你可以自行修改，在同目录下我也提供了未压缩版本，有基础的可以很便捷的进行修改。

## 问题与贡献

如果遇到任何问题或有建议，请[提交一个 issue](https://github.com/willow-god/Friend-Circle-Lite/issues)。欢迎贡献代码！

