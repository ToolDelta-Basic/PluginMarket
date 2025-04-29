import ctypes
from tooldelta import InternalBroadcast, Plugin, Frame, plugin_entry
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
from tooldelta.mc_bytes_packet.level_chunk import LevelChunk
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
    SubChunk,
)


class AutoSubChunkRequest(Plugin):
    name = "NieR: Automata"
    author = "2B"
    version = (0, 0, 1)

    LIB: ctypes.CDLL

    bot_has_position: bool = False
    bot_last_dimension: int = 0
    bot_last_chunk_pos_x: int = 0
    bot_last_chunk_pos_z: int = 0
    request_radius: int = 4

    def __init__(self, frame: Frame):
        self.frame = frame

        self.bot_has_position = False
        self.bot_last_dimension = 0
        self.bot_last_chunk_pos_x = 0
        self.bot_last_chunk_pos_z = 0
        self.request_radius = 4

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

        self.ListenPacket(PacketIDS.LevelChunk, self.on_level_chunk)  # type: ignore
        self.ListenInternalBroadcast(
            "ggpp:publish_player_position", self.on_player_position
        )
        self.ListenPacket(PacketIDS.SubChunk, self.on_sub_chunk)  # type: ignore

    def on_def(self):
        _ = self.GetPluginAPI("循环获取玩家坐标", (0, 0, 2))

    def on_inject(self):
        self.game_ctrl = self.frame.get_game_control()
        self.blob_hash = self.game_ctrl.blob_hash_holder()
        self.load_lib()

    def load_lib(self):
        from tooldelta.internal.launch_cli.neo_libs.neo_conn import LIB

        LIB.TranslateChunkNBT.argtypes = [CBytes, CInt]
        LIB.TranslateChunkNBT.restype = TranslateChunkNBT_return
        LIB.FreeMem.argtypes = [ctypes.c_void_p]

        self.LIB = LIB

    def publish_chunk_data(
        self, result_code: int, pos: tuple[int, int, int], blocks: bytes, nbts: bytes
    ):
        """
        API (scq:publish_chunk_data): 发布区块信息

        Event data 示例:
            ```
            {
                "result_code": int(...),     # 这个子区块的请求结果 (详见 tooldelta.mc_bytes_packet.sub_chunk 以查看常量)
                "sub_chunk_pos_x": pos[0],   # 这个子区块的 X 坐标
                "sub_chunk_pos_y": pos[1],   # 这个子区块的 Y 坐标
                "sub_chunk_pos_z": pos[2],   # 这个子区块的 Z 坐标
                "blocks": blocks,            # 这个子区块的方块数据 (这是网络编码形式，需要使用 bedrock-world-operator 解码)
                "nbts": nbts,                # 这个子区块的 NBT 方块数据 (这是可以直接存入存档的 NBT 格式)
            }
            ```
        """
        bs = b""

        if len(nbts) > 0:
            ret = self.LIB.TranslateChunkNBT(toByteCSlice(nbts), CInt(len(nbts)))
            bs = as_python_bytes(ret.bs, ret.l)
            self.LIB.FreeMem(ret.bs)

        self.BroadcastEvent(
            InternalBroadcast(
                "scq:publish_chunk_data",
                {
                    "result_code": result_code,
                    "sub_chunk_pos_x": pos[0],
                    "sub_chunk_pos_y": pos[1],
                    "sub_chunk_pos_z": pos[2],
                    "blocks": blocks,
                    "nbts": bs,
                },
            )
        )

    def on_player_position(self, event: InternalBroadcast):
        if self.game_ctrl.bot_name not in event.data:
            return

        bot_data = event.data[self.game_ctrl.bot_name]
        current_dimension: int = bot_data["dimension"]
        current_chunk_pos_x = int(bot_data["x"]) >> 4
        current_chunk_pos_z = int(bot_data["z"]) >> 4

        if (
            not self.bot_has_position
            or current_chunk_pos_x != self.bot_last_chunk_pos_x
            or current_chunk_pos_z != self.bot_last_chunk_pos_z
            or current_dimension != self.bot_last_dimension
        ):
            self.bot_last_dimension = current_dimension
            self.bot_last_chunk_pos_x = current_chunk_pos_x
            self.bot_last_chunk_pos_z = current_chunk_pos_z
            self.bot_has_position = True
            self.send_request_queue(
                current_dimension, (current_chunk_pos_x, current_chunk_pos_z)
            )

    def send_request_queue(self, dimension: int, center: tuple[int, int]):
        if not 0 <= dimension <= 2:
            return

        pk = sub_chunk_request.SubChunkRequest(dimension)
        pk.SubChunkPosX = center[0]
        pk.SubChunkPosY = 0
        pk.SubChunkPosZ = center[1]

        y_range = (-4, 19)
        if dimension == 1:
            y_range = (0, 7)
        if dimension == 2:
            y_range = (0, 15)

        for x_offset in range(-self.request_radius, self.request_radius + 1):
            for z_offset in range(-self.request_radius, self.request_radius):
                for i in range(y_range[0], y_range[1] + 1):
                    pk.Offsets.append((x_offset, i, z_offset))

        self.game_ctrl.sendPacket(PacketIDS.IDSubChunkRequest, pk)

    def on_level_chunk(self, pk: LevelChunk) -> bool:
        if not 0 <= pk.Dimension <= 2:
            return False

        request = sub_chunk_request.SubChunkRequest(pk.Dimension)
        request.SubChunkPosX = pk.ChunkPosX
        request.SubChunkPosY = 0
        request.SubChunkPosZ = pk.ChunkPosZ

        y_range = (-4, 19)
        if pk.Dimension == 1:
            y_range = (0, 7)
        if pk.Dimension == 2:
            y_range = (0, 15)

        for i in range(y_range[0], y_range[1] + 1):
            request.Offsets.append((0, i, 0))

        self.game_ctrl.sendPacket(PacketIDS.IDSubChunkRequest, request)
        return False

    def on_sub_chunk(self, pk: SubChunk) -> bool:
        if len(pk.Entries) == 0 or not 0 <= pk.Dimension <= 2:
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

        for index in range(len(pk.Entries)):
            entry = pk.Entries[index]

            if (
                entry.Result == SUB_CHUNK_RESULT_SUCCESS_ALL_AIR
                or entry.Result != SUB_CHUNK_RESULT_SUCCESS
            ):
                sub_chunk_finish_states[index] = True
                self.publish_chunk_data(
                    entry.Result,
                    (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                    b"",
                    b"",
                )
                continue

            if pk.CacheEnabled:
                # Firstly, we check local blob hash list.
                # If blob hash not hit, ask blob hash holder (server side)
                # to get payload.
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
                self.publish_chunk_data(
                    entry.Result,
                    (
                        entry.SubChunkPosX,
                        entry.SubChunkPosY,
                        entry.SubChunkPosZ,
                    ),
                    payload,
                    entry.NBTData.tobytes(),
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

        has_set_center = False
        new_sub_chunk_request_center = SubChunkPos()
        new_sub_chunk_request_offset: list[tuple[int, int, int]] = []

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
                if not has_set_center:
                    new_sub_chunk_request_center = SubChunkPos(
                        entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ
                    )
                    has_set_center = True
                new_sub_chunk_request_offset.append(
                    (
                        entry.SubChunkPosX - new_sub_chunk_request_center.x,
                        entry.SubChunkPosY - new_sub_chunk_request_center.y,
                        entry.SubChunkPosZ - new_sub_chunk_request_center.z,
                    ),
                )
                continue
            # When blob hash is enabled, the entry.RawPayload will
            # only holds the Block Entity NBT data of this sub chunk.
            sub_chunk_finish_states[index] = True
            self.publish_chunk_data(
                entry.Result,
                (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                payload,
                entry.NBTData.tobytes(),
            )

        # There is some sub chunk entries failed,
        # and here we resent sub chunk request to
        # reget them.
        if has_set_center:
            self.game_ctrl.sendPacket(
                PacketIDS.IDSubChunkRequest,
                sub_chunk_request.SubChunkRequest(
                    pk.Dimension,
                    new_sub_chunk_request_center.x,
                    new_sub_chunk_request_center.y,
                    new_sub_chunk_request_center.z,
                    new_sub_chunk_request_offset,
                ),
            )

        return False


entry = plugin_entry(AutoSubChunkRequest)
