import logging
from urllib.parse import urlparse, urljoin
import re

def replace_non_domain(link: str, blog_url: str) -> str:
    """
    暂未实现
    检测并替换字符串中的非正常域名部分（如 IP 地址或 localhost），替换为 blog_url。
    替换后强制使用 https，且考虑 blog_url 尾部是否有斜杠。

    :param link: 原始地址字符串
    :param blog_url: 替换为的博客地址
    :return: 替换后的地址字符串
    """
    try:
        parsed = urlparse(link)
        if 'localhost' in parsed.netloc or re.match(r'^\d{1,3}(\.\d{1,3}){3}$', parsed.netloc):  # IP地址或localhost
            # 提取 path + query
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            return urljoin(blog_url.rstrip('/') + '/', path.lstrip('/'))
        else:
            return link  # 合法域名则返回原链接
    except Exception as e:
        logging.warning(f"替换链接时出错：{link}, error: {e}")
        return link
