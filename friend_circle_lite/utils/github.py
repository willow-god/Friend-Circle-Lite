import logging
import requests
import re
from friend_circle_lite import HEADERS_JSON

def extract_emails_from_issues(api_url):
    """
    从GitHub issues API中提取以[e-mail]开头的title中的邮箱地址。

    参数：
    api_url (str): GitHub issues API的URL。

    返回：
    dict: 包含所有提取的邮箱地址的字典。
    {
        "emails": [
            "3162475700@qq.com"
        ]
    }
    """
    try:
        response = requests.get(api_url, headers=HEADERS_JSON, timeout=10)
        response.raise_for_status()
        issues = response.json()
    except Exception as e:
        logging.error(f"无法获取 GitHub issues 数据，错误信息: {e}")
        return None

    email_pattern = re.compile(r'^\[邮箱订阅\](.+)$')
    emails = []

    for issue in issues:
        title = issue.get("title", "")
        match = email_pattern.match(title)
        if match:
            email = match.group(1).strip()
            emails.append(email)

    return {"emails": emails}