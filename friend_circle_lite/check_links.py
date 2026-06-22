import csv
import json
import time
import logging
import requests
import warnings
from datetime import datetime
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor

from friend_circle_lite.utils.json import read_json, write_json

warnings.filterwarnings("ignore", message="Unverified HTTPS request is being made.*")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 "
        "(Friend-Circle-Lite/2.0; +https://github.com/scfcn/Friend-Circle-Lite)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "X-Check-Flink": "1.0"
}

RAW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 "
        "(Friend-Circle-Lite/2.0; +https://github.com/scfcn/Friend-Circle-Lite)"
    ),
    "X-Check-Flink": "2.0"
}

API_URL_TEMPLATE = "https://v2.xxapi.cn/api/status?url={}"

# 常见友链页面路径，按出现频率大致排序
LINKPAGE_CANDIDATES = [
    "/link/", "/link",
    "/links/", "/links",
    "/friend/", "/friend",
    "/friends/", "/friends",
    "/flink/", "/flink",
    "/link.html", "/links.html",
    "/friend.html", "/friends.html",
]


def _request_url(session, url, headers=HEADERS, desc="", timeout=15, verify=True, **kwargs):
    """统一封装的 GET 请求函数"""
    try:
        start_time = time.time()
        response = session.get(url, headers=headers, timeout=timeout, verify=verify, **kwargs)
        latency = round(time.time() - start_time, 2)
        return response, latency
    except requests.RequestException as e:
        logging.warning(
            f"[{desc}] 请求失败: {url}，错误如下: \n"
            f"================================================================\n{e}\n"
            f"================================================================"
        )
        return None, -1


def _is_url(path):
    return urlparse(path).scheme in ("http", "https")


def _find_author_link(content, variants):
    """在 HTML 内容中查找是否包含作者链接"""
    for variant in variants:
        if (
            f'href="{variant}"' in content
            or f"href='{variant}'" in content
            or f'href="{variant}/"' in content
            or f"href='{variant}/'" in content
        ):
            return "href"
        if variant in content:
            return "text"
    return None


