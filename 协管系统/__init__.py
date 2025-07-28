from tooldelta import Plugin, plugin_entry, cfg
from tooldelta.constants import PacketIDS

from .config import CONFIG_DEFAULT, CONFIG_STD
from .core import Core
from .deepseek import DeepSeek

class Auxiliary(Plugin):
    name = "协管系统"
    author = "果_k"
    version = (0, 0, 5)

    def __init__(self, frame):
        super().__init__(frame)
        self.players = self.game_ctrl.players
        self.ListenPreload(self.on_def)
        
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.config = config
        self.GMlist = config["协管名单"]
        self.Info = config["Info"]
        self.NO_CMDsend = config["命令转发禁用关键词"]
        self.Focus = config["快捷功能"]
        self.online_time_scoreboard = config["在线时间计分板"]
        self.RandomRemark = config["随机插话"]
        self.SetDeepOSeek = config["SetDeepOSeek"]
        self.SetDeepSeek = config["SetDeepSeek"]
        
        # 初始化功能模块
        self.core = Core(self)
        self.deepseek = DeepSeek(self)

        #监听数据包与注册
        if config.get("随机插话是否启用", False):
            self.ListenPacket(PacketIDS.Text, self.deepseek.RandomRemark)
    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.deepseek.conversations_O.clear()  # 清除所有的历史对话
        # 固定注册
        always_registered = [
            (["协管系统"], [], "协管系统", self.core.GMmenu),
            (["快捷功能"], ..., "触发词后加对应功能数字可快速选择", self.core.GM_focus),
        ]
        # 按条件配置注册
        conditional_registered = [
            # 格式为 "开关配置名 [触发词] 参数 描述 处理函数"
            ("命令转发是否启用", ["命令转发", "转发"], ..., "命令转发", self.core.CMDpost),
            ("伪魔法指令DeepSeek是否启用", ["DeepOSeek", "dos"], ..., "DeepOSeek", self.deepseek.DeepOSeek),
            ("协管名单是否启用", ["协管名单"], [], "查看所有协管名称", self.core.GMuser),
            ("DeepSeek", ["DeepSeek", "ds"], ..., "DeepSeek", self.deepseek.DeepSeek),
        ]
        for trigger in always_registered:
            self.chatbar.add_new_trigger(*trigger)

        for config_key, *trigger_info in conditional_registered:
            if self.config[config_key]:
                self.chatbar.add_new_trigger(*trigger_info)
    
entry = plugin_entry(Auxiliary)