import logging
from friend_circle_lite.utils.json import read_json, write_json

def load_cache(cache_file: str):
    if not cache_file:
        return []
    
    data = read_json(cache_file)
    if data is None:
        logging.info(f"缓存文件 {cache_file} 不存在或无法读取，将自动创建。")
        return []

    if not isinstance(data, list):
        logging.warning(f"缓存文件 {cache_file} 格式异常（应为列表）。将忽略。")
        return []

    norm = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        url = item.get('url')
        if name and url:
            norm.append({'name': name, 'url': url, 'source': 'cache'})
    return norm

def save_cache(cache_file: str, cache_items: list[dict]):
    if not cache_file:
        return

    out = [{'name': i['name'], 'url': i['url']} for i in cache_items]
    if write_json(cache_file, out):
        logging.info(f"缓存已保存到 {cache_file}（{len(out)} 条）。")
    else:
        logging.error(f"保存缓存文件 {cache_file} 失败")
