import csv
import json
import time
import logging
import requests
import warnings
from queue import Queue
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
    "/pyq/", "/pyq",
    "/link.html", "/links.html",
    "/friend.html", "/friends.html",
]

# 用于判断页面是否为友链页的内容关键词
LINKPAGE_INDICATORS = [
    "友链", "友情链接", "交换链接",
    "friends", "links", "friend list", "link list",
    "友链朋友圈", "link-list", "friend-list",
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


def _check_author_link_in_page(session, linkpage_url, author_url):
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
    found_in_href = False
    found_as_text = False

    for variant in variants:
        if (
            f'href="{variant}"' in content
            or f"href='{variant}'" in content
            or f'href="{variant}/"' in content
            or f"href='{variant}/'" in content
        ):
            found_in_href = True
            break

        if variant in content:
            found_as_text = True

    if found_in_href:
        logging.info(f"友链页面 {linkpage_url} 中找到作者链接: {normalized}")
        return True
    elif found_as_text:
        logging.info(f"友链页面 {linkpage_url} 中包含作者URL文本但非链接")
        return True
    else:
        logging.info(f"友链页面 {linkpage_url} 中未找到作者链接")
        return False


def _detect_linkpage(session, link):
    """根据常见路径自动探测友链页面"""
    try:
        parsed = urlparse(link)
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception as e:
        logging.warning(f"解析链接失败: {link}, 错误: {e}")
        return ""

    for path in LINKPAGE_CANDIDATES:
        candidate_url = urljoin(base, path)
        response, _ = _request_url(
            session, candidate_url, headers=RAW_HEADERS,
            desc="友链页探测", timeout=10
        )
        if not response or response.status_code != 200:
            continue

        content = response.text.lower()
        if any(indicator.lower() in content for indicator in LINKPAGE_INDICATORS):
            logging.info(f"自动探测到友链页: {link} -> {candidate_url}")
            return candidate_url

    logging.info(f"未能自动探测到 {link} 的友链页")
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


def _check_one_link(item, proxy_url_template, author_url, specific_map, previous_map):
    """单个链接检测（每个线程独立 session，避免线程安全问题）"""
    link = item["link"]
    has_author_link = False

    with requests.Session() as session:
        # 解析/探测友链页地址
        linkpage = _resolve_linkpage(session, item, specific_map, previous_map)
        if linkpage:
            item["linkpage"] = linkpage

        for method, url in [
            ("直接访问", link),
            ("代理访问", proxy_url_template.format(link) if proxy_url_template else None),
        ]:
            if not url or not _is_url(url):
                logging.warning(f"[{method}] 无效链接: {link}")
                continue

            response, latency = _request_url(session, url, desc=method)
            if response and response.status_code == 200:
                logging.info(f"[{method}] 成功访问: {link} ，延迟 {latency} 秒")

                if item.get("linkpage") and author_url:
                    has_author_link = _check_author_link_in_page(session, item["linkpage"], author_url)

                return item, latency, has_author_link
            elif response and response.status_code != 200:
                logging.warning(f"[{method}] 状态码异常: {link} -> {response.status_code}")
            else:
                logging.warning(f"[{method}] 请求失败，Response 无效: {link}")

    return item, -1, False


def _handle_api_requests(failed_items, author_url, specific_map, previous_map):
    """使用第三方 API 兜底检测失败的链接"""
    results = []
    with requests.Session() as session:
        for item in failed_items:
            time.sleep(0.2)
            link = item["link"]
            api_url = API_URL_TEMPLATE.format(link)
            response, latency = _request_url(session, api_url, headers=RAW_HEADERS, desc="API 检查", timeout=30)
            has_author_link = False

            # API 路径下同样解析/探测友链页
            linkpage = _resolve_linkpage(session, item, specific_map, previous_map)
            if linkpage:
                item["linkpage"] = linkpage

            if response:
                try:
                    res_json = response.json()
                    if int(res_json.get("code")) == 200 and int(res_json.get("data")) == 200:
                        logging.info(f"[API] 成功访问: {link} ，状态码 200")
                        item["latency"] = latency

                        if item.get("linkpage") and author_url:
                            has_author_link = _check_author_link_in_page(session, item["linkpage"], author_url)
                    else:
                        logging.warning(f"[API] 状态异常: {link} -> [{res_json.get('code')}, {res_json.get('data')}]")
                        item["latency"] = -1
                except Exception as e:
                    logging.error(f"[API] 解析响应失败: {link}，错误: {e}")
                    item["latency"] = -1
            else:
                item["latency"] = -1

            results.append((item, item.get("latency", -1), has_author_link))

    return results


def check_and_save(
    source_url,
    author_url="",
    proxy_url="",
    max_workers=10,
    result_file="./result.json",
    specific_linkpage=None,
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

    api_request_queue = Queue()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(
            executor.map(
                lambda item: _check_one_link(item, proxy_url_template, author_url, specific_map, previous_map),
                link_list,
            )
        )

    # 收集需要 API 兜底的项
    for item, latency, _ in results:
        if latency == -1:
            api_request_queue.put(item)

    updated_api_results = _handle_api_requests(list(api_request_queue.queue), author_url, specific_map, previous_map)
    for updated_item in updated_api_results:
        for idx, (item, latency, has_author) in enumerate(results):
            if item["link"] == updated_item[0]["link"]:
                results[idx] = updated_item
                break

    current_links = {item["link"] for item in link_list}
    link_status = []

    for item, latency, has_author_link in results:
        try:
            name = item.get("name", "未知")
            link = item.get("link")
            if not link:
                logging.warning(f"跳过无效项: {item}")
                continue

            prev_entry = next(
                (x for x in previous_results.get("link_status", []) if x.get("link") == link),
                {},
            )
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
