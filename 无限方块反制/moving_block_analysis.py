import threading
import time
from dataclasses import dataclass
from .define import AntiInfiniteBlockBase
from tooldelta import utils
from tooldelta.utils.tooldelta_thread import ToolDeltaThread
from tooldelta import (
    FrameExit,
    GameCtrl,
)


@dataclass
class MovingBlockSample:
    moving_block_pos: tuple[int, int, int]
    piston_pos: tuple[int, int, int]


class MovingBlockAnalysis:
    base: AntiInfiniteBlockBase

    _mu: threading.Lock
    _pending_list: list[MovingBlockSample]

    _should_close: bool
    _close_waiter: threading.Lock

    def __init__(self, base: AntiInfiniteBlockBase):
        self.base = base
        self._mu = threading.Lock()
        self._pending_list = []
        self._should_close = False
        self._close_waiter = threading.Lock()

    def game_ctrl(self) -> GameCtrl:
        return self.base.plugin.game_ctrl

    def game_interact(self):
        return self.base.game_interact

    def on_close(self, _: FrameExit):
        self._close_waiter.acquire()
        self._should_close = True
        self._close_waiter.acquire()
        self._close_waiter.release()

    def on_inject(self):
        self.auto_analysis()

    def append_to_pending_list(
        self, moving_block_pos: tuple[int, int, int], piston_pos: tuple[int, int, int]
    ):
        with self._mu:
            self._pending_list.append(MovingBlockSample(moving_block_pos, piston_pos))

    @utils.thread_func(
        "无限方块反制: 异常方块分析", thread_level=ToolDeltaThread.SYSTEM
    )
    def auto_analysis(self):
        while True:
            if self._should_close:
                self._close_waiter.release()
                return
            self._auto_analysis()
            time.sleep(0.5)

    def _auto_analysis(self):
        with self._mu:
            for i in self._pending_list:
                self._analysis_single_sample(i)
            self._pending_list.clear()

    def _analysis_single_sample(self, sample: MovingBlockSample):
        min_pos = (
            min(sample.moving_block_pos[0], sample.piston_pos[0]),
            min(sample.moving_block_pos[1], sample.piston_pos[1]),
            min(sample.moving_block_pos[2], sample.piston_pos[2]),
        )
        max_pos = (
            max(sample.moving_block_pos[0], sample.piston_pos[0]),
            max(sample.moving_block_pos[1], sample.piston_pos[1]),
            max(sample.moving_block_pos[2], sample.piston_pos[2]),
        )
        size = (
            max_pos[0] - min_pos[0] + 1,
            max_pos[1] - min_pos[1] + 1,
            max_pos[2] - min_pos[2] + 1,
        )

        if size[0] > 64 or size[1] > 64 or size[2] > 64:
            return

        try:
            structure = self.game_interact().get_structure(min_pos, size)
        except Exception:
            return

        try:
            moving_block = structure.get_block(
                (
                    sample.moving_block_pos[0] - min_pos[0],
                    sample.moving_block_pos[1] - min_pos[1],
                    sample.moving_block_pos[2] - min_pos[2],
                ),
            )
            piston = structure.get_block(
                (
                    sample.piston_pos[0] - min_pos[0],
                    sample.piston_pos[1] - min_pos[1],
                    sample.piston_pos[2] - min_pos[2],
                ),
            )
        except Exception:
            return

        if moving_block.foreground is None or piston.foreground is None:
            return
        if moving_block.entity_data is None:
            return

        if str(moving_block.entity_data["id"]) != "MovingBlock":
            return
        piston_pos = (
            int(moving_block.entity_data["pistonPosX"]),
            int(moving_block.entity_data["pistonPosY"]),
            int(moving_block.entity_data["pistonPosZ"]),
        )
        if piston_pos != sample.piston_pos:
            return

        if "piston" not in piston.foreground.name:
            bot_name = self.game_ctrl().bot_name
            x, y, z = sample.moving_block_pos

            self.game_ctrl().sendwocmd(
                f'execute as @a[name="{bot_name}"] at @s run setblock {x} {y} {z} cherry_wall_sign'
            )
            self.game_ctrl().sendwscmd_with_resp("")
            self.game_ctrl().sendwscmd_with_resp("")

            self.game_ctrl().sendwocmd(
                f'execute as @a[name="{bot_name}"] at @s run setblock {x} {y} {z} air'
            )
            self.game_ctrl().sendwscmd_with_resp("")
            self.game_ctrl().sendwscmd_with_resp("")

            for command_line in self.base.command_line:
                self.game_ctrl().sendwocmd(
                    f'execute as @a[name="{bot_name}"] at @s positioned {x} {y} {z} run {command_line}'
                )
