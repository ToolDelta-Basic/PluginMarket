"""```
『Orion System 猎户座』违规与作弊行为综合反制系统
╔════════════════════════════════════════════════════════════╗
║    ██████╗     ██████╗     ██╗     ██████╗     ██╗   ██╗   ║
║   ██╔═══██╗    ██   ██╗    ██║    ██╔═══██╗    ███╗  ██║   ║
║   ██║   ██║    ██   ██║    ██║    ██║   ██║    ████╗ ██║   ║
║   ██║   ██║    ██████╔╝    ██║    ██║   ██║    ██╔██╗██║   ║
║   ██║   ██║    ██╔██═╝     ██║    ██║   ██║    ██║ ████║   ║
║   ██║   ██║    ██║ ██╗     ██║    ██║   ██║    ██║  ███║   ║
║   ╚██████╔╝    ██║  ██╗    ██║    ╚██████╔╝    ██║   ██║   ║
║    ╚═════╝     ╚═╝  ╚═╝    ╚═╝     ╚═════╝     ╚═╝   ╚═╝   ║
╚════════════════════════════════════════════════════════════╝
```"""

from tooldelta import Plugin, fmts, plugin_entry, TYPE_CHECKING
from threading import Lock
import os
from importlib import reload

import config
import core
import ban_system
import ban_utils

reload(config)
reload(core)
reload(ban_system)
reload(ban_utils)


class Orion_System(Plugin):
    """插件主类"""

    name = "『Orion System』违规与作弊行为综合反制系统"
    author = "style_天枢『猎户座』"
    version = (0, 3, 2)

    def __init__(self, frame) -> None:
        """
        初始化插件
        Args:
            frame (ToolDelta): ToolDelta框架
        """
        super().__init__(frame)
        self.config_mgr = config.OrionConfig(self)
        self.utils = ban_utils.OrionUtils(self)
        self.config_mgr.load_config()
        self.config_mgr.upgrade_plugin_data()
        self.create_lock()
        self.create_dir()
        self.core = core.OrionCore(self)
        self.ban_system = ban_system.BanSystem(self)
        server_number = self.frame.launcher.serverNumber
        if (
            self.config_mgr.load_in_trial_server is False
            and server_number in self.config_mgr.trial_server_list
        ):
            fmts.print_inf(f"§b发现本服({server_number})为测试服，猎户座将不会启动")
            return
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.core.entry()

    def on_preload(self) -> None:
        """插件加载完成后调用此方法"""
        self.xuid_getter = self.GetPluginAPI("XUID获取")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        # 进行类型检查
        if TYPE_CHECKING:
            from 前置_玩家XUID获取 import XUIDGetter
            from 前置_聊天栏菜单 import ChatbarMenu

            self.xuid_getter: XUIDGetter
            self.chatbar: ChatbarMenu

    def on_active(self) -> None:
        """机器人进入租赁服后调用此方法"""
        self.utils.print_inf(self.config_mgr.info_top_message)
        self.ban_system.entry()
        self.core.active_entry()

    def create_lock(self) -> None:
        """创建插件需要的线程锁"""
        # 这是获取玩家设备号函数的线程锁，要求当多个玩家连续登录时逐个获取设备号，而不是连续tp最后啥也没得到
        # 当连续多个玩家进入游戏后，只允许一个线程获取device_id，其他获取device_id的线程处于等待状态，直到获取到当前玩家设备号或超时后再执行下一个线程
        self.lock_get_device_id = Lock()
        # 这是玩家封禁函数的线程锁，要求在封禁玩家时如果有相同路径读取操作时逐一读取磁盘，防止出现冲突或报错
        self.lock_ban_xuid = Lock()
        self.lock_ban_device_id = Lock()
        # 这是用于刷新“检测发言频率”和“检测重复刷屏”缓存的计时器的线程锁，防止异步资源访问时出现冲突
        self.lock_timer = Lock()

    def create_dir(self) -> None:
        """创建插件需要的目录和依赖文件"""
        os.makedirs(f"{self.data_path}/{self.config_mgr.xuid_dir}", exist_ok=True)
        os.makedirs(f"{self.data_path}/{self.config_mgr.device_id_dir}", exist_ok=True)
        player_data_path = f"{self.data_path}/{self.config_mgr.player_data_file}"
        if not os.path.exists(player_data_path):
            ban_utils.OrionUtils.disk_write(player_data_path, {})


entry = plugin_entry(Orion_System, "Orion_System")
