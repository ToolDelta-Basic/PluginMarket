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
    ANIMATION = "a"      # 动画
    COMIC = "b"          # 漫画
    GAME = "c"           # 游戏
    LITERATURE = "d"     # 文学
    ORIGINAL = "e"       # 原创
    INTERNET = "f"       # 来自网络
    OTHER = "g"          # 其他
    FILM = "h"           # 影视
    POETRY = "i"         # 诗词
    NETEASE_MUSIC = "j"  # 网易云
    PHILOSOPHY = "k"     # 哲学
    FUNNY = "l"          # 抖机灵


class JoinHitokoto(Plugin):
    name = "进服一言"
    author = "机入"
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
            "一言分类": "NETEASE_MUSIC",
            "等待时间": 10,
            "分类说明": "可选: ANIMATION(动画), COMIC(漫画), GAME(游戏), LITERATURE(文学), ORIGINAL(原创), INTERNET(来自网络), OTHER(其他), FILM(影视), POETRY(诗词), NETEASE_MUSIC(网易云), PHILOSOPHY(哲学), FUNNY(抖机灵)",
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
            fmts.print_war(f"配置的分类 '{category}' 无效, 将使用默认分类 'NETEASE_MUSIC'")
            self.category_code = HitokotoType.NETEASE_MUSIC.value
        else:
            self.category_code = HitokotoType[category].value
            fmts.print_suc(f"一言分类已设置为: {category}")

    @utils.thread_func("一言")
    def on_player_join(self, player: Player):
        playername = player.name
        try:
            time.sleep(self.cfg["等待时间"])  # 等待玩家完全进入
            data = requests.get(
                f"https://v1.hitokoto.cn",
                params={
                    "c": self.category_code,
                    "encode": "text",
                },
                timeout=10,
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


entry = plugin_entry(JoinHitokoto)
