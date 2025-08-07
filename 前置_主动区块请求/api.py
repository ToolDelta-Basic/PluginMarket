import time
from tooldelta import InternalBroadcast, Plugin
from tooldelta.mc_bytes_packet import sub_chunk_request
from tooldelta.mc_bytes_packet.sub_chunk import SUB_CHUNK_RESULT_CHUNK_NOT_FOUND
from tooldelta.internal.launch_cli.neo_libs.neo_conn import (
    CInt,
    TranslateChunkNBT_return,
    as_python_bytes,
    toByteCSlice,
)
from .define import (
    EMPTY_SINGLE_SUB_CHUNK,
    AutoSubChunkRequestBase,
    ChunkListener,
    ChunkPosWithDimension,
    SingleSubChunk,
)


class AutoSubChunkRequestAPI:
    auto_sub_chunk_request_base: AutoSubChunkRequestBase

    def __init__(self, auto_sub_chunk_request_base: AutoSubChunkRequestBase):
        self.auto_sub_chunk_request_base = auto_sub_chunk_request_base

    def base(self) -> AutoSubChunkRequestBase:
        return self.auto_sub_chunk_request_base

    def plugin(self) -> Plugin:
        return self.base().plugin

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
        if self.base().should_close:
            return

        self.base().must_chunk_position_waiter.acquire()
        self.plugin().BroadcastEvent(InternalBroadcast("ggpp:force_update", {}))
        self.base().must_chunk_position_waiter.acquire()

        self.base().must_chunk_position_waiter_release.acquire()
        if self.base().must_chunk_position_waiter.locked():
            self.base().must_chunk_position_waiter.release()
        self.base().must_chunk_position_waiter_release.release()

        dimension: int = event.data["dimension"]
        request_chunks: list[dict] = event.data["request_chunks"]

        y_range = (-4, 19)
        if dimension == 1:
            y_range = (0, 7)
        if dimension == 2:
            y_range = (0, 15)

        self.base().mu.acquire()
        for i in request_chunks:
            chunk_pos_with_dim = ChunkPosWithDimension(
                i["chunk_pos_x"], i["chunk_pos_z"], dimension
            )
            if (
                chunk_pos_with_dim in self.base().chunk_listener
                or chunk_pos_with_dim in self.base().requet_queue
            ):
                continue

            pk = sub_chunk_request.SubChunkRequest(
                dimension, chunk_pos_with_dim.x, 0, chunk_pos_with_dim.z
            )
            pk.Offsets = [(0, y, 0) for y in range(y_range[0], y_range[1] + 1)]
            self.base().requet_queue[chunk_pos_with_dim] = pk

            self.base().chunk_listener[chunk_pos_with_dim] = ChunkListener(
                [EMPTY_SINGLE_SUB_CHUNK for _ in range(32)], 0, False
            )
        self.base().mu.release()

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
            ret: TranslateChunkNBT_return = self.base().LIB.TranslateChunkNBT(
                toByteCSlice(nbts), CInt(len(nbts))
            )
            bs = as_python_bytes(ret.bs, ret.length)
            self.base().LIB.FreeMem(ret.bs)

        self.base().mu.acquire()

        cp = ChunkPosWithDimension(pos[0], pos[2], dimension)
        if cp not in self.base().chunk_listener:
            self.base().mu.release()
            return
        current_listener = self.base().chunk_listener[cp]

        if current_listener.expire_unix_time == 0:
            current_listener.expire_unix_time = int(time.time()) + 10

        current_sub_chunk = SingleSubChunk(result_code, pos[1], blocks, bs)
        current_listener.subchunks[pos[1] + 4] = current_sub_chunk

        y_range = range(24)
        if dimension == 1:
            y_range = range(4, 12)
        elif dimension == 2:
            y_range = range(4, 20)

        chunk_is_completely = True
        for i in y_range:
            if current_listener.subchunks[i] == EMPTY_SINGLE_SUB_CHUNK:
                chunk_is_completely = False
                break

        if chunk_is_completely:
            pub: list[dict] = []

            for i in current_listener.subchunks:
                if i == EMPTY_SINGLE_SUB_CHUNK:
                    continue
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

            current_listener.finished = True
            if len(pub) > 0:
                self.plugin().BroadcastEvent(
                    InternalBroadcast("scq:publish_chunk_data", pub)
                )

        self.base().mu.release()

    def set_chunk_all_failed_and_publish(
        self,
        dimension: int,
        chunk_pos: tuple[int, int],
    ):
        """
        set_chunk_all_failed_and_publish 将位于维度 dimension 且位置处于 chunk_pos 的区块的所有子区块结果设为失败。
        它是一个内部的实现细节，并且是线程不安全的(没有使用全局互斥锁)，主要用于撤销那些超出机器人可达范围的区块
        """
        cp = ChunkPosWithDimension(chunk_pos[0], chunk_pos[1], dimension)
        if cp not in self.base().chunk_listener:
            return
        current_listener = self.base().chunk_listener[cp]

        y_range = range(24)
        if dimension == 1:
            y_range = range(4, 12)
        elif dimension == 2:
            y_range = range(4, 20)

        for i in y_range:
            if current_listener.subchunks[i] != EMPTY_SINGLE_SUB_CHUNK:
                continue
            current_listener.subchunks[i] = SingleSubChunk(
                SUB_CHUNK_RESULT_CHUNK_NOT_FOUND, i - 4, b"", b""
            )

        pub: list[dict] = []
        for i in current_listener.subchunks:
            if i == EMPTY_SINGLE_SUB_CHUNK:
                continue
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

        if cp in self.base().requet_queue:
            del self.base().requet_queue[cp]
        if cp in self.base().chunk_listener:
            del self.base().chunk_listener[cp]

        if len(pub) > 0:
            self.plugin().BroadcastEvent(
                InternalBroadcast("scq:publish_chunk_data", pub)
            )
