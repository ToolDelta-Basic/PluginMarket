from typing import Any, Dict, List


NO_CREATE_REGIONS_FILE = "不可创建领地区域.json"
CONFIG_FILE_DIR = "插件配置文件"
DYNAMIC_LOAD_SETTINGS_KEY = "动态载入设置"
DYNAMIC_LOAD_ENABLED_KEY = "是否启用动态载入配置文件（仅用于本插件）"
DYNAMIC_LOAD_INTERVAL_KEY = "动态载入检测时间间隔（单位：秒）"
DYNAMIC_LOAD_DEFAULT_INTERVAL = 5


def default_config() -> Dict[str, Any]:
    return {
        DYNAMIC_LOAD_SETTINGS_KEY: {
            DYNAMIC_LOAD_ENABLED_KEY: True,
            DYNAMIC_LOAD_INTERVAL_KEY: DYNAMIC_LOAD_DEFAULT_INTERVAL,
        },
        "是否启用": True,
        "唤醒词": [".领地"],
        "数据文件": "领地数据.json",
        "检测间隔": 2,
        "缓冲区距离": 5,
        "传送半径": 5000,
        "最大领地半径": 200,
        "最大领地长": 200,
        "最大领地高": 200,
        "最大领地宽": 200,
        "最大领地数量": 4,
        "白名单": ["小石潭记qwq"],
    }


def default_no_create_regions() -> List[Dict[str, Any]]:
    return [
        {
            "名称": "主城保护范围",
            "启用": True,
            "类型": "圆形",
            "中心": [10017, 209, 20016],
            "半径": 500,
        },
        {
            "名称": "示例圆形区域",
            "启用": False,
            "类型": "圆形",
            "中心": [0, 64, 0],
            "半径": 100,
        },
        {
            "名称": "示例方形区域",
            "启用": False,
            "类型": "方形",
            "起点": [0, -64, 0],
            "终点": [100, 320, 100],
        },
    ]
