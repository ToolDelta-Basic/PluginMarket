"""插件配置加载器"""

from tooldelta import cfg, fmts, TYPE_CHECKING
from typing import ClassVar, Any
import os

if TYPE_CHECKING:
    from .__init__ import MCStructureLoader


class Config:
    CONFIG_DEFAULT: ClassVar[dict[str, Any]] = {
        "是否导入空气方块": True,
        "是否导入命令": True,
        "方块导入速度(方块/秒)": 5000,
        "命令导入速度(命令/秒)": 5,
        "命令模式(0:控制台命令;1:魔法指令)": 1,
    }
    CONFIG_STD: ClassVar[dict[str, Any]] = {
        "是否导入空气方块": bool,
        "是否导入命令": bool,
        "方块导入速度(方块/秒)": cfg.PInt,
        "命令导入速度(命令/秒)": cfg.PInt,
        "命令模式(0:控制台命令;1:魔法指令)": int,
    }

    def __init__(self, plugin: "MCStructureLoader") -> None:
        self.name = plugin.name
        self.version = plugin.version

    def load_config(self) -> None:
        try:
            self.config, _ = cfg.get_plugin_config_and_version(
                self.name,
                self.CONFIG_STD,
                self.CONFIG_DEFAULT,
                self.version,
            )
            self.get_parsed_config()
            self.check_config()
        except cfg.ConfigKeyError as error:
            fmts.print_inf(
                f"§e<mcstructure导入器> §6警告: 发现插件配置文件中有{error},这可能是因为插件本体已更新而插件配置文件未更新,已自动替换为新版配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()
        except cfg.ConfigValueError as error:
            fmts.print_inf(
                f"§e<mcstructure导入器> §c警告: 发现插件配置文件中有{error},请检查您是否删除或新增了某些配置项的内容导致类型检查不通过,已自动替换为初始配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()

    def get_parsed_config(self) -> None:
        config = self.config
        self.INCLUDE_AIR: bool = config["是否导入空气方块"]
        self.INCLUDE_CMD: bool = config["是否导入命令"]
        self.BLOCK_LOAD_SPEED: int = config["方块导入速度(方块/秒)"]
        self.CMD_LOAD_SPEED: int = config["命令导入速度(命令/秒)"]
        self.CMD_MODE: int = config["命令模式(0:控制台命令;1:魔法指令)"]

    def check_config(self) -> None:
        if self.CMD_MODE not in (0, 1):
            fmts.print_inf(
                "§e<mcstructure导入器> §6警告: 您填写的命令模式有误, 已切换为 <魔法指令>"
            )
            self.config["命令模式(0:控制台命令;1:魔法指令)"] = 1
            cfg.upgrade_plugin_config(self.name, self.config, self.version)
