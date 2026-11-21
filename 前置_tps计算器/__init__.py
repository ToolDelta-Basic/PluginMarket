from threading import Event, Thread
from time import monotonic

from tooldelta import Plugin, plugin_entry
from tooldelta.internal.types import FrameExit


class TPSCalculator(Plugin):
    name = "前置-TPS计算器"
    author = "SuperScript"
    version = (0, 0, 3)

    sample_interval = 5
    sample_max_age = 40

    def __init__(self, frame):
        super().__init__(frame)
        self._last_sample: tuple[int, float] | None = None
        self._measurement: tuple[float, float] | None = None
        self._stop = Event()
        self._sampler = Thread(
            target=self._sample_loop, name="ToolDelta TPS calculator", daemon=True
        )
        self.ListenActive(self._start)
        self.ListenFrameExit(self._close)

    def _start(self):
        if self._sampler.ident is None:
            self._sampler.start()

    def _close(self, _event: FrameExit):
        self._stop.set()

    def _sample_loop(self):
        warned = False
        while not self._stop.is_set():
            try:
                self._sample()
            except Exception as exc:
                if not warned and not self._stop.is_set():
                    self.print_war(f"无法查询游戏时间，暂时无法更新 TPS：{exc}")
                    warned = True
            else:
                warned = False
            self._stop.wait(self.sample_interval)

    def _sample(self):
        started = monotonic()
        response = self.game_ctrl.sendwscmd_with_resp("/time query gametime", 2)
        sampled_at = (started + monotonic()) / 2
        for message in response.OutputMessages:
            if (
                message.Success
                and message.Message.removeprefix("%") == "commands.time.query.gametime"
                and message.Parameters
            ):
                tick = int(message.Parameters[0])
                break
        else:
            raise ValueError("/time query gametime 未返回游戏 tick 计数")

        previous = self._last_sample
        self._last_sample = (tick, sampled_at)
        if previous is None:
            return
        previous_tick, previous_time = previous
        elapsed = sampled_at - previous_time
        if tick < previous_tick or elapsed > self.sample_max_age:
            self._measurement = None
        elif elapsed > 0:
            self._measurement = (min(20.0, (tick - previous_tick) / elapsed), sampled_at)

    def get_tps(self) -> float:
        """返回最近两次有效采样算出的 TPS，采样不足或过期时返回 0。"""
        measurement = self._measurement
        if measurement is None or monotonic() - measurement[1] > self.sample_max_age:
            return 0.0
        return measurement[0]


entry = plugin_entry(TPSCalculator, "tps计算器")
