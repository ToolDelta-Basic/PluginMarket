"""『Lyra-天琴座』ToolDelta导入器"""

import importlib
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, cast

from tooldelta import Plugin, fmts, plugin_entry

from . import basic, config, linux_support
from .lyra_loader.common import block_converter

if TYPE_CHECKING:
    from pip模块支持 import PipSupport

MCWORLD_PACKAGE = "amulet-leveldb"
MCWORLD_PACKAGE_VERSION = "1.0.7"


class LyraSystem(Plugin):
    """『Lyra-天琴座』ToolDelta导入器"""

    name = "『Lyra-天琴座』ToolDelta导入器"
    author = "style_天枢"
    version = (0, 0, 5)

    def __init__(self, frame) -> None:
        super().__init__(frame)
        self.config_mgr = config.Config(self)
        self.config_mgr.load_config()
        self.basic_mgr = basic.Basic(self)
        self.converter: block_converter.BlockConverter
        self.command_loader: object
        self.ListenActive(self.on_active)

    def ensure_mcworld_dependency(self) -> None:
        """仅在导入 MCWorld 时确保 Mojang LevelDB 读取库可用"""
        try:
            importlib.import_module("leveldb")
            try:
                installed_version = version(MCWORLD_PACKAGE)
            except PackageNotFoundError:
                return
            if installed_version != MCWORLD_PACKAGE_VERSION:
                fmts.print_war(
                    f"检测到 {MCWORLD_PACKAGE} {installed_version}, "
                    f"Lyra已验证的版本为 {MCWORLD_PACKAGE_VERSION}；将继续使用当前版本"
                )
            return
        except ImportError:
            pass

        if sys.platform.startswith("linux"):
            if problem := linux_support.check_build_environment():
                raise RuntimeError(linux_support.dependency_error_message(problem))

        try:
            pip = cast("PipSupport", self.GetPluginAPI("pip"))
            pip.install([f"{MCWORLD_PACKAGE}=={MCWORLD_PACKAGE_VERSION}"])
        except SystemExit as error:
            if sys.platform.startswith("linux"):
                message = linux_support.dependency_error_message(
                    "pip下载或源码编译失败, 请查看上方pip输出"
                )
            else:
                message = (
                    "MCWorld依赖 amulet-leveldb 安装失败, 本次导入已取消"
                    "请检查当前Python版本与系统架构是否受支持, 以及pip网络是否可用"
                    "其他五种格式不受影响"
                )
            raise RuntimeError(message) from error
        except Exception as error:
            raise RuntimeError(
                "无法调用pip模块支持安装MCWorld依赖, 本次导入已取消"
                "其他五种格式不受影响"
            ) from error

        importlib.invalidate_caches()
        try:
            importlib.import_module("leveldb")
        except ImportError as error:
            raise RuntimeError(
                "amulet-leveldb安装完成, 但无法导入leveldb模块；"
                "请确认pip模块支持的数据目录已加入Python搜索路径"
                "本次MCWorld导入已取消, 其他五种格式不受影响"
            ) from error

    def on_active(self) -> None:
        self.converter = block_converter.BlockConverter.from_plugin(self)
        self.basic_mgr.entry()


entry = plugin_entry(LyraSystem, "『Lyra-天琴座』ToolDelta导入器")
