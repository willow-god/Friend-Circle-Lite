import yaml
import logging

def load_config(config_file):
    """
    加载配置文件。
    
    参数：
    config_file (str): 配置文件的路径。
    
    返回：
    dict: 加载的配置数据。
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logging.error(f"配置文件 {config_file} 未找到")
        return {}
    except yaml.YAMLError as e:
        logging.error(f"YAML解析错误: {str(e)}")
        return {}
    except Exception as e:
        logging.error(f"加载配置文件时发生未知错误: {str(e)}")
        return {}
