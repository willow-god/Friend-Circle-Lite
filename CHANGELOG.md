# Changelog

## [2.0.0] - 2026-05-31

### 🎉 重大更新：友链可达性检测与数据结构重构

本次更新合并了 [check-flink](https://github.com/willow-god/check-flink) 项目的友链可达性检测功能，并对数据结构进行了重大重构，实现了友圈文章与友链状态的分离。

---

## 📋 目录

- [核心功能变更](#核心功能变更)
- [数据结构变更](#数据结构变更)
- [配置文件变更](#配置文件变更)
- [前端页面变更](#前端页面变更)
- [迁移指南](#迁移指南)
- [兼容性说明](#兼容性说明)

---

## 🚀 核心功能变更

### 新增功能

#### 1. 友链可达性检测
- **直连检测**：直接访问友链站点，验证可达性
- **代理检测**：通过代理服务（如 Cloudflare Worker）检测被墙站点
- **API 检测**：通过第三方 API 兜底检测（如 xxapi.cn）
- **反链检测**：检测友链页面是否包含你的站点链接
- **智能缓存**：检测结果缓存 24 小时，避免频繁请求
- **失败计数**：记录连续失败次数，便于识别长期失效友链

#### 2. 数据合并功能重构
- **独立配置**：`merge_settings` 从 `spider_settings` 中独立出来
- **并列控制**：友圈文章和友链可达性数据分别控制是否合并
- **智能合并**：
  - 可达性优先级：direct > proxy > api > none
  - 延迟取最优：选择响应时间更短的结果
  - 反链取并集：任一环境检测到反链即为有反链
  - 失败次数取最小：选择失败次数较少的结果

#### 3. 前端展示页面
- **新首页**：继承 check-flink 风格，同时展示友链状态和友圈文章
- **友链状态卡片**：显示可达性、响应时间、失败次数、反链状态
- **状态过滤**：支持按全部/失效/可抓取/仅API/较慢筛选
- **搜索功能**：同时搜索友链、文章、作者

---

## 📊 数据结构变更

### 旧结构（v1.x）

```json
// all.json（混合数据）
{
  "statistical_data": {
    "friends_num": 199,
    "active_num": 155,
    "article_num": 250,
    "error_num": 15
  },
  "article_data": [...],
  "link_check_data": [...],    // ❌ 已移除
  "friend_data": [...]          // ❌ 已移除
}

// errors.json
[
  ["站点名", "站点地址", "头像地址"],
  ...
]
```

### 新结构（v2.0）

```json
// all.json（仅友圈文章）
{
  "statistical_data": {
    "friends_num": 199,
    "active_num": 155,
    "article_num": 250,
    "error_num": 15
  },
  "article_data": [...]
}

// link.json（友链可达性）✨ 新增
{
  "statistical_data": {
    "link_total_num": 199,
    "link_reachable_num": 187,
    "link_unreachable_num": 12,
    "crawl_allowed_num": 167,
    "api_only_num": 20,
    "has_author_link_num": 131,
    "link_last_checked_time": "2026-05-31 19:33:00"
  },
  "link_data": [
    {
      "name": "清羽飞扬",
      "link": "https://blog.liushen.fun/",
      "link_page": "https://blog.liushen.fun/link/",
      "avatar": "https://blog.liushen.fun/favicon.ico",
      "reachable": true,
      "crawlable": true,
      "method": "direct",
      "latency": 0.07,
      "fail_count": 0,
      "checked_at": "2026-05-31 19:33:00",
      "has_backlink": true,
      "reason": "allowed_by_direct"
    },
    ...
  ]
}

// errors.json（真正不可达的友链）
[
  ["站点名", "站点地址", "头像地址"],
  ...
]
```

### 字段说明

#### link.json 中的 link_data 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 友链名称 |
| `link` | string | 友链地址 |
| `link_page` | string | 友链页地址（用于反链检测） |
| `avatar` | string | 头像地址 |
| `reachable` | boolean | 是否可达 |
| `crawlable` | boolean | 是否可抓取（直连或代理可达） |
| `method` | string | 最佳检测方式：`direct`/`proxy`/`api`/`disabled` |
| `latency` | number | 响应延迟（秒），-1 表示不可达 |
| `fail_count` | number | 连续失败次数 |
| `checked_at` | string | 检测时间 |
| `has_backlink` | boolean\|null | 是否有反链，null 表示未检测 |
| `reason` | string | RSS 抓取决策原因 |

---

## ⚙️ 配置文件变更

### 旧配置（v1.x）

```yaml
spider_settings:
  enable: true
  json_url: "https://blog.liushen.fun/friend.json"
  article_count: 5
  merge_result:                    # ❌ 已废弃
    enable: false
    merge_json_url: "https://fc.liushen.fun"
```

### 新配置（v2.0）

```yaml
spider_settings:
  enable: true
  json_url: "https://blog.liushen.fun/friend.json"
  article_count: 5

# ✨ 新增：友链可达性检测配置
link_check:
  enable: true                      # 是否启用友链可达性检测
  max_age_hours: 24                 # 缓存时间（小时）
  timeout: 15                       # 请求超时时间（秒）
  max_workers: 10                   # 并发检测数量
  proxy_url: ""                     # 代理前缀（如 Cloudflare Worker）
                                    # ⚠️ 代理服务可能违反某些服务条款，请谨慎使用
                                    # 支持环境变量 LINK_CHECK_PROXY_URL 覆盖（优先级更高）
  status_api_url: "https://v2.xxapi.cn/api/status?url={url}"  # 兜底 API
  enable_backlink_check: true       # 是否检测反链
  author_url: "blog.liushen.fun"    # 你的站点域名

# ✨ 新增：数据合并配置（独立出来）
merge_settings:
  enable: false                     # 是否启用数据合并
  remote_base_url: "https://fc.liushen.fun"  # 远程数据源基础 URL
  merge_article_data: true          # 是否合并友圈文章数据
  merge_link_check_data: true       # 是否合并友链可达性数据
```

### 配置变更说明

#### 1. `merge_result` → `merge_settings`
- **位置变更**：从 `spider_settings.merge_result` 移至顶级 `merge_settings`
- **字段重命名**：
  - `merge_json_url` → `remote_base_url`
  - 新增 `merge_article_data`（友圈文章合并开关）
  - 新增 `merge_link_check_data`（友链可达性合并开关）

#### 2. 友链数据格式
- **旧格式（3字段）**：`["站点名", "站点地址", "头像地址"]`
- **新格式（4字段）**：`["站点名", "站点地址", "友链页地址", "头像地址"]`
- **兼容性**：两种格式均支持，自动识别

---

## 🎨 前端页面变更

### 文件变更

| 文件 | 状态 | 说明 |
|------|------|------|
| `static/index.html` | ✏️ 重写 | 继承 check-flink 风格，展示友链状态+友圈文章 |
| `static/status.html` | ❌ 删除 | 功能已合并到 index.html |
| `main/fclite.js` | ✅ 保持 | 不变，供外部引用 |
| `main/fclite.css` | ✅ 保持 | 不变，供外部引用 |

### 新首页特性

- **诗词背景**：李白《登金陵凤凰台》
- **统计卡片**：友链总数、可抓取、文章总数、失效友链
- **友链状态展示**：
  - 状态点动画（绿色=正常，黄色=较慢，蓝色=API，红色=失效）
  - 失败次数显示
  - 反链图标（❤️ 有反链 / 💔 无反链）
- **友圈文章展示**：标题固定两行高度，作者+时间
- **搜索过滤**：同时搜索友链、文章、作者

---

## 🔄 迁移指南

### 对于使用者

#### 1. 更新配置文件

如果你之前启用了 `merge_result`，需要调整配置：

```yaml
# 旧配置
spider_settings:
  merge_result:
    enable: true
    merge_json_url: "https://example.com"

# 新配置
merge_settings:
  enable: true
  remote_base_url: "https://example.com"
  merge_article_data: true
  merge_link_check_data: true
```

#### 2. 更新友链数据格式（可选）

如果想启用反链检测，建议更新为 4 字段格式：

```json
{
  "friends": [
    ["清羽飞扬", "https://blog.liushen.fun/", "https://blog.liushen.fun/link/", "https://blog.liushen.fun/favicon.ico"]
  ]
}
```

#### 3. 更新 GitHub Actions

如果自定义了 workflow，需要添加 `link.json` 到发布文件：

```yaml
- name: Build static publish directory
  run: |
    mkdir pages
    cp -r main static all.json link.json errors.json pages/
```

### 对于外部引用者

#### 如果你引用了 `all.json`

✅ **无需修改**，`all.json` 结构保持兼容，仅移除了 `link_check_data` 和 `friend_data` 字段。

#### 如果你引用了 `main/fclite.js` 和 `main/fclite.css`

✅ **无需修改**，这两个文件保持不变。

#### 如果你需要友链可达性数据

✨ **新增引用** `link.json`：

```javascript
fetch('/link.json')
  .then(response => response.json())
  .then(data => {
    const links = data.link_data;
    const stats = data.statistical_data;
    // 使用友链数据
  });
```

---

## ✅ 兼容性说明

### 向后兼容

- ✅ `all.json` 结构保持兼容（仅移除冗余字段）
- ✅ `errors.json` 结构不变
- ✅ `main/fclite.js` 和 `main/fclite.css` 不变
- ✅ 友链数据支持 3 字段和 4 字段格式
- ✅ 旧版引用者无需修改代码

### 不兼容变更

- ❌ `all.json` 不再包含 `link_check_data` 和 `friend_data`
- ❌ `spider_settings.merge_result` 配置已废弃
- ❌ `static/status.html` 已删除

### 升级建议

1. **最小升级**：仅更新代码，不修改配置 → 友链检测默认启用，但反链检测默认关闭
2. **推荐升级**：更新配置 + 更新友链数据为 4 字段格式 → 完整体验所有新功能
3. **完整升级**：更新配置 + 更新友链数据 + 启用数据合并 → 国内外数据智能合并

---

## 📝 相关链接

- [Friend-Circle-Lite 主仓库](https://github.com/willow-god/Friend-Circle-Lite)
- [check-flink 原项目](https://github.com/willow-god/check-flink)
- [详细文档](https://blog.liushen.fun/posts/4dc716ec/)

---

## 🙏 致谢

感谢所有使用 Friend-Circle-Lite 的朋友们，以及为项目提供反馈和建议的贡献者！
