import os
from pathlib import Path
from tooldelta.utils import fmts
from .conversion import python_to_lua_table
from .user_data import UserData
from .safe import SafeDict
from .omega_sub_modules import Storage, Cmds, Players, Listen, System, BotAction, AsyncHttp, Cqhttp, Flex, Share, Websocket, Menu, StoragePath, Builder, Common, BotUq

class OmegaInfo:
    def __init__(self, name):
        self.name = name

class Omega:
    def __init__(self, control, lua_runtime, plugin_config):
        # 模块配置
        self.control = control
        self.event_cbs = self.control.event_cbs
        self.frame = self.control.frame
        self.packet_handler = self.frame.packet_handler
        self.lua_runtime = lua_runtime
        self.game_ctrl = self.control.game_ctrl
        self.players = self.control.players
        self.game_data_handler = self.control.game_data_handler
        self.chatbar = self.control.chatbar
        self.world_interactive = self.control.world_interactive
        # 路径配置
        self.storage_dir_path = self.control.storage_dir_path
        self.config_dir_path = self.control.config_dir_path
        self.framework_config_file_path = self.control.framework_config_file_path
        self.cache_dir_path = self.control.cache_dir_path
        self.code_dir_path = self.control.code_dir_path
        self.data_dir_path = self.control.data_dir_path
        self.log_dir_path = self.control.log_dir_path
        self.framework_config = self.control.framework_config
        self.terminal_module_config = self.control.terminal_module_config
        # 插件配置
        self.plugin_config = plugin_config
        self.info = OmegaInfo(name = self.plugin_config.name)
        self.config = UserData(SafeDict(self.plugin_config.to_json()["配置"]), self.lua_runtime)
        self.fmts_header = fmts.colormode_replace(f"§f {self.plugin_config.name} ", 7) + " "
        # 子模块
        self.storage = Storage(self)
        self.cmds = Cmds(self)
        self.players = Players(self)
        self.listen = Listen(self)
        self.system = System(self)
        self.bot_action = BotAction(self)
        self.async_http = AsyncHttp(self)
        self.cqhttp = Cqhttp(self)
        self.flex = Flex(self)
        self.share = Share(self)
        self.websocket = Websocket(self)
        self.menu = Menu(self)
        self.storage_path = StoragePath(self)
        self.builder = Builder(self)
        self.common = Common(self)
        self.botUq = BotUq(self)

    def user_data_to_lua_value(self, ud):
        return python_to_lua_table(ud, self.lua_runtime)