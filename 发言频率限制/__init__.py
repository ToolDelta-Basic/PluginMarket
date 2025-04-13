import time
from tooldelta import ToolDelta, cfg, Chat, Player, Plugin, plugin_entry, TYPE_CHECKING


class ChatFreqLimit(Plugin):
    name = "发言频率限制v1"
    author = "wling/7912"
    version = (0, 0, 6)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        STD_BAN_CFG = {"时间内": int, "在时间内达到多少条": int}
        DEFAULT_BAN_CFG = {
            "时间内": 3,
            "在时间内达到多少条": 6,
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, STD_BAN_CFG, DEFAULT_BAN_CFG, self.version
        )
        self.playerMsgTimeDict = {}
        self.msgSendNunMaxPerTime = self.cfg["时间内"]
        self.msgSendNumMax = self.cfg["在时间内达到多少条"]
        self.ListenPreload(self.on_preload)
        self.ListenChat(self.on_chat)
        self.ListenPlayerLeave(self.on_player_leave)

    def on_preload(self):
        ban_plugin = self.GetPluginAPI("封禁系统")
        if TYPE_CHECKING:
            from 封禁系统 import BanSystem

            ban_plugin = self.get_typecheck_plugin_api(BanSystem)
        self.ban = ban_plugin.ban

    def on_chat(self, chat: Chat):
        playername = chat.player.name
        if not chat.player.is_op():
            msgSendTime = time.time()
            if playername not in self.playerMsgTimeDict:
                self.playerMsgTimeDict[playername] = []
            for i in self.playerMsgTimeDict[playername][:]:
                if i <= msgSendTime - self.msgSendNunMaxPerTime:
                    self.playerMsgTimeDict[playername].remove(i)
            self.playerMsgTimeDict[playername].append(msgSendTime)
            if len(self.playerMsgTimeDict[playername]) >= self.msgSendNumMax:
                # 生成时间戳，比现在多五分钟，传参给
                # ban(playername, int(time.time()) + 300, "发信息过快")
                self.ban(playername, int(time.time()) + 300, "发信息过快")
                self.playerMsgTimeDict[playername] = []

    def on_player_leave(self, player: Player):
        if player.name in self.playerMsgTimeDict:
            del self.playerMsgTimeDict[player.name]


entry = plugin_entry(ChatFreqLimit)
