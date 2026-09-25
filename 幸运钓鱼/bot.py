"""机器人停靠与坐标查询。"""

import json

from tooldelta import Player

from .config import Settings

# querytarget 给玩家的是视线高度, 减掉眼高才是脚下坐标
EYE = 1.62

# 离停靠点超过这么多格才送回去, 免得为零点几格反复 tp
TOLERANCE = 8.0


def quote(name: str) -> str:
    """把玩家名包成指令里的带引号字符串, 转义掉反斜杠和引号。"""
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Bot:
    """让机器人守在钓鱼区, 顺带提供按选择器查坐标的能力。"""

    def __init__(self, plugin, settings: Settings):
        self.plugin = plugin
        self.settings = settings

    def query(self, selector: str, eye_offset: float = 0.0) -> dict[int, tuple]:
        """查询选择器选中的实体坐标, 返回 {uniqueId: (x, y, z)}。"""
        resp = self.plugin.send_with_resp(f"querytarget {selector}")
        if (
            resp is None
            or not resp.OutputMessages
            or not resp.OutputMessages[0].Success
        ):
            return {}
        try:
            entries = json.loads(resp.OutputMessages[0].Parameters[0])
        except (IndexError, TypeError, ValueError):
            return {}
        if not isinstance(entries, list):
            return {}
        result: dict[int, tuple] = {}
        for entry in entries:
            try:
                p = entry["position"]
                result[int(entry["uniqueId"])] = (
                    float(p["x"]), float(p["y"]) - eye_offset, float(p["z"])
                )
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def keep_docked(self) -> None:
        """机器人不在停靠点附近就送回去。

        不是开服 tp 一次就完事: 它可能掉下去、被打死重生、或者被别的东西传走,
        一旦离开钓鱼区, 服务端就不再推送那边的实体包, 整套检测静默失效。
        """
        if not self.settings["机器人停靠"]:
            return
        bot = self.plugin.game_ctrl.bot_name
        if not bot:
            return
        safe = quote(bot)
        dock = self.settings.dock_point()
        where = next(iter(self.query(safe, EYE).values()), None)
        if where is not None:
            drift = sum((where[i] - dock[i]) ** 2 for i in range(3)) ** 0.5
            if drift <= TOLERANCE:
                return
            self.plugin.print_inf(
                f"机器人离停靠点 {drift:.0f} 格, 送回 "
                f"{dock[0]:.0f} {dock[1]:.0f} {dock[2]:.0f}"
            )
        self.plugin.send(f"tp {safe} {dock[0]:.1f} {dock[1]:.1f} {dock[2]:.1f}")

    def nearest_player(self, pos: tuple[float, float, float]) -> Player | None:
        """离鱼钩最近的在线玩家。

        只在元数据里没有 owner_eid 时用。鱼钩最远也就抛出去二三十格, 钓鱼时人又
        是朝着钩站的, 实践中够准, 但两个人肩并肩下竿可能认错。
        """
        maintainer = self.plugin.game_ctrl.players
        bot = self.plugin.game_ctrl.bot_name
        best: Player | None = None
        best_dist = float("inf")
        for uid, where in self.query("@a", EYE).items():
            player = maintainer.getPlayerByUniqueID(uid)
            if player is None or player.name == bot:
                continue
            dist = sum((where[i] - pos[i]) ** 2 for i in range(3))
            if dist < best_dist:
                best, best_dist = player, dist
        return best
