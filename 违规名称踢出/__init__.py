from tooldelta import (
    constants,
    ToolDelta,
    Plugin,
    cfg,
    Chat,
    Player,
    plugin_entry,
)
import requests
from tooldelta.plugin_market import url_join
from tooldelta.utils.tempjson import load_and_read
class kill(Plugin):
    version = (0, 0, 10)
    name = "违规名称踢出"
    author = "大庆油田"
    description = "简单的违规名称踢出"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.make_data_path()
        CFG_STD = {
            cfg.KeyGroup("包含以下字样的玩家将被踢出"): cfg.JsonList(str),
            "原因": str,
            "是否使用云词库":bool
        }
        CFG_DEFAULT = {
            "包含以下字样的玩家将被踢出": ["木合塔尔", "NO"],
            "原因": "",
            "是否使用云词库":True
        }
        self.cfg, V = cfg.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )
        self.ci = self.cfg.get("包含以下字样的玩家将被踢出", [])
        self.ci.extend(self.cfg.get("踢出词", []))
        if self.cfg.get("是否使用云词库",True):
            self.print("开始获取远程违禁名称")
            try:
                url = cfg.get_cfg(
                "ToolDelta基本配置.json", {"插件市场源": str}
            )["插件市场源"]
                url = url_join(url,"违规名称踢出/词库.json")
                r = requests.get(url).json()
            except:
                print("获取远程词库失败，将尝试使用本地词库")
                r= load_and_read("插件文件/ToolDelta类式插件/违规名称踢出/词库.json",True,1,[])
            self.ci.extend(r)
        self.yy = self.cfg["原因"]
        self.ListenPacket(constants.PacketIDS.PlayerList, self.on_prejoin)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenChat(self.on_player_message)

    def on_active(self):
        for player in self.frame.get_players().getAllPlayers():
            self.on_player_join(player)

    def on_prejoin(self, pk: dict):
        is_joining = not pk["ActionType"]
        if is_joining:
            for entry_user in pk["Entries"]:
                player = entry_user["Username"]
                xuid = entry_user["XUID"]
                for a in self.ci:
                    if a in player:
                        self.print(f"§c 玩家名 {player} 包含关键字 {a}, 已被踢出")
                        self.game_ctrl.sendwocmd(f"kick {xuid} {self.yy}")
        return False

    def killpl(self, player: str, xuid: str):
        for a in self.ci:
            if a in player:
                self.game_ctrl.sendwocmd(f"kick {xuid} {self.yy}")

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        xuid = chat.player.xuid

        self.killpl(player, xuid)

    def on_player_join(self, playerf: Player):
        player = playerf.name
        xuid = playerf.xuid
        self.killpl(player, xuid)


entry = plugin_entry(kill)
