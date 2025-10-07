from tooldelta import (
    Plugin,
    utils,
    Player,
    plugin_entry,
    cfg,
    fmts,
)

import time
import requests
from enum import Enum


class HitokotoType(str, Enum):
    """一言分类枚举"""
    动画 = "a"
    漫画 = "b"
    游戏 = "c"
    文学 = "d"
    原创 = "e"
    来自网络 = "f"
    其他 = "g"
    影视 = "h"
    诗词 = "i"
    网易云 = "j"
    哲学 = "k"
    抖机灵 = "l"


class NewPlugin(Plugin):
    name = "进服一言"
    author = "机入 & Q3CC"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        # 定义配置标准
        STD_CFG = {
            "一言分类": str,
            "等待时间": int,
            "分类说明": str,
        }
        # 默认配置
        DEFAULT_CFG = {
            "一言分类": "网易云",
            "等待时间": 10,
            "分类说明": "可选: 动画, 漫画, 游戏, 文学, 原创, 来自网络, 其他, 影视, 诗词, 网易云, 哲学, 抖机灵（我也不知道这是什么）",
        }
        # 获取配置
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name,
            STD_CFG,
            DEFAULT_CFG,
            self.version,
        )
        self.ListenPreload(self.on_def)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        # 验证配置的分类是否有效
        category = self.cfg["一言分类"]
        valid_categories = [member.name for member in HitokotoType]
        if category not in valid_categories:
            fmts.print_war(f"配置的分类 '{category}' 无效, 将使用默认分类 '网易云'")
            self.category_code = HitokotoType.网易云.value
        else:
            self.category_code = HitokotoType[category].value
            fmts.print_suc(f"一言分类已设置为: {category}")

    @utils.thread_func("一言")
    def on_player_join(self, player: Player):
        playername = player.name
        try:
            time.sleep(self.cfg["等待时间"])  # 等待玩家完全进入
            data = requests.get(
                f"https://v1.hitokoto.cn/?c={self.category_code}&encode=text",
                timeout=10
            )
            if data.status_code == 200:
                if data.text.strip():
                    self.game_ctrl.say_to(playername, f"一言: {data.text}")
                else:
                    fmts.print_err("一言API返回空内容")
            else:
                fmts.print_err(f"一言API返回错误状态码: {data.status_code}")
        except requests.RequestException as e:  # 异常
            fmts.print_err(f"一言异常: {e}")


entry = plugin_entry(NewPlugin)
