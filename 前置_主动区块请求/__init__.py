import ctypes
import threading
import time
import queue
from collections import deque
from dataclasses import dataclass
from tooldelta import InternalBroadcast, Plugin, Frame, plugin_entry
from tooldelta import cfg as config
from tooldelta.constants.packets import PacketIDS
from tooldelta.internal.launch_cli.neo_libs.blob_hash.packet.define import (
    HashWithPosition,
    SubChunkPos,
)
from tooldelta.internal.launch_cli.neo_libs.neo_conn import (
    CBytes,
    CInt,
    TranslateChunkNBT_return,
    as_python_bytes,
    toByteCSlice,
)
from tooldelta.mc_bytes_packet import sub_chunk_request
from tooldelta.mc_bytes_packet.base_bytes_packet import BaseBytesPacket
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
    SubChunk,
)
from tooldelta.utils import fmts
from tooldelta.utils.tooldelta_thread import ToolDeltaThread


@dataclass(frozen=True)
class ChunkPosWithDimension:
    x: int = 0
    z: int = 0
    dim: int = 0


@dataclass(frozen=True)
class PlayerChunkPos:
    last_update_unix_time: int
    pos: ChunkPosWithDimension


@dataclass(frozen=True)
class SingleSubChunk:
    ResultCode: int = 0
    PosY: int = 0
    Blocks: bytes = b""
    NBTs: bytes = b""


@dataclass
class LocalCache:
    subchunks: list[SingleSubChunk]
    channel: queue.Queue[None]


EMPTY_SINGLE_SUB_CHUNK = SingleSubChunk()
EMPTY_CHUNK_POS_WITH_DIMENSION = ChunkPosWithDimension()


