# SQLite 设计说明

运行期状态统一保存在 `runtime_paths.cache_file`（默认 `./temp/cache.sqlite3`）。GitHub Actions 通过 `temp` artifact 在多次运行之间传递这个文件。

## 表结构

| 表 | 主键 | 作用 | 生命周期 |
| --- | --- | --- | --- |
| `feed_cache` | `name` | 记录站点可用的 RSS 地址，避免每次重新探测 | 长期 |
| `link_check_state` | 归一化后的主页 `url` | 友链可达性、RSS 可抓取性、反链、不可达起点等检测快照 | 按 `max_age_hours` 刷新 |
| `article_tracking` | 自增 `id` | 保存订阅推送使用的最近文章快照（默认最多 10 篇） | 每次订阅检查覆盖 |
| `app_state` | `key` | 跨运行的小型状态，例如邮件推送基线与上次发送的计划时间 | 长期 |

所有建表语句集中在 `friend_circle_lite/storage/schema.py`，运行时存储与 `debug` 模式下的 schema 诊断共用同一份定义，避免字段漂移。

## 设计取舍

- **`feed_cache` 使用站点名称作为主键**：上游友链 JSON、`specific_RSS` 配置和 RSS 缓存都按名称匹配，保持现状可以避免额外的映射层。代价是同一名称的两个站点会互相覆盖；如果未来出现重名需求，建议改为 `(name, url)` 复合键并补一个按名称查询的索引。
- **`link_check_state` 使用归一化 URL 作为主键**：同一站点可能改名，URL 更稳定；名称、头像、友链页作为检测快照冗余保存，便于直接生成 `link.json`。
- **`article_tracking` 每次覆盖写入**：只保留最近若干篇用于判断“新文章”，历史数据没有长期保留价值。
- **`app_state` 使用键值对**：邮件推送的 cron 基线和最近发送时间很小且结构可能演进，单独建表比塞进业务表更清晰。
- **已移除 `fail_count`**：不可达时长现在由 `unreachable_since` 计算，旧字段没有读写价值；旧数据库在正常运行时保留该列也不会报错，开启 `debug` 时诊断器会按当前 schema 重建表并清理。
- **不启用 WAL / 复杂索引**：程序是单进程、低频写入，表规模很小（友链数量级），当前设计足够；如未来改成并发服务，再考虑 WAL 与索引。

## 迁移策略

- 旧版 `cache.json`、`feed_cache.yaml`、`newest_posts.json` 会在首次读取时自动迁移到 SQLite。
- `link_check_state` 的增量字段会在启动时通过 `ALTER TABLE` 补齐。
- 更大幅度的 schema 漂移可以在配置中开启 `debug: true`，由 `SQLiteDebugDumper` 保守重建核心表并输出全量数据。
