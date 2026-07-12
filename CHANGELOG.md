# Changelog

## [2.1.0] - 2026-06-08

### 本次更新范围

本次更新整理自 2026-06-06 至 2026-06-08 的提交：

- `a50101a`：将代理配置单独提取出来
- `673ee3b`：完善逻辑，将网站可达性检测深度融入
- `e781ccf`：更新逻辑，实现更加优雅的实现
- `5e9dd6b`：完善日志流
- `d1fde2f`：更新主页，使其更加好看

这次更新重点是减少重复请求、稳定公开数据结构、整理配置项、增强调试能力，并重写独立展示首页。

---

### 核心逻辑调整

#### 1. 友链可达性检测成为友圈抓取前置流程

友圈抓取现在依赖友链可达性检测结果，`link_check.enable` 旧字段仍会兼容读取，但不再作为有效开关。

新的检测流程如下：

1. 优先尝试 RSS 探测或复用缓存 RSS。
2. RSS 可解析时，直接认为站点可达且可抓取。
3. RSS 不可解析时，记录 `crawlable=false`，再尝试主页可达性。
4. 主页仍不可达时，再使用状态码 API 作为兜底可达性判断。
5. 反链检测在可达性检测后执行，只有站点可达时才继续检测。

这样后续友圈抓取只会尝试 `crawlable=true` 且存在 RSS 缓存的站点，不会在每次抓取时重复遍历探测所有 RSS 地址。

默认运行节奏为：

- GitHub Actions 每 4 小时执行一次友链朋友圈任务。
- 友链可达性检测与 RSS 探测按 `link_check.max_age_hours` 控制，默认 24 小时才对同一站点重新检测一次。
- 没有 RSS 的站点会缓存为 `crawlable=false`，在缓存有效期内直接跳过，不会每 4 小时重复探测。
- 每 4 小时的友圈抓取会复用检测缓存，只请求可抓取 RSS 的站点，从而在保证文章更新频率的同时尽量降低请求数量。

#### 2. RSS 缓存与可达性缓存合并维护

- 友链检测缓存默认 24 小时，由 `link_check.max_age_hours` 控制。
- 缓存未过期时，RSS 地址、主页可达性、反链结果会直接复用。
- 已缓存 RSS 地址的站点会优先重新验证该 RSS；验证失败后才重新走 RSS 探测流程。
- 主页 URL 与友链页 URL 会做末尾斜杠归一化，避免同一站点因 `/` 差异重复检测。
- 新增参考延迟 `latency`，取 RSS、主页或 API 阶段中实际完成检测的耗时，不再使用 `0.0` 或 `-1.0` 作为公开占位值。

#### 3. 反链检测独立于 RSS 探测

反链检测以友链原数据中的主页 URL / 友链页 URL 为依据，不依赖 RSS 探测结果。若站点不可达，则反链直接视为未通过；若站点可达且开启 `enable_backlink_check`，才请求友链页并判断是否包含 `author_url`。

---

### 配置变更

#### 1. 新增代理配置块

代理配置从友链检测中拆出，统一放到顶级 `proxy_settings`：

```yaml
proxy_settings:
  proxy_url: ""
```

程序会先直连，请求失败且配置了代理时自动走代理。推荐通过仓库环境变量 `PROXY_URL` 覆盖，不建议直接把代理地址写入配置文件。

推荐代理格式为代理前缀：

```text
https://proxy.example.com/
```

程序会自动拼接为：

```text
https://proxy.example.com/https://example.com/feed.xml
```

