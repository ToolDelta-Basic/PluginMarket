import ctypes
from tooldelta import FrameExit, Plugin, ToolDelta, plugin_entry
from tooldelta.constants.packets import PacketIDS
from tooldelta.internal.launch_cli.neo_libs.neo_conn import (
    CBytes,
    CInt,
    TranslateChunkNBT_return,
)
from .api import AutoSubChunkRequestAPI
from .define import AutoSubChunkRequestBase
from .sub_chunk_process import AutoSubChunkRequestSubChunkProcess
from .requet_queue import AutoSubChunkRequetQueue


class AutoSubChunkRequest(Plugin):
    name = "NieR: Automata"
    author = "2B"
    version = (0, 4, 5)

    base: AutoSubChunkRequestBase
    api: AutoSubChunkRequestAPI
    requet_queue: AutoSubChunkRequetQueue
    sub_chunk_process: AutoSubChunkRequestSubChunkProcess

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)

        self.base = AutoSubChunkRequestBase(self)
        self.api = AutoSubChunkRequestAPI(self.base)
        self.requet_queue = AutoSubChunkRequetQueue(self.api)
        self.sub_chunk_process = AutoSubChunkRequestSubChunkProcess(self.api)

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)

        self.ListenInternalBroadcast("scq:must_get_chunk", self.api.must_get_chunk)
        self.ListenInternalBroadcast(
            "ggpp:publish_player_position", self.requet_queue.on_player_position
        )
        self.ListenBytesPacket(PacketIDS.SubChunk, self.sub_chunk_process.on_sub_chunk)

    def on_def(self):
        _ = self.GetPluginAPI("循环获取玩家坐标", (0, 0, 4))

    def on_inject(self):
        self.base.blob_hash = self.game_ctrl.blob_hash_holder()
        self.load_lib()
        self.requet_queue.auto_poll()

    def on_close(self, _: FrameExit):
        self.base.get_request_queue_running_states_mu.acquire()
        self.base.close_waiter.acquire()
        self.base.should_close = True
        self.base.get_request_queue_running_states_mu.release()

        if self.base.request_queue_is_running:
            self.base.close_waiter.acquire()
            self.base.close_waiter.release()

    def load_lib(self):
        from tooldelta.internal.launch_cli.neo_libs.neo_conn import LIB

        LIB.TranslateChunkNBT.argtypes = [CBytes, CInt]
        LIB.TranslateChunkNBT.restype = TranslateChunkNBT_return
        LIB.FreeMem.argtypes = [ctypes.c_void_p]

        self.base.LIB = LIB


entry = plugin_entry(AutoSubChunkRequest, "主动区块请求")
