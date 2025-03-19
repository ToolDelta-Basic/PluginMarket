import threading
from tooldelta import Plugin, utils, plugin_entry
from tooldelta.constants import PacketIDS


class XUIDGetter(Plugin):
    name = "前置-玩家XUID获取"
    author = "System"
    version = (0, 0, 6)
    inject_signal = False

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_pkt)
        self.map_init_event = threading.Event()
    def on_inject(self):
        self.map = {k: v[-8:] for k, v in self.game_ctrl.players_uuid.copy().items()}
        self.cached_playernames: dict[str, int] = {}
        self.inject_signal = True
        self.frame.add_console_cmd_trigger(
            ["xuids"], None, "查看在线玩家的 XUID 列表", self.on_lookup_xuids
        )
        for k, v in self.get_map().items():
            self.record_player_xuid(k, v[-8:])
        self.map_init_event.set()

    def on_lookup_xuids(self, _):
        for k, v in self.get_map().items():
            print(f"{k}: {v}")

    def get_map(self):
        if not self.inject_signal:
            return {k: v[-8:] for k, v in self.game_ctrl.players_uuid.copy().items()}
        return self.map

    @utils.thread_func("处理玩家 XUID")
    def on_pkt(self, pk):
        self.map_init_event.wait()
        is_joining = not pk["ActionType"]
        for entry in pk["Entries"]:
            playername = entry["Username"]
            xuid = entry.get("XUID")
            if len(xuid) > 8:
                raise ValueError(f"Not valid XUID: {xuid}")
            uuid = entry["UUID"]
            if is_joining:
                self.map[playername] = xuid
                self.record_player_xuid(playername, xuid)
            else:
                playername = {v: k for k, v in self.map.items()}[uuid[-8:]]
                if playername in self.map.values():
                    self.cached_playernames[playername] = 4
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

    @utils.timer_event(20, "XUID缓存区")
    def cache_clean(self):
        # 因为玩家退出后的瞬间仍有插件会使用此玩家的 XUID
        # 所以需要将退出玩家的 XUID 存留一段时间
        for k, v in self.cached_playernames.copy().items():
            if v == 0:
                del self.cached_playernames[k]
                del self.map[k]
            else:
                self.cached_playernames[k] = v - 1


entry = plugin_entry(XUIDGetter, "XUID获取")
