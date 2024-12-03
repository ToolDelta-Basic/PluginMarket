from tooldelta import Plugin, plugins, Utils
from tooldelta.constants import PacketIDS


@plugins.add_plugin_as_api("XUID获取")
class XUIDGetter(Plugin):
    name = "前置-玩家XUID获取"
    author = "System"
    version = (0, 0, 1)

    inject_signal = False

    def on_inject(self):
        path = self.format_data_path("xuids.json")
        Utils.TMPJson.loadPathJson(path, needFileExists=False)
        if Utils.TMPJson.read(path) is None:
            Utils.TMPJson.write(path, {})
        self.map = self.game_ctrl.players_uuid.copy()
        self.inject_signal = True

    def get_map(self):
        if not self.inject_signal:
            return self.game_ctrl.players_uuid.copy()
        return self.map

    def on_frame_exit(self):
        Utils.TMPJson.unloadPathJson(self.format_data_path("xuids.json"))

    @plugins.add_packet_listener(PacketIDS.IDPlayerList)
    def on_pkt(self, pk):
        is_joining = not pk["ActionType"]
        for entry in pk["Entries"]:
            playername = entry["Username"]
            xuid = entry.get("XUID")
            if is_joining:
                self.map[playername] = xuid
                self.record_player_xuid(playername, xuid)
            else:
                del self.map[playername]
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
        map = self.get_map()
        if playername in map.keys():
            return map[playername]
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
        map = self.get_map()
        if xuid in map.values():
            return {v: k for k, v in map.items()}[xuid]
        if allow_offline:
            return self.get_name_by_xuid_offline(xuid)
        else:
            raise ValueError(f"无法通过XUID {xuid} 获取玩家名")

    def get_name_by_xuid_offline(self, xuid: str):
        path = self.format_data_path("xuids.json")
        c = Utils.TMPJson.read(path)
        try:
            return c[xuid]
        except KeyError:
            raise ValueError(f"未曾记录XUID {xuid}")

    def get_xuid_by_name_offline(self, playername: str):
        path = self.format_data_path("xuids.json")
        c = Utils.TMPJson.read(path)
        if playername not in c.values():
            raise ValueError(f"未曾记录玩家 {playername} 的XUID")
        return {v: k for k, v in c.items()}[playername]

    def record_player_xuid(self, playername: str, xuid: str):
        path = self.format_data_path("xuids.json")
        c = Utils.TMPJson.read(path)
        c[xuid] = playername
        Utils.TMPJson.write(path, c)
