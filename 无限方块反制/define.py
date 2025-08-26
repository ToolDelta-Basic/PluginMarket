from io import BytesIO
from typing import Any
from collections.abc import Callable
from tooldelta import Plugin
from tooldelta import cfg as config


class AntiInfiniteBlockBase:
    plugin: Plugin

    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin

        CFG_DEFAULT = {
            "默认监测频率 (单位: 秒)": 5,
            "反制命令": [
                "title @p[r=30] actionbar 您可能在无限刷物，请文明游戏！",
                "say 有人在使用无限刷物！",
            ],
        }
        cfg, _ = config.get_plugin_config_and_version(
            "无限方块反制",
            config.auto_to_std(CFG_DEFAULT),
            CFG_DEFAULT,
            self.plugin.version,
        )

        self.repeat_time: int = int(cfg["默认监测频率 (单位: 秒)"])
        self.command_line: list[str] = list(cfg["反制命令"])

        self.nbt_unmarshal: Callable[[BytesIO], Any] | None = None

    def on_def(self):
        _ = self.plugin.GetPluginAPI("世界の记忆", (0, 1, 3))
        game_interact: "GameInteractive" = self.plugin.GetPluginAPI(
            "前置-世界交互", (2, 0, 0)
        )

        pip = self.plugin.GetPluginAPI("pip")
        if 0:
            from pip模块支持 import PipSupport
            from 前置_世界交互 import GameInteractive

            pip: PipSupport
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        from bedrockworldoperator.utils.unmarshalNBT import (
            UnMarshalBufferToPythonNBTObject,
        )

        self.nbt_unmarshal = UnMarshalBufferToPythonNBTObject
        self.game_interact = game_interact
