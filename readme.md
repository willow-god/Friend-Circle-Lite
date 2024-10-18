# RSS 订阅前端页面

这是一个用于展示 RSS 订阅内容的简单 HTML 页面。该前端页面用于渲染从后端获取的 RSS 订阅数据。本分支仅包含用于展示的静态资源（HTML、CSS、JS）。

## 功能

- **展示 RSS 订阅内容**：可以显示 RSS 订阅文章的标题、描述和发布时间。
- **简洁设计**：简单直观的用户界面，适用于浏览和查看 RSS 内容。
- **响应式布局**：适配不同设备的浏览体验。

## 部署到网站

如果你已经正确托管本分支到静态托管平台，你可以通过以下几个步骤将数据渲染到你的前端页面：

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
            error_img: 'https://i.p-i.vip/30/20240815-66bced9226a36.webp',
        }
    }
</script>
<link rel="stylesheet" href="https://fastly.jsdelivr.net/gh/willow-god/Friend-Circle-Lite/main/fclite.min.css">
<script src="https://fastly.jsdelivr.net/gh/willow-god/Friend-Circle-Lite/main/fclite.min.js"></script>
```

其中第一个地址填入你自己的地址即可，**注意**尾部带`/`，不要遗漏。
