"""抽奖与发奖。"""

import random
import threading

from tooldelta import Player

from .actionbar import ActionBar
from .config import Settings


def amount(raw) -> int:
    "整数是定值, [最少, 最多] 在区间里随机"
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            lo, hi = int(raw[0]), int(raw[1])
            return random.randint(min(lo, hi), max(lo, hi))
        except (TypeError, ValueError):
            return 1
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


class LootDealer:
    def __init__(self, plugin, settings: Settings, bar: ActionBar, stop: threading.Event):
        self.plugin = plugin
        self.settings = settings
        self.bar = bar
        self.stop = stop
        # 本服支不支持 /loot; None = 还没试过
        self._loot_cmd_ok: bool | None = None

    def roll(self) -> dict | None:
        table = self.settings.loot_table()
        if not table:
            return None
        weights = [float(e.get("权重", 0)) for e in table]
        return random.choices(table, weights=weights, k=1)[0]

    def clear_vanilla(self, pos: tuple) -> None:
        """清掉鱼钩附近的掉落物, 也就是服务端自己给的那条鱼。

        物品实体在收竿那一刻才生成, 而且立刻朝玩家飞, 只清一次很容易踩空:
        太早还没生成, 太晚已经飞走。
        """
        x, y, z = pos
        radius = float(self.settings["清除半径(格)"])
        cmd = f"kill @e[type=item,x={x:.1f},y={y:.1f},z={z:.1f},r={radius}]"
        self.plugin.send(cmd)
        if self.stop.wait(0.35):
            return
        self.plugin.send(cmd)

    def grant(self, player: Player, entry: dict) -> None:
        name = str(entry.get("名称", "??"))
        count = amount(entry.get("数量", 1))
        rarity = str(entry.get("稀有度", "普通"))
        style = self.settings.style(rarity)

        if not self._deliver(player, entry, count):
            return
        fields = {
            "名称": name,
            "数量": count,
            "稀有度": rarity,
            "品质": f"{style.get('颜色', '§7')}[{rarity}]§r",
            "玩家": player.name,
        }
        if tip := self.settings["钓获提示"]:
            text = tip.format(**fields)
            # 动作栏抢眼但会淡出, 聊天栏留痕可以往上翻, 两处都发
            self.bar.show(player, text, float(self.settings["提示持续(秒)"]))
            player.show(text)
        if sound := style.get("音效"):
            self.plugin.send(f"playsound {sound} {player.safe_name}")
        if style.get("全服播报") and (msg := self.settings["全服播报"]):
            self.plugin.game_ctrl.say_to("@a", msg.format(**fields))

    def _deliver(self, player: Player, entry: dict, count: int) -> bool:
        """把物品塞给玩家, 返回是否成功。

        物品 ID 写错时 /give 只是静默失败, 玩家看到 "钓到了 XX" 却两手空空, 所以
        拿 SuccessCount 确认真给出去了再提示。发不出去就什么都不显示。

        战利品表走 /loot give: 基岩版的 /give 附带不了附魔数据, 只有这条路能拿到
        带真附魔的书和装备。本服不支持时退回「备用物品」, 只判一次并记住。
        """
        if table := entry.get("战利品表"):
            if self._loot_cmd_ok is not False:
                ok = self._run(f'loot give {player.safe_name} loot "{table}"')
                if self._loot_cmd_ok is None:
                    self._loot_cmd_ok = ok
                    if not ok:
                        self.plugin.print_war(
                            "本服不支持 /loot give, 战利品表类奖励将退回「备用物品」"
                        )
                if ok:
                    return True
            entry = {**entry, "物品": entry.get("备用物品") or "enchanted_book"}
        item = str(entry.get("物品") or "").strip()
        if not item:
            self.plugin.print_war(f"战利品「{entry.get('名称')}」没写物品 ID, 跳过")
            return False
        cmd = f"give {player.safe_name} {item} {count}"
        if self._run(cmd):
            return True
        self.plugin.print_war(
            f"发不出战利品「{entry.get('名称')}」: §c{item}§r 这个物品 ID 在本服无效 "
            f"(指令: {cmd})"
        )
        return False

    def _run(self, cmd: str) -> bool:
        # SuccessCount 不受 sendcommandfeedback 影响, 关了回显也读得到
        resp = self.plugin.send_with_resp(cmd)
        return bool(resp and resp.SuccessCount)
