from typing import Dict

from tooldelta import plugin_entry, Plugin, ToolDelta, TYPE_CHECKING, utils, Player
from tooldelta.constants import PacketIDS

from guild.matchers import ItemNameMatcher
from guild.handlers import handlers
from guild.handlers_quick import handlers_quick
from guild.logic import logic_functions
from guild.control import GuildManager
from guild.config import Config



# FIRE 公会插件主类 FIRE
class GuildPlugin(Plugin):
    name = "公会系统"
    author = "星林 & 夏至"
    version = (0, 1, 0)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)

        self.guilds_file = self.format_data_path("公会数据文件.json")
        self.guild_manager = GuildManager(self.guilds_file)
        self.guild_chat_mode: Dict[str, bool] = {}
        self.item_matcher = ItemNameMatcher() 
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.exp_thread = utils.createThread(self.guild_exp_task, usage="公会经验增加任务")
        self.online_thread = utils.createThread(self.update_online_task, usage="在线状态更新任务")

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.xuidm = self.GetPluginAPI("XUID获取")

        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_玩家XUID获取 import XUIDGetter

            self.chatbar: ChatbarMenu
            self.xuidm: XUIDGetter
    
    def on_inject(self):
        self.game_ctrl.sendwocmd(f"/scoreboard objectives add {Config.GUILD_SCOREBOARD} dummy 积分")
        self.game_ctrl.sendwocmd(f"/scoreboard players add @a {Config.GUILD_SCOREBOARD} 0")
        trigger_configs = [
            {
                "commands": ["公会", "guild"],
                "args": [("", str, "")],
                "description": "公会系统指令",
                "callback": self.guild_menu_cb,
            },
            {
                "commands": ["gc", "公会聊天"],
                "args": [("message", str, "")],
                "description": "公会聊天频道",
                "callback": self.guild_chat_cb,
            },
            {
                "commands": ["公会仓库", "仓库"],
                "args": [("", str, "")],
                "description": "公会仓库系统",
                "callback": self.quick_vault_menu,
            },
            {
                "commands": ["仓库出售", "出售"],
                "args": [("item_id", str, ""), ("count", int, 1), ("price", int, 0)],
                "description": "快速出售物品到仓库",
                "callback": self.quick_vault_sell,
            },
            {
                "commands": ["自定义出售"],
                "args": [("item_id", str, ""), ("count", int, 1), ("price", int, 0)],
                "description": "自定义价格出售物品到仓库",
                "callback": self.custom_vault_sell,
            },
            {
                "commands": ["物品列表", "支持物品"],
                "args": [("", str, "")],
                "description": "查看支持的物品名称列表",
                "callback": self.show_item_list,
            },
            {
                "commands": ["清理公会数据"],
                "args": [("confirm", str, "")],
                "description": "清理所有公会数据 (管理员专用)",
                "callback": self.admin_clear_guild_data,
            },
            {
                "commands": ["公会据点", "据点"],
                "args": [("action", str, "")],
                "description": "公会据点操作 (tp/set)",
                "callback": self.quick_base_action,
            },
            {
                "commands": ["调试公会菜单"],
                "args": [("", str, "")],
                "description": "调试公会菜单显示问题",
                "callback": self.debug_guild_menu,
            },
            {
                "commands": ["调试据点功能"],
                "args": [("", str, "")],
                "description": "调试据点功能问题",
                "callback": self.debug_base_function,
            },
        ]

        # 注册数据更新菜单
        self.frame.add_console_cmd_trigger(
            ["更新公会数据"],
            "","更新由于版本更新导致的数据丢失",
            self.guild_update_data
        )
        for trigger in trigger_configs:
            self.chatbar.add_new_trigger(
                trigger["commands"],
                trigger["args"],
                trigger["description"],
                trigger["callback"],
            )

        self.ListenPacket(PacketIDS.IDText, self.on_chat_packet)
        self.ListenPacket(PacketIDS.IDPlayerAction, self.on_player_action)

    def on_player_join(self, player: Player):
        _ = player.name
        self.game_ctrl.sendcmd(f"/scoreboard players add @a {Config.GUILD_SCOREBOARD} 0")

for name, func in {**handlers, **handlers_quick, **logic_functions}.items():
    setattr(GuildPlugin, name, func)


entry = plugin_entry(GuildPlugin)