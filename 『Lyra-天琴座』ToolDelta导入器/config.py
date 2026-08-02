"""『Lyra-天琴座』配置文件"""

import os
from typing import TYPE_CHECKING, Any, ClassVar

from tooldelta import cfg, fmts

if TYPE_CHECKING:
    from .__init__ import LyraSystem


class Config:
    CONFIG_DEFAULT: ClassVar[dict[str, Any]] = {
        "控制台导入器触发词": ["导入", "load"],
        "是否导入空气方块": True,
        "是否导入命令": True,
        "方块导入速度(方块/秒)": 1000,
        "命令导入速度(命令/秒)": 3,
    }
    CONFIG_STD: ClassVar[dict[str, Any]] = {
        "控制台导入器触发词": cfg.JsonList(str, -1),
        "是否导入空气方块": bool,
        "是否导入命令": bool,
        "方块导入速度(方块/秒)": cfg.PNumber,
        "命令导入速度(命令/秒)": cfg.PNumber,
    }

    def __init__(self, plugin: "LyraSystem") -> None:
        self.name = plugin.name
        self.version = plugin.version
        self.config_path = os.path.join("插件配置文件", f"{self.name}.json")
        self.config_old = os.path.join("插件配置文件", f"old_{self.name}.json")

    def load_config(self) -> None:
        try:
            self.config, _ = cfg.get_plugin_config_and_version(
                self.name, self.CONFIG_STD, self.CONFIG_DEFAULT, self.version
            )
        except (cfg.ConfigKeyError, cfg.ConfigValueError) as error:
            fmts.print_inf(
                f"§6❀ 警告: 『Lyra-天琴座』旧配置与新版不兼容: {error}, 已备份并重建"
            )
            if os.path.exists(self.config_old):
                os.remove(self.config_old)
            os.replace(self.config_path, self.config_old)
            self.load_config()
            return
        self.CONSOLE_TRIGGERS = list(self.config["控制台导入器触发词"])
        self.INCLUDE_AIR = bool(self.config["是否导入空气方块"])
        self.INCLUDE_CMD = bool(self.config["是否导入命令"])
        self.BLOCK_LOAD_SPEED = float(self.config["方块导入速度(方块/秒)"])
        self.CMD_LOAD_SPEED = float(self.config["命令导入速度(命令/秒)"])
        self.LOAD_SPEED = self.BLOCK_LOAD_SPEED