class AutoSubChunkRequest(Plugin):
    name = "NieR: Automata"
    author = "2B"
    version = (0, 0, 5)

    LIB: ctypes.CDLL

    multiple_pos: dict[str, PlayerChunkPos]
    request_radius: int
    force_update_time: float
    request_chunk_per_second: int

    mu: threading.Lock
    must_chunk_position_waiter: threading.Lock
    requet_queue: deque[sub_chunk_request.SubChunkRequest]
    request_queue_set: set[ChunkPosWithDimension]
    local_cache: dict[ChunkPosWithDimension, LocalCache]

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = self.frame.get_game_control()

        CFG_DEFAULT = {
            "请求半径(最大 16 半径)": 4,
            "每多少秒重新请求周围区块(浮点数)": 300,
            "每秒请求多少个区块(整数)": 6,
        }
        cfg, _ = config.get_plugin_config_and_version(
            "主动区块请求", config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, (0, 0, 5)
        )

        self.multiple_pos = {}
        self.request_radius = min(int(cfg["请求半径(最大 16 半径)"]), 16)
        self.force_update_time = float(cfg["每多少秒重新请求周围区块(浮点数)"])
        self.request_chunk_per_second = int(cfg["每秒请求多少个区块(整数)"])

        self.mu = threading.Lock()
        self.must_chunk_position_waiter = threading.Lock()
        self.requet_queue = deque()
        self.request_queue_set = set()
        self.local_cache = {}

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

        self.ListenInternalBroadcast("scq:must_get_chunk", self.must_get_chunk)
        self.ListenInternalBroadcast(
            "ggpp:publish_player_position", self.on_player_position
        )
        self.ListenBytesPacket(PacketIDS.SubChunk, self.on_sub_chunk)

    def on_def(self):
        _ = self.GetPluginAPI("循环获取玩家坐标", (0, 0, 3))

    def on_inject(self):
        self.blob_hash = self.game_ctrl.blob_hash_holder()
        self.load_lib()
        ToolDeltaThread(
            self._send_request_queue, usage="循环获取玩家坐标: 自动发送请求"
        )

    def load_lib(self):
        from tooldelta.internal.launch_cli.neo_libs.neo_conn import LIB

        LIB.TranslateChunkNBT.argtypes = [CBytes, CInt]
        LIB.TranslateChunkNBT.restype = TranslateChunkNBT_return
        LIB.FreeMem.argtypes = [ctypes.c_void_p]

        self.LIB = LIB

    def _send_request_queue(self):
        while True:
            self.mu.acquire()
            for _ in range(len(self.multiple_pos) * self.request_chunk_per_second):
                if len(self.requet_queue) > 0:
                    request = self.requet_queue.popleft()
                    self.game_ctrl.sendPacket(PacketIDS.IDSubChunkRequest, request)
                    self.request_queue_set.discard(
                        ChunkPosWithDimension(
                            request.SubChunkPosX,
                            request.SubChunkPosZ,
                            request.Dimension,
                        )
                    )
            self.mu.release()
            time.sleep(1)

    def must_get_chunk(self, event: InternalBroadcast):
        """
        API (scq:must_get_chunk):
            插件主动请求区块信息，用于保证请求的区块一定可以命中，然后插件可以通过 scq:publish_chunk_data 来侦听返回的区块数据。
            注意，我们只保证命中(不会卡死)，但受制于机器人当前的位置，可能部分区块真的不在机器人可以请求的有效范围内，这种情况下你就会得到不完整的或者完全失败的区块结果。

        Event data 示例:
            ```
            {
                "dimension": int(...),             # 目标维度的 ID (必须与机器人同维度)
                "request_chunks": [
                    {
                        "chunk_pos_x": int(...),   # 要请求的区块的区块 X 坐标
                        "chunk_pos_z": int(...)    # 要请求的区块的区块 Z 坐标
                    },
                    {...},
                    ...
                ]
            }
            ```
        """
        self.must_chunk_position_waiter.acquire()
        self.BroadcastEvent(InternalBroadcast("ggpp:force_update", {}))
        self.must_chunk_position_waiter.acquire()
        self.must_chunk_position_waiter.release()

        dimension: int = event.data["dimension"]
        request_chunks: list[dict] = event.data["request_chunks"]

        y_range = (-4, 19)
        if dimension == 1:
            y_range = (0, 7)
        if dimension == 2:
            y_range = (0, 15)

        self.mu.acquire()
        for i in request_chunks:
            chunk_pos_with_dimension = ChunkPosWithDimension(
                i["chunk_pos_x"], i["chunk_pos_z"], dimension
            )
            if chunk_pos_with_dimension in self.request_queue_set:
                continue

            pk = sub_chunk_request.SubChunkRequest(
                dimension, chunk_pos_with_dimension.x, 0, chunk_pos_with_dimension.z
            )

            offsets: list[tuple[int, int, int]] = []
            for y in range(y_range[0], y_range[1] + 1):
                offsets.append((0, y, 0))

            pk.Offsets = offsets

            self.requet_queue.append(pk)
            self.request_queue_set.add(
                ChunkPosWithDimension(pk.SubChunkPosX, pk.SubChunkPosZ, dimension)
            )
        self.mu.release()

    def try_publish_chunk_data(
        self,
        result_code: int,
        dimension: int,
        pos: tuple[int, int, int],
        blocks: bytes,
        nbts: bytes,
    ):
        """
        API (scq:publish_chunk_data): 发布区块信息，确保下面的列表中携带了这个区块的所有子区块（也就是我们发布的完整区块信息）

        Event data 示例:
            ```
            [
                {
                    "result_code": int(...),       # 这个子区块的请求结果 (详见 tooldelta.mc_bytes_packet.sub_chunk 以查看常量)
                    "sub_chunk_pos_x": int(...),   # 这个子区块的 X 坐标
                    "sub_chunk_pos_y": int(...),   # 这个子区块的 Y 坐标
                    "sub_chunk_pos_z": int(...),   # 这个子区块的 Z 坐标
                    "dimension": int(...),         # 这个子区块所在的维度
                    "blocks": b"...",              # 这个子区块的方块数据 (这是网络编码形式，需要使用 bedrock-world-operator 解码)
                    "nbts": b"...",                # 这个子区块的 NBT 方块数据 (这是可以直接存入存档的 NBT 格式)
                },
                {...},
                ...
            ]
            ```
        """
        bs = b""

        if len(nbts) > 0:
            ret = self.LIB.TranslateChunkNBT(toByteCSlice(nbts), CInt(len(nbts)))
            bs = as_python_bytes(ret.bs, ret.l)
            self.LIB.FreeMem(ret.bs)

        self.mu.acquire()

        cp = ChunkPosWithDimension(pos[0], pos[2], dimension)
        if cp not in self.local_cache:
            channel = queue.Queue()
            self.local_cache[cp] = LocalCache(
                [EMPTY_SINGLE_SUB_CHUNK for _ in range(32)], channel
            )

            def simple_chunk_waiter():
                try:
                    channel.get(timeout=10)
                except Exception:
                    self.mu.acquire()
                    if cp in self.local_cache:
                        del self.local_cache[cp]
                    self.mu.release()
                    fmts.print_war(f"主动区块请求: 区块 {cp} 超时")

            ToolDeltaThread(
                simple_chunk_waiter, usage=f"主动区块请求: 区块 {cp} 的等待器"
            )

        current_sub_chunk = SingleSubChunk(result_code, pos[1], blocks, bs)
        self.local_cache[cp].subchunks[pos[1] + 4] = current_sub_chunk

        chunk_is_completely = True
        if dimension == 1:
            for i in range(8):
                if self.local_cache[cp].subchunks[i] == EMPTY_SINGLE_SUB_CHUNK:
                    chunk_is_completely = False
        elif dimension == 2:
            for i in range(16):
                if self.local_cache[cp].subchunks[i] == EMPTY_SINGLE_SUB_CHUNK:
                    chunk_is_completely = False
        else:
            for i in range(24):
                if self.local_cache[cp].subchunks[i] == EMPTY_SINGLE_SUB_CHUNK:
                    chunk_is_completely = False

        if chunk_is_completely:
            pub: list[dict] = []
            for i in self.local_cache[cp].subchunks:
                if i != EMPTY_SINGLE_SUB_CHUNK:
                    pub.append(
                        {
                            "result_code": i.ResultCode,
                            "sub_chunk_pos_x": cp.x,
                            "sub_chunk_pos_y": i.PosY,
                            "sub_chunk_pos_z": cp.z,
                            "dimension": cp.dim,
                            "blocks": i.Blocks,
                            "nbts": i.NBTs,
                        },
                    )
            self.local_cache[cp].channel.put(None)
            if cp in self.local_cache:
                del self.local_cache[cp]
            if len(pub) > 0:
                self.BroadcastEvent(InternalBroadcast("scq:publish_chunk_data", pub))

        self.mu.release()

    def on_player_position(self, event: InternalBroadcast):
        if self.game_ctrl.bot_name not in event.data:
            return

        current_unix_time = int(time.time())

        # Clean to make memory happy
        bot_dimension: int = event.data[self.game_ctrl.bot_name]["dimension"]
        new_mapping: dict[str, PlayerChunkPos] = {}
        for key in event.data:
            if event.data[key]["dimension"] != bot_dimension:
                continue
            if key in self.multiple_pos:
                new_mapping[key] = self.multiple_pos[key]
            else:
                new_mapping[key] = PlayerChunkPos(0, EMPTY_CHUNK_POS_WITH_DIMENSION)
        self.multiple_pos = new_mapping

        # Actually speaking, by the way you read to here,
        # you may know our logic is not very common.
        # Note that this is a key point, don't let others known.
        for key, value in self.multiple_pos.items():
            if key not in event.data:
                continue

            current_data = event.data[key]
            current_dimension: int = current_data["dimension"]
            current_chunk_pos_x = int(current_data["x"]) >> 4
            current_chunk_pos_z = int(current_data["z"]) >> 4

            if (
                current_unix_time - value.last_update_unix_time
                >= self.force_update_time
                or current_dimension != value.pos.dim
                or current_chunk_pos_x != value.pos.x
                or current_chunk_pos_z != value.pos.z
            ):
                self.multiple_pos[key] = PlayerChunkPos(
                    current_unix_time,
                    ChunkPosWithDimension(
                        current_chunk_pos_x, current_chunk_pos_z, current_dimension
                    ),
                )
                self.append_to_request_queue(
                    current_dimension, (current_chunk_pos_x, current_chunk_pos_z)
                )

        if not self.must_chunk_position_waiter.acquire(timeout=0):
            self.must_chunk_position_waiter.release()
        else:
            self.must_chunk_position_waiter.release()

    def append_to_request_queue(self, dimension: int, center: tuple[int, int]):
        y_range = (-4, 19)
        if dimension == 1:
            y_range = (0, 7)
        if dimension == 2:
            y_range = (0, 15)

        all_chunks: list[tuple[int, int]] = [(center[0], center[1])]

        last_x = center[0]
        last_z = center[1]
        facing_round = 0
        facing = [(0, 1), (1, 0), (0, -1), (-1, 0)]

        for current_round in range(2 * self.request_radius + 1):
            idx = facing_round % 4
            idx2 = (facing_round + 1) % 4

            for step_forward in range(current_round + 1):
                zoom = step_forward + 1
                current_x = last_x + zoom * facing[idx][0]
                current_z = last_z + zoom * facing[idx][1]
                all_chunks.append((current_x, current_z))

            last_x = all_chunks[-1][0]
            last_z = all_chunks[-1][1]

            for step_forward in range(current_round + 1):
                zoom = step_forward + 1
                current_x = last_x + zoom * facing[idx2][0]
                current_z = last_z + zoom * facing[idx2][1]
                all_chunks.append((current_x, current_z))

            last_x = all_chunks[-1][0]
            last_z = all_chunks[-1][1]
            facing_round += 2

        all_chunks = all_chunks[: -2 - 2 * self.request_radius]

        self.mu.acquire()
        for chunk in all_chunks:
            chunk_pos_with_dim = ChunkPosWithDimension(chunk[0], chunk[1], dimension)

            if chunk_pos_with_dim not in self.request_queue_set:
                pk = sub_chunk_request.SubChunkRequest(dimension, chunk[0], 0, chunk[1])

                for y in range(y_range[0], y_range[1] + 1):
                    pk.Offsets.append((0, y, 0))

                self.requet_queue.append(pk)
                self.request_queue_set.add(chunk_pos_with_dim)
        self.mu.release()

    def on_sub_chunk(self, pk: BaseBytesPacket) -> bool:
        assert type(pk) is SubChunk, "Should Nerver happened"

        if len(pk.Entries) == 0 or "blob_hash" not in self.__dict__:
            return False

        # sub_chunk_finish_states holds a list that for a sub chunk
        # entry in pk.Entries[i], this sub chunk entry is
        # finished or unfinished.
        #
        # Unfinished sub chunk entry means that the payload of
        # this entry need ask blob hash holder (server side) to get.
        sub_chunk_finish_states = [False for _ in range(len(pk.Entries))]

        # pending_blob_hash is the missing blob hash that need to
        # ask blob hash holder (server side) to get.
        pending_blob_hash: list[HashWithPosition] = []

        # unloaded_sub_chunk holds a list that contains some failed sub chunk
        # entries. These sub chunk failed is because of server has not loaded
        # them, and will be load in the future.
        # Therefore, we need to record these entires and reset packet.SubChunkRequest
        # to reget them.
        unloaded_sub_chunk: list[SubChunkPos] = []

        for index in range(len(pk.Entries)):
            entry = pk.Entries[index]

            if entry.Result == SUB_CHUNK_RESULT_SUCCESS_ALL_AIR:
                self.try_publish_chunk_data(
                    entry.Result,
                    pk.Dimension,
                    (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                    b"",
                    b"",
                )
                sub_chunk_finish_states[index] = True
                continue

            if entry.Result != SUB_CHUNK_RESULT_SUCCESS:
                # We compute if current sub chunk entry could reached by the bot
                is_include = False
                for _, value in self.multiple_pos.items():
                    if (
                        abs(entry.SubChunkPosX - value.pos.x) <= self.request_radius
                        and abs(entry.SubChunkPosZ - value.pos.z) <= self.request_radius
                        and pk.Dimension == value.pos.dim
                    ):
                        is_include = True
                        break
                # This sub chunk entry failed due to the bot is
                # moved to another place that can't reach this sub chunk.
                # Therefore, set result as failed immediately.
                if not is_include:
                    self.try_publish_chunk_data(
                        entry.Result,
                        pk.Dimension,
                        (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                        b"",
                        b"",
                    )
                # Or, this sub chunk is not loaded, and waiting server to load them.
                # Therefore, we add to unloaded sub chunk list, and them reget them
                # in a single packet.SubChunkRequest packet.
                else:
                    unloaded_sub_chunk.append(
                        SubChunkPos(
                            entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ
                        )
                    )
                # Although this sub chunk failed, due to we do the corresponding
                # process, so we can set them as finished safely.
                sub_chunk_finish_states[index] = True
                continue

            if pk.CacheEnabled:
                # Firstly, we check local blob hash list.
                # If blob hash not hit, ask blob hash holder (server side)
                # to get payload.
                #
                # Note that it's possible for self.blob_hash is not exist,
                # maybe the plugin was executed before it was injected.=
                payload = self.blob_hash.load_blob_cache(entry.BlobHash)
                # payload is empty bytes means that this blob hash needs
                # us to ask blob hash holder (server side) to get.
                if len(payload) == 0:
                    pending_blob_hash.append(
                        HashWithPosition(
                            entry.BlobHash,
                            SubChunkPos(
                                entry.SubChunkPosX,
                                entry.SubChunkPosY,
                                entry.SubChunkPosZ,
                            ),
                            pk.Dimension,
                        )
                    )
                    continue
                # When blob hash is enabled, the entry.RawPayload will
                # only holds the Block Entity NBT data of this sub chunk.
                sub_chunk_finish_states[index] = True
                self.try_publish_chunk_data(
                    entry.Result,
                    pk.Dimension,
                    (
                        entry.SubChunkPosX,
                        entry.SubChunkPosY,
                        entry.SubChunkPosZ,
                    ),
                    payload,
                    entry.NBTData.tobytes(),
                )

        # Request these failed sub chunks due to server is still loading them.
        if len(unloaded_sub_chunk) > 0:
            center = unloaded_sub_chunk[0]
            offsets: list[tuple[int, int, int]] = []
            for i in unloaded_sub_chunk:
                offsets.append((i.x - center.x, i.y - center.y, i.z - center.z))
            self.game_ctrl.sendPacket(
                PacketIDS.IDSubChunkRequest,
                sub_chunk_request.SubChunkRequest(
                    pk.Dimension, center.x, center.y, center.z, offsets
                ),
            )

        # Request missing blob hash from server-side blob hash holder.
        if len(pending_blob_hash) > 0:
            # Retry 3 times, due to blob hash holder may haven't started
            # processing on this sub chunk packet when here we have already
            # receive sub chunk packet.
            for _ in range(3):
                hit_hashes: dict[HashWithPosition, bool] = {}
                new_pending_blob_hash: list[HashWithPosition] = []

                resp = self.blob_hash.get_client_function().get_hash_payload(
                    pending_blob_hash
                )

                # hitHashes record how many blob
                # hash we get from blob hash holder
                # (server side)
                for key in resp:
                    hit_hashes[key] = True

                # new_pending_blob_hash holds the blob hash we still not have
                for i in pending_blob_hash:
                    if i not in hit_hashes:
                        new_pending_blob_hash.append(i)

                # set pending_blob_hash as new_pending_blob_hash.
                # And if len(pending_blob_hash) == 0,
                # then all blob hash we missing is hit and
                # here we should break retry
                pending_blob_hash = new_pending_blob_hash
                if len(pending_blob_hash) == 0:
                    break

        failed_sub_chunks: list[SubChunkPos] = []

        # Now we get most (hash, payload) for those
        # unfinished sub chunk entry.
        # Therefore, we start to finish those entries.
        for index in range(len(pk.Entries)):
            if sub_chunk_finish_states[index]:
                continue
            entry = pk.Entries[index]

            # We try to reload blob hash from local cache again.
            payload = self.blob_hash.load_blob_cache(entry.BlobHash)
            # payload is empty bytes refer to this sub chunk entry is still
            # missing its payload, and that means this sub chunk entry
            # is failed.
            # For those failed sub chunk entries, we send new
            # packet.SubChunkRequest to reget those entries.
            if len(payload) == 0:
                failed_sub_chunks.append(
                    SubChunkPos(
                        entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ
                    )
                )
                continue
            # When blob hash is enabled, the entry.RawPayload will
            # only holds the Block Entity NBT data of this sub chunk.
            sub_chunk_finish_states[index] = True
            self.try_publish_chunk_data(
                entry.Result,
                pk.Dimension,
                (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                payload,
                entry.NBTData.tobytes(),
            )

        # There is some sub chunk entries failed,
        # and here we resent sub chunk request to
        # reget them.
        if len(failed_sub_chunks) > 0:
            center = failed_sub_chunks[0]
            offsets: list[tuple[int, int, int]] = []
            for i in failed_sub_chunks:
                offsets.append((i.x - center.x, i.y - center.y, i.z - center.z))
            self.game_ctrl.sendPacket(
                PacketIDS.IDSubChunkRequest,
                sub_chunk_request.SubChunkRequest(
                    pk.Dimension, center.x, center.y, center.z, offsets
                ),
            )

        return False


entry = plugin_entry(AutoSubChunkRequest, "主动区块请求")
