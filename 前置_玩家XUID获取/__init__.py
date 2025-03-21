from tooldelta import Plugin, utils, plugin_entry
from tooldelta.constants import PacketIDS


class XUIDGetter(Plugin):
    name = "前置-玩家XUID获取"
    author = "System"
    version = (0, 0, 7)
    inject_signal = False

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_pkt)
        self.player_2_xuid_map: dict[str, str] = {}

    def on_inject(self):
        self.update_map()
        self.inject_signal = True
        self.frame.add_console_cmd_trigger(
            ["xuids"], None, "查看在线玩家的 XUID 列表", self.on_lookup_xuids
        )
        for k, v in self.get_map().items():
            self.record_player_xuid(k, v[-8:])

    def on_lookup_xuids(self, _):
        for k, v in self.get_map().items():
            self.print(f"{k}: {v}")

    def get_map(self):
        if not self.inject_signal:
            self.update_map()
        return self.player_2_xuid_map

    def update_map(self):
        self.player_2_xuid_map.update(
            {
                player.name: player.xuid
                for player in self.frame.get_players().getAllPlayers()
            }
        )

    @utils.thread_func("处理玩家 XUID")
    def on_pkt(self, pk):
        # 在登录前就获取 XUID
        is_joining = not pk["ActionType"]
        for entry in pk["Entries"]:
            playername = entry["Username"]
            xuid = entry.get("XUID")
            if len(xuid) > 8:
                raise ValueError(f"Not valid XUID: {xuid}")
            if is_joining:
                self.player_2_xuid_map[playername] = xuid
                self.record_player_xuid(playername, xuid)
        return False

    def get_xuid_by_name(self, playername: str, allow_offline=False):
        """
        通过玩家名获取 XUID.
        Args:
            playername (str): 玩家名
            allow_offline (bool, optional): 是否允许搜索离线玩家, 默认为否.
        Raises:
            ValueError: 无法获取玩家的 XUID
        Returns:
            str: 玩家 XUID
        """
        if playername in self.player_2_xuid_map.keys():
            return self.player_2_xuid_map[playername]
        if allow_offline:
            return self.get_xuid_by_name_offline(playername)
        else:
            raise ValueError(f"无法获取 {playername} 的XUID")

    def get_name_by_xuid(self, xuid: str, allow_offline=False):
        """
        通过 XUID 获取玩家名.
        Args:
            xuid (str): XUID
            allow_offline (bool, optional): 是否允许搜索离线玩家, 默认为否.
        Raises:
            ValueError: 无法获取玩家名
        Returns:
            str: 玩家名
        """
        if xuid in self.player_2_xuid_map.values():
            return {v: k for k, v in self.player_2_xuid_map.items()}[xuid]
        if allow_offline:
            return self.get_name_by_xuid_offline(xuid)
        else:
            raise ValueError(f"无法通过XUID {xuid} 获取玩家名")

    def get_name_by_xuid_offline(self, xuid: str):
        path = self.format_data_path("xuids.json")
        c = utils.tempjson.load_and_read(path, need_file_exists=False, default={})
        try:
            return c[xuid]
        except KeyError:
            raise ValueError(f"未曾记录XUID {xuid}")

    def get_xuid_by_name_offline(self, playername: str):
        path = self.format_data_path("xuids.json")
        c = utils.tempjson.load_and_read(path, need_file_exists=False, default={})
        if playername not in c.values():
            raise ValueError(f"未曾记录玩家 {playername} 的XUID")
        return {v: k for k, v in c.items()}[playername]

    def record_player_xuid(self, playername: str, xuid: str):
        path = self.format_data_path("xuids.json")
        c = utils.tempjson.load_and_read(path, need_file_exists=False, default={})
        c[xuid] = playername
        utils.tempjson.load_and_write(path, c, need_file_exists=False)


entry = plugin_entry(XUIDGetter, "XUID获取")
