import subprocess
import threading
from io import BytesIO
from typing import Any, Callable
from .chest_cache import ChestCache
from tooldelta import Plugin
from tooldelta import cfg as config
from tooldelta.utils import tempjson


class FlowersForMachineBase:
    plugin: Plugin

    server_started: bool
    server_start_time: int
    server: subprocess.Popen[bytes] | None

    should_close: bool
    running_mutex: threading.Lock

    bwo: Any | None
    nbt_marshal: Callable[[BytesIO, Any, str], None] | None
    chest_cache: ChestCache

    def __init__(self, plugin: Plugin):
        self.plugin = plugin

        CFG_DEFAULT = {
            "验证服务地址": "",
            "验证服务令牌": "",
            "租赁服号": "",
            "租赁服密码": "",
            "我已经修改了操作台坐标": False,
            "我已经阅读了版本 v2 自述": False,
            "操作台所在维度 ID": 0,
            "操作台中心 X 轴坐标": 0,
            "操作台中心 Y 轴坐标": 0,
            "操作台中心 Z 轴坐标": 0,
            "本地服务器端口号": 8080,
        }
        cfg, _ = config.get_plugin_config_and_version(
            "献给机械の花束",
            config.auto_to_std(CFG_DEFAULT),
            CFG_DEFAULT,
            self.plugin.version,
        )

        self.asa = str(cfg["验证服务地址"])
        self.ast = str(cfg["验证服务令牌"])
        self.rsn = str(cfg["租赁服号"])
        self.rsp = str(cfg["租赁服密码"])
        self.set_console_pos = bool(cfg["我已经修改了操作台坐标"])
        self.read_v1_readme = bool(cfg["我已经阅读了版本 v2 自述"])
        self.cdi = int(cfg["操作台所在维度 ID"])
        self.ccx = int(cfg["操作台中心 X 轴坐标"])
        self.ccy = int(cfg["操作台中心 Y 轴坐标"])
        self.ccz = int(cfg["操作台中心 Z 轴坐标"])
        self.ssp = int(cfg["本地服务器端口号"])

        self.server_started = False
        self.server_start_time = 0
        self.server = None

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.bwo = None
        self.nbt_marshal = None
        self.chest_cache = ChestCache()

        self.plugin.make_data_path()

    def need_upgrade_bwo(self) -> bool:
        version_path = self.plugin.format_data_path("bwo_version.json")
        loaded_dict = tempjson.load_and_read(
            version_path, need_file_exists=False, default={}
        )
        if "version" not in loaded_dict:
            return True
        if loaded_dict["version"] != "1.3.1":
            return True
        return False

    def save_bwo_version(self):
        version_path = self.plugin.format_data_path("bwo_version.json")
        tempjson.write(
            version_path,
            {"version": "1.3.1"},
        )
        tempjson.flush(version_path)

    def on_def(self):
        pip = self.plugin.GetPluginAPI("pip")

        if 0:
            from pip模块支持 import PipSupport

            pip: PipSupport
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        if self.need_upgrade_bwo():
            pip.upgrade("bedrock-world-operator")
            self.save_bwo_version()

        import bedrockworldoperator as bwo
        from bedrockworldoperator.utils.marshalNBT import MarshalPythonNBTObjectToWriter

        self.bwo = bwo
        self.nbt_marshal = MarshalPythonNBTObjectToWriter
