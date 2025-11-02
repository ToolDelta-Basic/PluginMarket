from time import time as _time
from dataclasses import dataclass, field
from tooldelta import Player, Plugin, fmts, utils, plugin_entry


def int_time():
    return int(_time())


@dataclass
class PlayerHistory:
    xuid: str
    name: str
    deviceID: str | None
    first_join: int
    last_join: int = field(default_factory=int_time)

    @classmethod
    def loads(cls, data: dict, now_join: bool = True):
        return cls(
            xuid=data["xuid"],
            name=data["name"],
            deviceID=data["deviceID"],
            first_join=data["first_join"],
            last_join=(int_time() if now_join else data["last_join"]),
        )

    @classmethod
    def load_from_player(
        cls,
        player: Player,
        first_join_time: int | None = None,
        deviceID: str | None = None,
    ):
        return cls(
            player.xuid,
            player.name,
            getattr(player, "device_id", None) or deviceID,
            first_join_time or int_time(),
        )

    def dumps(self):
        return {
            "xuid": self.xuid,
            "name": self.name,
            "deviceID": self.deviceID,
            "first_join": self.first_join,
            "last_join": self.last_join,
        }


class PlayerHistoryPlugin(Plugin):
    name = "玩家记录"
    author = "SuperScript"
    version = (0, 0, 3)
    description = "easter egg: Welcome to Zootopia!"

    def __init__(self, frame):
        super().__init__(frame)
        self._cached_player_history: dict[str, PlayerHistory] | None = {}
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.frame.add_console_cmd_trigger(
            ["history", "玩家记录"], None, "查询玩家记录", lambda args: self.on_search()
        )

    @utils.thread_func("记录玩家数据")
    def on_active(self):
        for player in self.frame.get_players().getAllPlayers():
            self.record_player(player)
        self.flush_players_history()

    def on_player_join(self, player: Player):
        self.record_player(player)
        self.flush_players_history()

    def on_search(self):
        fmts.print_inf("请输入玩家名/玩家名中的关键词")
        resp = input(fmts.fmt_info("查找玩家记录: ")).strip()
        if resp == "":
            fmts.print_inf("未输入关键词, 无法继续")
            return
        playernames = {i.name: i for i in self.get_players_history().values()}
        m = utils.fuzzy_match(list(playernames.keys()), resp)
        if m == []:
            fmts.print_inf("未找到匹配的玩家, 无法继续")
            return
        if len(m) == 1:
            target = playernames[m[0]]
        else:
            resp = 0
            for i, playername in enumerate(m):
                fmts.print_inf(f"{i + 1}. {playername}")
            while 1:
                resp2 = utils.try_int(input(fmts.fmt_info("请输入序号: ")).strip())
                if resp2 is None:
                    fmts.print_err("输入的不是序号")
                    continue
                elif resp2 not in range(1, len(m) + 1):
                    fmts.print_err("输入的序号不在范围内")
                resp = resp2 - 1
                break
            target = playernames[m[resp]]
        fmts.print_inf(f"玩家 {target.name} 的历史记录:")
        fmts.print_inf(f"  XUID: {target.xuid}")
        fmts.print_inf(f"  设备ID: {target.deviceID or '未获取'}")
        fmts.print_inf(f"  最早记录的加入时间: {target.first_join}")
        fmts.print_inf(f"  上次加入时间: {target.last_join}")

    def record_player(self, player: Player):
        h = self.get_players_history()
        old = h.get(player.xuid)
        if old is not None:
            h[player.xuid] = PlayerHistory.load_from_player(
                player, old.first_join, old.deviceID or player.device_id
            )
        else:
            h[player.xuid] = PlayerHistory.load_from_player(player)

    def get_players_history(self):
        if self._cached_player_history is None:
            self._cached_player_history = {
                k: PlayerHistory.loads(v)
                for k, v in utils.tempjson.load_and_read(
                    self.format_data_path("player_history.json")
                ).items()
            }
        return self._cached_player_history

    def flush_players_history(self):
        content = {k: v.dumps() for k, v in self.get_players_history().items()}
        utils.tempjson.load_and_write(
            path := self.format_data_path("player_history.json"),
            content,
            need_file_exists=False,
        )
        utils.tempjson.flush(path)


# for future api reference
entry = plugin_entry(PlayerHistoryPlugin, "玩家记录")
