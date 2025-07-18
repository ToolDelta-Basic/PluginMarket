import ctypes
import threading
from dataclasses import dataclass
from tooldelta.mc_bytes_packet import sub_chunk_request
from tooldelta.internal.launch_cli.neo_libs.blob_hash.blob_hash_holder import (
    BlobHashHolder,
)
from tooldelta import (
    GameCtrl,
    Plugin,
    cfg as config,
)


@dataclass(frozen=True)
class ChunkPosWithDimension:
    x: int = 0
    z: int = 0
    dim: int = 0


@dataclass(frozen=True)
class DimChunkPosWithUnixTime:
    last_update_unix_time: int
    pos: ChunkPosWithDimension


@dataclass(frozen=True)
class SingleSubChunk:
    ResultCode: int = 0
    PosY: int = 0
    Blocks: bytes = b""
    NBTs: bytes = b""


@dataclass
class ChunkListener:
    subchunks: list[SingleSubChunk]
    expire_unix_time: int
    finished: bool


EMPTY_SINGLE_SUB_CHUNK = SingleSubChunk()
EMPTY_CHUNK_POS_WITH_DIMENSION = ChunkPosWithDimension()


class AutoSubChunkRequestBase:
    plugin: Plugin
    game_ctrl: GameCtrl

    LIB: ctypes.CDLL
    blob_hash: BlobHashHolder

    multiple_pos: dict[str, DimChunkPosWithUnixTime]
    request_radius: int
    request_radius_pow: int
    force_update_time: float
    request_chunk_per_second: int

    mu: threading.Lock
    must_chunk_position_waiter_release: threading.Lock
    must_chunk_position_waiter: threading.Lock
    requet_queue: dict[ChunkPosWithDimension, sub_chunk_request.SubChunkRequest]
    chunk_listener: dict[ChunkPosWithDimension, ChunkListener]

    should_close: bool
    get_request_queue_running_states_mu: threading.Lock
    request_queue_is_running: bool
    close_waiter: threading.Lock

    def __init__(self, plugin: Plugin):
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl

        CFG_DEFAULT = {
            "请求半径(最大 5 半径)": 4,
            "每多少秒重新请求周围区块(浮点数)": 300,
            "每秒同维度的每个玩家请求多少个区块(整数)": 6,
            "每秒最多请求的总区块数(整数)": 60,
        }
        cfg, _ = config.get_plugin_config_and_version(
            "主动区块请求",
            config.auto_to_std(CFG_DEFAULT),
            CFG_DEFAULT,
            self.plugin.version,
        )

        self.multiple_pos = {}
        self.request_radius = min(int(cfg["请求半径(最大 5 半径)"]), 5)
        self.request_radius_pow = self.request_radius**2
        self.force_update_time = float(cfg["每多少秒重新请求周围区块(浮点数)"])
        self.request_chunk_per_second = int(
            cfg["每秒同维度的每个玩家请求多少个区块(整数)"]
        )
        self.max_chunks_to_request_per_second = int(cfg["每秒最多请求的总区块数(整数)"])

        self.mu = threading.Lock()
        self.must_chunk_position_waiter_release = threading.Lock()
        self.must_chunk_position_waiter = threading.Lock()
        self.requet_queue = {}
        self.chunk_listener = {}

        self.should_close = False
        self.get_request_queue_running_states_mu = threading.Lock()
        self.request_queue_is_running = False
        self.close_waiter = threading.Lock()
