import yaml

def load_config(config_file):
    """
    加载配置文件。
    
    参数：
    config_file (str): 配置文件的路径。
    
    返回：
    dict: 加载的配置数据。
    """
    with open(config_file, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)