如需自行搭建代理，可参考：[使用 CF Workers 搭建反代加速器](https://blog.liushen.fun/posts/dd89adc9/)。

仍兼容 `https://proxy.example.com?url={url}` 这类高级格式，但普通反代场景不推荐。

#### 2. `link_check` 配置简化

当前有效配置如下：

```yaml
link_check:
  max_age_hours: 24
  timeout: 15
  max_workers: 10
  status_api_url: "https://v2.xxapi.cn/api/status?url={url}"
  enable_backlink_check: true
  author_url: "blog.liushen.fun"
```

变化说明：

- `enable`：旧字段兼容读取，但友圈抓取依赖可达性检测，因此不再作为有效开关。
- `proxy_url`：已移动到 `proxy_settings.proxy_url`。
- `status_api_url`：只作为兜底可达性检测。API-only 结果只用于展示，不参与 RSS 抓取。

#### 3. 新增调试开关

```yaml
debug: false
```

也可以通过环境变量开启：

```text
FCL_DEBUG=1
```

开启后，程序结束前会全量打印 SQLite 缓存表结构与所有数据，并保守清理核心表中的旧字段或残留结构，方便定位缓存兼容问题。

---

### 数据结构变更

#### 1. `all.json` 保持稳定

`all.json` 仍只面向友链朋友圈文章展示，公开结构不变：

```json
{
  "statistical_data": {
    "friends_num": 201,
    "active_num": 160,
    "error_num": 41,
    "article_num": 275,
    "last_updated_time": "2026-06-07 00:41:06"
  },
  "article_data": []
}
```

#### 2. `link.json` 简化为可达性展示数据

`link.json` 集中保存友链可达性数据和检测统计：

```json
{
  "statistical_data": {
    "link_total_num": 201,
    "link_reachable_num": 182,
    "link_unreachable_num": 19,
    "crawl_allowed_num": 180,
    "api_only_num": 0,
    "has_author_link_num": 130,
    "link_last_checked_time": "2026-06-07 00:40:31"
  },
  "link_data": [
    {
      "name": "清羽飞扬",
      "link": "https://blog.liushen.fun/",
      "link_page": "https://blog.liushen.fun/link/",
      "avatar": "https://blog.liushen.fun/favicon.ico",
      "reachable": true,
      "crawlable": true,
      "latency": 0.21,
      "fail_count": 0,
      "has_backlink": true
    }
  ]
}
```

本次移除公开展示中不必要的冗余字段：

- `method`
- `reason`
- 单站 `checked_at`

保留顶部 `link_last_checked_time` 用于表示本轮友链检测数据更新时间。缓存未过期且未重新检测时，该时间不会被每次运行强行刷新。

#### 3. `errors.json`

`errors.json` 仍作为兼容输出保留，用于旧流程或需要查看异常友链的场景。新首页主要读取 `all.json` 与 `link.json`。

---

### 数据合并

数据合并继续使用顶级 `merge_settings`：

```yaml
merge_settings:
  enable: false
  remote_base_url: "https://fc.liushen.fun"
  merge_article_data: true
  merge_link_check_data: true
```

合并时会按 `remote_base_url` 自动请求：

- `/all.json`
- `/link.json`
- `/errors.json`

文章数据与友链可达性数据可分别通过 `merge_article_data`、`merge_link_check_data` 控制。适合国内外两条线路分别维护缓存后再合并公开输出。

---

### 日志与 GitHub Actions

- 日志增加模块标签，例如 `[爬虫入口]`、`[友链检测]`、`[RSS 抓取]`，并补充总友链数、缓存复用数、本次实际检测数等关键信息。
- URL 后统一留空格再接中文说明，避免日志中的链接和中文被部分渲染器连在一起。
- GitHub Actions 定时任务调整为 `22 */4 * * *`，避开整点拥堵。
- 工作流增加 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`，提前适配 GitHub Actions Node.js 24 运行时。

---

### 前端展示页

`static/index.html` 重写为单文件展示页：

- 顶部可切换 `友链可达性` 与 `友链朋友圈`。
- `友链可达性` 默认显示不可达友链，`全部` 按钮放在最后。
- `友链朋友圈` 默认显示前 24 条，`全部` 按钮放在最后。
- 友链状态以图标展示，鼠标悬浮显示详细说明。
- 文章卡片展示作者头像，标题最多两行并自动省略。
- 页面恢复国风浅蓝背景与《登金陵凤凰台》诗句底纹。
- 滚动条、响应式布局、少量文章卡片高度等细节已优化。
- `main/fclite.js` 和 `main/fclite.css` 保持不变，外部用户原有嵌入方式不受影响。

---

### 迁移提示

从旧配置升级时，建议检查以下内容：

1. 将代理地址从 `link_check.proxy_url` 移到 `proxy_settings.proxy_url`，或直接使用仓库环境变量 `PROXY_URL`。
2. 删除或忽略 `link_check.enable`，当前友链检测会始终作为友圈抓取前置流程运行。
3. 若使用自定义发布脚本，请确保发布目录包含 `all.json`、`link.json`、`errors.json`。
4. 若之前依赖 `link.json` 中的 `method`、`reason`、单站 `checked_at`，请改用 `reachable`、`crawlable`、`latency`、`fail_count`、`has_backlink` 与顶部 `link_last_checked_time`。
5. 出现缓存兼容问题时，可临时设置 `FCL_DEBUG=1` 查看 SQLite 缓存内容。

---

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
