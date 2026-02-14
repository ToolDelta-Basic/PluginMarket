from tooldelta import Plugin, plugin_entry, cfg
from .config import CONFIG_DEFAULT, CONFIG_STD
from .core import Core
from .agent import AIAgent
from .permission import PermissionManager
from .tool_logger import ToolLogger
from . import utils
# Author 3340903371 定制插件dd

class MCAgent(Plugin):
    name = "MCAgent"
    author = "果_k"
    version = (1, 0, 0)

    def __init__(self, frame):
        """Initialize MCAgent plugin."""
        super().__init__(frame)
        self.players = self.game_ctrl.players
        self.ListenPreload(self.on_def)
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.config = config
        self.whitelist = config["白名单"]
        self.full_permission_whitelist = config.get("完全权限白名单", [])
        self.level1_permission_whitelist = config.get("一级权限白名单", [])
        self.dangerous_commands = config.get("危险命令列表", ["/op", "/deop", "op ", "deop ", "stop"])
        self.Info = config["Info"]
        self.ui_texts = config["UI文本"]
        self.agent_config = config["AI配置"]
        self.utils = utils.Utils(self)
        self.permission_manager = PermissionManager(self)
        self.tool_logger = ToolLogger(self)
        self.core = Core(self)
        self.agent = AIAgent(self)

    def on_def(self):
        """Register chatbar menu triggers."""
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        
        always_registered = [
            ([ "助手", "ai"], ..., "MC Agent(支持工具调用)", self.core.AIAssistant),
            (["清除对话", "clear"], [], "清除AI对话历史", self.core.ClearChat),
            (["退出助手", "取消", "cancel"], [], "取消当前AI请求", self.core.CancelAI),
        ]
        
        for trigger in always_registered:
            self.chatbar.add_new_trigger(*trigger)
    
    def get_core(self):
        return self.core
    
    def get_agent(self):
        return self.agent
    
    def get_utils(self):
        return utils

entry = plugin_entry(MCAgent, "GetMCAgentAPI", (1, 0, 0))
