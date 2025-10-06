"""插件配置加载器"""

from tooldelta import cfg, fmts, TYPE_CHECKING
from typing import ClassVar, Any
import os

if TYPE_CHECKING:
    from .__init__ import SchematicLoader


class Config:
    CONFIG_DEFAULT: ClassVar[dict[str, Any]] = {
        "是否导入空气方块": True,
        "导入速度(方块/秒)": 5000,
    }
    CONFIG_STD: ClassVar[dict[str, Any]] = {
        "是否导入空气方块": bool,
        "导入速度(方块/秒)": cfg.PInt,
    }

    def __init__(self, plugin: "SchematicLoader"):
        self.name = plugin.name
        self.version = plugin.version

    def load_config(self):
        try:
            self.config, _ = cfg.get_plugin_config_and_version(
                self.name,
                self.CONFIG_STD,
                self.CONFIG_DEFAULT,
                self.version,
            )
            self.get_parsed_config()
        except cfg.ConfigKeyError as error:
            fmts.print_inf(
                f"§e<schematic导入器> §6警告：发现插件配置文件中有{error},这可能是因为插件本体已更新而插件配置文件未更新,已自动替换为新版配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()
        except cfg.ConfigValueError as error:
            fmts.print_inf(
                f"§e<schematic导入器> §c警告：发现插件配置文件中有{error},请检查您是否删除或新增了某些配置项的内容导致类型检查不通过,已自动替换为初始配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()

    def get_parsed_config(self):
        config = self.config
        self.INCLUDE_AIR: bool = config["是否导入空气方块"]
        self.LOAD_SPEED: int = config["导入速度(方块/秒)"]
