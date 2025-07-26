import logging
from dateutil import parser
from datetime import datetime, timezone, timedelta

def format_published_time(time_str):
    """
    格式化发布时间为统一格式 YYYY-MM-DD HH:MM

    参数:
    time_str (str): 输入的时间字符串，可能是多种格式。

    返回:
    str: 格式化后的时间字符串，若解析失败返回空字符串。
    """
    # 尝试自动解析输入时间字符串
    try:
        parsed_time = parser.parse(time_str, fuzzy=True)
    except (ValueError, parser.ParserError):
        # 定义支持的时间格式
        time_formats = [
            '%a, %d %b %Y %H:%M:%S %z',  # Mon, 11 Mar 2024 14:08:32 +0000
            '%a, %d %b %Y %H:%M:%S GMT',   # Wed, 19 Jun 2024 09:43:53 GMT
            '%Y-%m-%dT%H:%M:%S%z',         # 2024-03-11T14:08:32+00:00
            '%Y-%m-%dT%H:%M:%SZ',          # 2024-03-11T14:08:32Z
            '%Y-%m-%d %H:%M:%S',           # 2024-03-11 14:08:32
            '%Y-%m-%d'                     # 2024-03-11
        ]
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(time_str, fmt)
                break
            except ValueError:
                continue
        else:
            logging.warning(f"无法解析时间字符串：{time_str}")
            return ''

    # 处理时区转换
    if parsed_time.tzinfo is None:
        parsed_time = parsed_time.replace(tzinfo=timezone.utc)
    shanghai_time = parsed_time.astimezone(timezone(timedelta(hours=8)))
    return shanghai_time.strftime('%Y-%m-%d %H:%M')