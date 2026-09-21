"""动作栏提示。"""

import json
import threading
import time
from typing import Callable

from tooldelta import Player

# 动作栏几秒就淡出, 一条提示要按这个间隔重发才挂得住
REFRESH = 0.6


class ActionBar:
    """玩家动作栏上的提示, 按固定间隔重发来维持住不淡出。"""

    def __init__(
        self,
        send: Callable[[str], None],
        stop: threading.Event,
        alive: Callable[[], bool],
    ):
        self.send = send
        self.stop = stop
        self.alive = alive
        self._token: dict[str, object] = {}
        self._until: dict[str, float] = {}

    def show(self, player: Player, text: str, duration: float) -> None:
        """把一条提示挂在玩家动作栏上, 持续 duration 秒。

        每次调用换一个令牌, 旧循环发现令牌变了就退场。不这么做的话 "上钩了" 那
        两秒的重发会把紧接着的 "钓到了 XX" 一遍遍盖回去, 而收竿就发生在咬钩后一
        秒内, 等于奖励提示永远看不见。
        """
        if not text.strip():
            return
        token = object()
        self._token[player.xuid] = token
        self._until[player.xuid] = time.time() + duration
        payload = json.dumps({"rawtext": [{"text": text}]}, ensure_ascii=False)
        deadline = time.time() + duration
        while True:
            if self._token.get(player.xuid) is not token:
                return
            self.send(f"titleraw {player.safe_name} actionbar {payload}")
            if time.time() + REFRESH >= deadline:
                break
            if self.stop.wait(REFRESH) or not self.alive():
                break
        if self._token.get(player.xuid) is token:
            self._until.pop(player.xuid, None)

    def is_alerting(self, player: Player) -> bool:
        """该玩家此刻动作栏上是不是还挂着提示。"""
        until = self._until.get(player.xuid)
        return until is not None and until > time.time()