def _render_with_playwright(url, scroll_times=3, scroll_delay=800):
    """使用 Playwright 渲染页面并模拟滚动，返回最终 HTML"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.warning("未安装 playwright，跳过 JS 渲染")
        return ""

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)

            for _ in range(scroll_times):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(scroll_delay)

            # 再等待一下确保懒加载完成
            page.wait_for_timeout(1000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logging.warning(f"Playwright 渲染失败: {url}, 错误: {e}")
        return ""


def _check_author_link_in_page(session, linkpage_url, author_url, render_js=False):
    """检测友链页面是否包含作者链接"""
    if not author_url:
        return False

    response, _ = _request_url(session, linkpage_url, headers=RAW_HEADERS, desc="友链页面检测")
    if not response:
        return False

    # 处理作者URL，确保有协议号
    normalized = author_url
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized

    # 生成各种可能的URL变体
    variants = {
        normalized,
        normalized.replace("https://", "http://"),
        normalized.replace("https://", "//"),
        normalized.replace("https://", ""),
        author_url,
        "//" + author_url,
        "https://" + author_url,
        "http://" + author_url,
    }

    content = response.text
    result = _find_author_link(content, variants)
    if result == "href":
        logging.info(f"友链页面 {linkpage_url} 中找到作者链接: {normalized}")
        return True
    elif result == "text":
        logging.info(f"友链页面 {linkpage_url} 中包含作者URL文本但非链接")
        return True

    if render_js:
        logging.info(f"初始 HTML 未找到作者链接，尝试 JS 渲染: {linkpage_url}")
        rendered_content = _render_with_playwright(linkpage_url)
        if rendered_content:
            rendered_result = _find_author_link(rendered_content, variants)
            if rendered_result == "href":
                logging.info(f"JS 渲染后找到作者链接: {linkpage_url}")
                return True
            elif rendered_result == "text":
                logging.info(f"JS 渲染后找到作者URL文本: {linkpage_url}")
                return True

    logging.info(f"友链页面 {linkpage_url} 中未找到作者链接")
    return False


# 友链页探测缓存：{域名: 友链页URL 或 ""}
_linkpage_cache = {}


def _detect_linkpage(session, link):
    """根据常见路径自动探测友链页面，首个返回 200 的路径即视为友链页。同域名结果会被缓存。"""
    try:
        parsed = urlparse(link)
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception as e:
        logging.warning(f"解析链接失败: {link}, 错误: {e}")
        return ""

    # 缓存命中则直接返回
    if base in _linkpage_cache:
        cached = _linkpage_cache[base]
        if cached:
            logging.info(f"友链页缓存命中: {link} -> {cached}")
        return cached

    for path in LINKPAGE_CANDIDATES:
        candidate_url = urljoin(base, path)
        response, _ = _request_url(
            session, candidate_url, headers=RAW_HEADERS,
            desc="友链页探测", timeout=10
        )
        if response and response.status_code == 200:
            logging.info(f"自动探测到友链页: {link} -> {candidate_url}")
            _linkpage_cache[base] = candidate_url
            return candidate_url

    logging.info(f"未能自动探测到 {link} 的友链页")
    _linkpage_cache[base] = ""
    return ""


def _resolve_linkpage(session, item, specific_map, previous_map):
    """
    确定最终用于反链检测的友链页地址。
    优先级：specific_map > 数据源自带 > 上一次结果缓存 > 自动探测
    """
    name = item.get("name", "").strip()
    link = item.get("link", "").strip()

    # 1. 自定义特殊映射优先
    if name and name in specific_map:
        return specific_map[name]

    # 2. 数据源自带
    if item.get("linkpage"):
        return item["linkpage"]

    # 3. 上一次结果缓存
    if link and link in previous_map and previous_map[link]:
        return previous_map[link]

    # 4. 自动探测
    if link:
        return _detect_linkpage(session, link)

    return ""


def _fetch_origin_data(origin_path):
    """读取数据源，支持网络/本地 JSON 或 CSV"""
    logging.info(f"正在读取数据源: {origin_path}")
    content = ""

    try:
        if _is_url(origin_path):
            with requests.Session() as session:
                response, _ = _request_url(session, origin_path, headers=RAW_HEADERS, desc="数据源")
                if response:
                    content = response.text
        else:
            with open(origin_path, "r", encoding="utf-8") as f:
                content = f.read()
    except Exception as e:
        logging.error(f"读取数据失败: {e}")
        return []

    try:
        data = json.loads(content)
        if isinstance(data, dict) and "link_list" in data:
            logging.info("成功解析 JSON 格式数据")
            return data["link_list"]
        elif isinstance(data, dict) and "friends" in data and isinstance(data["friends"], list):
            logging.info("成功解析 friend.json 数组格式数据")
            result = []
            for friend in data["friends"]:
                if isinstance(friend, list) and len(friend) >= 2:
                    result.append({"name": friend[0], "link": friend[1]})
                elif isinstance(friend, dict) and friend.get("name") and friend.get("link"):
                    result.append(friend)
            return result
        elif isinstance(data, list):
            logging.info("成功解析 JSON 数组格式数据")
            return data
    except json.JSONDecodeError:
        pass

    try:
        rows = list(csv.reader(content.splitlines()))
        logging.info("成功解析 CSV 格式数据")
        result = []
        for row in rows:
            if len(row) >= 2:
                item = {"name": row[0], "link": row[1]}
                if len(row) >= 3 and row[2].strip():
                    item["linkpage"] = row[2].strip()
                result.append(item)
        return result
    except Exception as e:
        logging.error(f"CSV 解析失败: {e}")
        return []


def _check_backlink(session, item, author_url, specific_map, previous_map, render_js=False):
    """解析/探测友链页，并检测是否包含作者反链"""
    if not author_url:
        return False

    linkpage = _resolve_linkpage(session, item, specific_map, previous_map)
    if linkpage:
        item["linkpage"] = linkpage
        return _check_author_link_in_page(session, linkpage, author_url, render_js)
    return False


def _check_link_round(item, proxy_url_template, author_url, specific_map, previous_map, method, render_js=False, session=None):
    """单轮主 URL 检测：method 为 'direct' 或 'proxy'"""
    link = item["link"]

    if method == "direct":
        url = link
        desc = "直接访问"
    else:
        url = proxy_url_template.format(link) if proxy_url_template else None
        desc = "代理访问"

    if not url or not _is_url(url):
        logging.warning(f"[{desc}] 无效链接: {link}")
        return item, -1, False

    own_session = session is None
    if own_session:
        session = requests.Session()
    try:
        response, latency = _request_url(session, url, desc=desc)
        if response and response.status_code == 200:
            logging.info(f"[{desc}] 成功访问: {link} ，延迟 {latency} 秒")
            has_author_link = _check_backlink(session, item, author_url, specific_map, previous_map, render_js)
            return item, latency, has_author_link
        elif response and response.status_code != 200:
            logging.warning(f"[{desc}] 状态码异常: {link} -> {response.status_code}")
        else:
            logging.warning(f"[{desc}] 请求失败，Response 无效: {link}")
    finally:
        if own_session:
            session.close()

    return item, -1, False


def _check_single_api(item, author_url, specific_map, previous_map, render_js=False):
    """使用第三方 API 检测单个链接"""
    with requests.Session() as session:
        link = item["link"]
        api_url = API_URL_TEMPLATE.format(link)
        response, latency = _request_url(session, api_url, headers=RAW_HEADERS, desc="API 检查", timeout=30)
        has_author_link = False

        if response:
            try:
                res_json = response.json()
                if int(res_json.get("code")) == 200 and int(res_json.get("data")) == 200:
                    logging.info(f"[API] 成功访问: {link} ，状态码 200")
                    item["latency"] = latency
                    has_author_link = _check_backlink(session, item, author_url, specific_map, previous_map, render_js)
                else:
                    logging.warning(f"[API] 状态异常: {link} -> [{res_json.get('code')}, {res_json.get('data')}]")
                    item["latency"] = -1
            except Exception as e:
                logging.error(f"[API] 解析响应失败: {link}，错误: {e}")
                item["latency"] = -1
        else:
            item["latency"] = -1

        return (item, item.get("latency", -1), has_author_link)


def _handle_api_requests(failed_items, author_url, specific_map, previous_map, render_js=False, max_workers=5):
    """使用第三方 API 并发检测失败的链接"""
    if not failed_items:
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_check_single_api, item, author_url, specific_map, previous_map, render_js)
            for item in failed_items
        ]
        results = [f.result() for f in futures]

    return results


def check_and_save(
    source_url,
    author_url="",
    proxy_url="",
    max_workers=10,
    result_file="./result.json",
    specific_linkpage=None,
    render_js=False,
):
    """执行友链检测并保存结果"""
    specific_linkpage = specific_linkpage or []
    specific_map = {
        entry["name"].strip(): entry["url"].strip()
        for entry in specific_linkpage
        if isinstance(entry, dict) and entry.get("name") and entry.get("url")
    }

    proxy_url_template = f"{proxy_url}{{}}" if proxy_url else None

    if proxy_url_template:
        logging.info("代理 URL 获取成功，代理协议: %s", proxy_url_template.split(":")[0])
    else:
        logging.info("未提供代理 URL")

    if author_url:
        logging.info("作者 URL: %s", author_url)
    else:
        logging.warning("未提供作者 URL，将跳过友链页面检测")

    link_list = _fetch_origin_data(source_url)
    if not link_list:
        logging.error("数据源为空或解析失败")
        return False

    previous_results = read_json(result_file) or {}
    previous_map = {
        entry.get("link", "").strip(): entry.get("linkpage", "").strip()
        for entry in previous_results.get("link_status", [])
        if entry.get("link") and entry.get("linkpage")
    }

    # 清除上次运行的探测缓存，确保每次运行干净
    _linkpage_cache.clear()

    # 第一轮：直接访问
    logging.info("开始第一轮检测：直接访问")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        direct_results = list(
            executor.map(
                lambda item: _check_link_round(item, proxy_url_template, author_url, specific_map, previous_map, "direct", render_js),
                link_list,
            )
        )

    success_results = [r for r in direct_results if r[1] != -1]
    proxy_pool = [r[0] for r in direct_results if r[1] == -1]
    logging.info(f"直接访问完成：成功 {len(success_results)} 个，进入第二轮 {len(proxy_pool)} 个")

    # 第二轮：代理访问（仅当配置了代理时）
    if proxy_pool and proxy_url_template:
        logging.info("开始第二轮检测：代理访问")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            proxy_results = list(
                executor.map(
                    lambda item: _check_link_round(item, proxy_url_template, author_url, specific_map, previous_map, "proxy", render_js),
                    proxy_pool,
                )
            )
        proxy_successes = [r for r in proxy_results if r[1] != -1]
        success_results.extend(proxy_successes)
        api_pool = [r[0] for r in proxy_results if r[1] == -1]
        logging.info(f"代理访问完成：成功 {len(proxy_successes)} 个，进入第三轮 {len(api_pool)} 个")
    else:
        if proxy_pool and not proxy_url_template:
            logging.info("未配置代理 URL，跳过第二轮代理访问")
        api_pool = proxy_pool

    # 第三轮：API 兜底
    if api_pool:
        logging.info(f"开始第三轮检测：API 兜底，共 {len(api_pool)} 个")
        api_results = _handle_api_requests(api_pool, author_url, specific_map, previous_map, render_js)
        success_results.extend(api_results)

    results = success_results

    # 预构建历史映射，避免后续 O(n²) 查找
    previous_by_link = {
        entry.get("link", "").strip(): entry
        for entry in previous_results.get("link_status", [])
        if entry.get("link")
    }

    current_links = {item["link"] for item in link_list}
    link_status = []

    for item, latency, has_author_link in results:
        try:
            name = item.get("name", "未知")
            link = item.get("link")
            if not link:
                logging.warning(f"跳过无效项: {item}")
                continue

            prev_entry = previous_by_link.get(link, {})
            prev_fail_count = prev_entry.get("fail_count", 0)
            fail_count = prev_fail_count + 1 if latency == -1 else 0

            link_status.append({
                "name": name,
                "link": link,
                "latency": latency,
                "fail_count": fail_count,
                "has_author_link": has_author_link,
                "linkpage": item.get("linkpage", ""),
            })
        except Exception as e:
            logging.error(f"处理链接时发生错误: {item}, 错误: {e}")

    link_status = [entry for entry in link_status if entry["link"] in current_links]

    accessible = sum(1 for x in link_status if x["latency"] != -1)
    has_author_count = sum(1 for x in link_status if x["has_author_link"])
    total = len(link_status)
    output = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "accessible_count": accessible,
        "inaccessible_count": total - accessible,
        "total_count": total,
        "has_author_link_count": has_author_count,
        "author_url": author_url,
        "link_status": link_status,
    }

    if write_json(result_file, output):
        logging.info(f"共检查 {total} 个链接，成功 {accessible} 个，失败 {total - accessible} 个")
        logging.info(f"其中 {has_author_count} 个友链页面包含作者链接")
        logging.info(f"结果已保存至: {result_file}")
        return True
    return False
