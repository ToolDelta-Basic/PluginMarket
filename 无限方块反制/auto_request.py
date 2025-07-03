import time
import threading
from .define import AntiInfiniteBlockBase
from .request_queue import RequestQueue, ChunkPos
from tooldelta import utils
from tooldelta.utils.tooldelta_thread import ToolDeltaThread
from tooldelta import (
    FrameExit,
    GameCtrl,
    InternalBroadcast,
    Plugin,
)


class AutoRequest:
    base: AntiInfiniteBlockBase
    request_queue: RequestQueue

    bot_dim: int
    known_bot_dim: bool

    should_close: bool
    close_waiter: threading.Lock

    def __init__(self, base: AntiInfiniteBlockBase):
        self.base = base
        self.request_queue = RequestQueue()

        self.bot_dim = 0
        self.known_bot_dim = False

        self.should_close = False
        self.close_waiter = threading.Lock()

    def game_ctrl(self) -> GameCtrl:
        return self.base.plugin.game_ctrl

    def plugin(self) -> Plugin:
        return self.base.plugin

    def on_close(self, _: FrameExit):
        self.close_waiter.acquire()
        self.should_close = True
        self.close_waiter.acquire()
        self.close_waiter.release()

    def on_inject(self):
        self.auto_send_request()

    def on_player_pos(self, event: InternalBroadcast):
        if not isinstance(event.data, dict):
            return

        bot_name = self.game_ctrl().bot_name
        if bot_name not in event.data:
            return

        self.bot_dim = event.data[bot_name]["dimension"]
        self.known_bot_dim = True

        for key in event.data:
            value: dict = event.data[key]
            if value["dimension"] != self.bot_dim:
                continue

            chunk_posx = int(value["x"]) >> 4
            chunk_posz = int(value["z"]) >> 4

            for i in range(chunk_posx - 1, chunk_posx + 2):
                for j in range(chunk_posz - 1, chunk_posz + 2):
                    self.request_queue.append_request(ChunkPos(i, j))

    def on_block_actor_data(self, packet) -> bool:
        self._on_block_actor_data(packet)
        return False

    def _on_block_actor_data(self, packet):
        if not self.known_bot_dim:
            return
        if "NBTData" not in packet:
            return

        nbt_data = packet["NBTData"]
        if not isinstance(nbt_data, dict):
            return

        if "id" not in nbt_data:
            return
        if nbt_data["id"] != "PistonArm":
            return

        break_blocks = nbt_data.get("BreakBlocks")
        if not isinstance(break_blocks, list):
            return

        length = len(break_blocks)
        if length % 3 != 0:
            return

        for i in range(length // 3):
            chunk_posx = int(break_blocks[i * 3]) >> 4
            chunk_posz = int(break_blocks[i * 3 + 2]) >> 4

            for i in range(chunk_posx - 1, chunk_posx + 2):
                for j in range(chunk_posz - 1, chunk_posz + 2):
                    self.request_queue.append_request(ChunkPos(i, j))

    @utils.thread_func(
        "无限方块反制: 自动请求区块", thread_level=ToolDeltaThread.SYSTEM
    )
    def auto_send_request(self):
        while True:
            if self.should_close:
                self.close_waiter.release()
                return
            self._auto_send_request()
            time.sleep(1)

    def _auto_send_request(self):
        self.request_queue.flush_wait_to_unix_time()
        if not self.known_bot_dim:
            return

        chunks = self.request_queue.pop_request()
        if len(chunks) == 0:
            return
        self.request_queue.set_wait_to_unix_time(chunks, self.base.repeat_time)

        request: list[dict] = []
        for i in chunks:
            request.append(
                {
                    "chunk_pos_x": i.posx,
                    "chunk_pos_z": i.posz,
                }
            )

        self.plugin().BroadcastEvent(
            InternalBroadcast(
                "scq:must_get_chunk",
                {
                    "dimension": self.bot_dim,
                    "request_chunks": request,
                },
            )
        )
