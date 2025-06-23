import threading
import time
import traceback
import numpy
from io import BytesIO
from dataclasses import dataclass
from tooldelta import FrameExit, InternalBroadcast, Plugin, Frame, plugin_entry
from tooldelta import cfg as config
from tooldelta.internal.launch_cli.neo_libs.blob_hash.packet.define import (
    HashWithPosition,
    PayloadByHash,
    SubChunkPos,
)
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta.utils import fmts
from tooldelta.utils.tooldelta_thread import ToolDeltaThread


class wrapper:
    @dataclass(frozen=True)
    class chunkPos:
        pos: "bwo.ChunkPos"
        dimension: int


class HoloPsychon(Plugin):
    name = "世界の记忆"
    author = "9S, 米特奥拉, 阿尔泰尔 和 艾姬多娜"
    version = (0, 0, 7)

    def __init__(self, frame: Frame):
        CFG_DEFAULT = {
            "存档名字": "Kunst Wunderkammer",
            "世界种子号": 96,
            "显示坐标": True,
            "启用调试": False,
            "总是同步方块实体数据(启用后方块实体同步频率失效)": True,
            "方块实体数据同步频率(秒)": 86400,
        }
        cfg, _ = config.get_plugin_config_and_version(
            "世界の记忆", config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )

        self.enable_debug = bool(cfg["启用调试"])
        self.world_seed = int(cfg["世界种子号"])
        self.world_dir_name = str(cfg["存档名字"])
        self.show_coordinates = bool(cfg["显示坐标"])
        self.always_sync_nbt = bool(
            cfg["总是同步方块实体数据(启用后方块实体同步频率失效)"]
        )
        self.nbt_sync_time = int(cfg["方块实体数据同步频率(秒)"])

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.frame = frame
        self.game_ctrl = self.frame.get_game_control()
        self.make_data_path()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.ListenInternalBroadcast("scq:publish_chunk_data", self.on_chunk_data)

    def on_def(self):
        global bwo, xxhash
        _ = self.GetPluginAPI("主动区块请求", (0, 2, 5))

        pip = self.GetPluginAPI("pip")
        if 0:
            from pip模块支持 import PipSupport

            pip: PipSupport
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})
        pip.require({"xxhash": "xxhash"})

        import bedrockworldoperator as bwo
        import xxhash

    def on_inject(self):
        self.world = bwo.new_world(self.format_data_path(self.world_dir_name))
        if not self.world.is_valid():
            fmts.print_err(
                "世界の记忆: 打开存档失败，请检查存档是否被占用或 level.dat 正确"
            )
            self._fatal_error("fatal error: failed to open the minecraft world, reload")

        ldt = self.world.get_level_dat()
        if ldt is not None:
            ldt.level_name = self.world_dir_name
            ldt.random_seed = self.world_seed
            ldt.show_coordinates = self.show_coordinates
            self.world.modify_level_dat(ldt)

        blob_hash = self.game_ctrl.blob_hash_holder()
        blob_hash.as_mirror_world_side().mirror_world_handler.set_handler(
            self._f1,
            self._f2,
            self._f3,
            self._f4,
            self._handle_server_disconnected,
        )

        if (
            not blob_hash.get_client_function().set_holder_request()
            and not blob_hash.is_disk_holder()
        ):
            fmts.print_err("世界の记忆: 请求当前结点作为镜像存档持有人失败")
            self._fatal_error(
                "fatal error: access point refused our set mirror world holder request, reload"
            )

        if not blob_hash.as_mirror_world_side().register_listener():
            fmts.print_war("世界の记忆: 尝试重复注册侦听者")

    def on_close(self, _: FrameExit):
        self.running_mutex.acquire()
        self.should_close = True
        if "world" in self.__dict__ and self.world.is_valid():
            self.world.close_world()
        self.running_mutex.release()

    def on_chunk_data(self, event: InternalBroadcast):
        self.running_mutex.acquire()
        if not self.should_close:
            self._on_chunk_data(event)
        self.running_mutex.release()

    def _fatal_error(self, err: str):
        fmts.print_err(err + "\n")

        for i in traceback.format_stack():
            fmts.print_err(i)

        ToolDeltaThread(
            self.frame.system_exit,
            (err,),
            usage="fatal error",
            thread_level=ToolDeltaThread.SYSTEM,
        )

    def _on_chunk_data(self, event: InternalBroadcast):
        if "world" not in self.__dict__:
            return

        nbt_blocks = BytesIO()

        cp = bwo.ChunkPos(
            event.data[0]["sub_chunk_pos_x"], event.data[0]["sub_chunk_pos_z"]
        )
        dim = bwo.Dimension(event.data[0]["dimension"])

        current_unix_time = int(time.time())
        if (
            current_unix_time - self.world.load_time_stamp(cp, dim) < self.nbt_sync_time
            and not self.always_sync_nbt
        ):
            return

        for i in event.data:
            code = i["result_code"]
            if (
                code != SUB_CHUNK_RESULT_SUCCESS
                and code != SUB_CHUNK_RESULT_SUCCESS_ALL_AIR
            ):
                return

        for i in event.data:
            if i["result_code"] == SUB_CHUNK_RESULT_SUCCESS:
                nbt_blocks.write(i["nbts"])

        self.world.save_nbt_payload_only(cp, nbt_blocks.getvalue(), dim)
        self.world.save_time_stamp(cp, current_unix_time, dim)

    def _f1(self, hashes: list[HashWithPosition]) -> list[bool]:
        self.running_mutex.acquire()

        if self.should_close:
            result = [False for _ in range(len(hashes))]
        else:
            result = self._handle_query_disk_hash_exist(hashes)

        self.running_mutex.release()
        return result

    def _handle_query_disk_hash_exist(
        self, hashes: list[HashWithPosition]
    ) -> list[bool]:
        fixed_hashes: dict[wrapper.chunkPos, list[bwo.HashWithPosY]] = {}
        fixed_result: dict[HashWithPosition, bool] = {}
        result = [False for _ in range(len(hashes))]

        for i in hashes:
            cp = wrapper.chunkPos(
                bwo.ChunkPos(i.sub_chunk_pos.x, i.sub_chunk_pos.z), i.dimension
            )
            hash_with_pos_y = bwo.HashWithPosY(i.hash, i.sub_chunk_pos.y)
            if cp not in fixed_hashes:
                fixed_hashes[cp] = [hash_with_pos_y]
            else:
                fixed_hashes[cp].append(hash_with_pos_y)

        for cp, multiple_y in fixed_hashes.items():
            chunk_hashes = self.world.load_full_sub_chunk_blob_hash(
                cp.pos, bwo.Dimension(cp.dimension)
            )
            if len(chunk_hashes) == 0:
                continue

            empty_hash_with_pos_y = bwo.HashWithPosY()
            chunk_hashes_mapping: list[bwo.HashWithPosY] = [
                empty_hash_with_pos_y for _ in range(32)
            ]
            for i in chunk_hashes:
                chunk_hashes_mapping[i.PosY + 4] = i

            for hash_with_pos_y in multiple_y:
                if (
                    chunk_hashes_mapping[hash_with_pos_y.PosY + 4].Hash
                    == hash_with_pos_y.Hash
                    and hash_with_pos_y.Hash != 0
                ):
                    pos = HashWithPosition(
                        hash_with_pos_y.Hash,
                        SubChunkPos(cp.pos.x, hash_with_pos_y.PosY, cp.pos.z),
                        cp.dimension,
                    )
                    fixed_result[pos] = True

        for index in range(len(hashes)):
            if hashes[index] in fixed_result:
                result[index] = True

        return result

    def _f2(self, hashes: list[HashWithPosition]) -> list[PayloadByHash]:
        self.running_mutex.acquire()

        if self.should_close:
            result = []
        else:
            result = self._handle_get_disk_hash_payload(hashes)

        self.running_mutex.release()
        return result

    def _handle_get_disk_hash_payload(
        self, hashes: list[HashWithPosition]
    ) -> list[PayloadByHash]:
        fixed_hashes: dict[wrapper.chunkPos, list[bwo.HashWithPosY]] = {}
        result: list[PayloadByHash] = []

        for i in hashes:
            cp = wrapper.chunkPos(
                bwo.ChunkPos(i.sub_chunk_pos.x, i.sub_chunk_pos.z), i.dimension
            )
            hash_with_pos_y = bwo.HashWithPosY(i.hash, i.sub_chunk_pos.y)
            if cp not in fixed_hashes:
                fixed_hashes[cp] = [hash_with_pos_y]
            else:
                fixed_hashes[cp].append(hash_with_pos_y)

        for cp, multiple_y in fixed_hashes.items():
            chunk_hashes = self.world.load_full_sub_chunk_blob_hash(
                cp.pos, bwo.Dimension(cp.dimension)
            )
            if len(chunk_hashes) == 0:
                continue

            chunk_hashes_mapping = [0 for _ in range(32)]
            for i in chunk_hashes:
                chunk_hashes_mapping[i.PosY + 4] = i.Hash

            for hash_with_pos_y in multiple_y:
                hash = chunk_hashes_mapping[hash_with_pos_y.PosY + 4]
                if hash != hash_with_pos_y.Hash or hash == 0:
                    continue

                sub_chunk_pos = bwo.SubChunkPos(
                    cp.pos.x, hash_with_pos_y.PosY, cp.pos.z
                )
                sub_chunk = self.world.load_sub_chunk(
                    sub_chunk_pos, bwo.Dimension(cp.dimension)
                )
                if not sub_chunk.is_valid():
                    continue

                r = bwo.Dimension(cp.dimension).range()
                payload = bwo.sub_chunk_network_payload(
                    sub_chunk, sub_chunk_pos.y - (r.start_range >> 4), r
                )
                if xxhash.xxh64(payload, 0).intdigest() != hash:
                    self.world.save_sub_chunk_blob_hash(
                        sub_chunk_pos, 0, bwo.Dimension(cp.dimension)
                    )
                    continue

                result.append(
                    PayloadByHash(
                        HashWithPosition(
                            hash,
                            SubChunkPos(
                                sub_chunk_pos.x, sub_chunk_pos.y, sub_chunk_pos.z
                            ),
                            cp.dimension,
                        ),
                        numpy.frombuffer(payload, dtype=numpy.uint8),
                    )
                )

        if self.enable_debug and len(hashes) > 0:
            fixed_result: list[HashWithPosition] = []
            for i in result:
                fixed_result.append(i.hash)
            output_message = "处理服务者查询请求(含二进制荷载)"
            output_message += f"\n\t\t§e查询成功率(命中率): §b{round(len(fixed_result) / len(hashes) * 100, 2)} §f%"
            output_message += f"\n\t\t§e要查询的子区块: §f{hashes}"
            output_message += f"\n\t\t§e镜像存档里面已有的子区块: §f{fixed_result}"
            fmts.print_suc(output_message + "\n")

        return result

    def _f3(self, payload: list[PayloadByHash]):
        self.running_mutex.acquire()
        if not self.should_close:
            self._handle_require_sync_hash_to_disk(payload)
        self.running_mutex.release()

    def _handle_require_sync_hash_to_disk(self, payload: list[PayloadByHash]) -> None:
        if self.enable_debug:
            fixed_request: list[HashWithPosition] = []
            for i in payload:
                fixed_request.append(i.hash)
            output_message = "服务者请求将子区块数据同步到磁盘"
            output_message += f"\n\t\t§e要同步到磁盘的子区块: §f{fixed_request}"
            fmts.print_inf(output_message + "\n")

        for i in payload:
            sub_chunk_with_index = bwo.from_sub_chunk_network_payload(
                i.payload.tobytes(), bwo.Dimension(i.hash.dimension).range()
            )
            if sub_chunk_with_index.sub_chunk.is_valid():
                self.world.save_sub_chunk(
                    bwo.SubChunkPos(
                        i.hash.sub_chunk_pos.x,
                        i.hash.sub_chunk_pos.y,
                        i.hash.sub_chunk_pos.z,
                    ),
                    sub_chunk_with_index.sub_chunk,
                    bwo.Dimension(i.hash.dimension),
                )

        for i in payload:
            self.world.save_sub_chunk_blob_hash(
                bwo.SubChunkPos(
                    i.hash.sub_chunk_pos.x,
                    i.hash.sub_chunk_pos.y,
                    i.hash.sub_chunk_pos.z,
                ),
                i.hash.hash,
                bwo.Dimension(i.hash.dimension),
            )

    def _f4(self, pos: list[HashWithPosition]):
        self.running_mutex.acquire()
        if not self.should_close:
            self._handle_clean_blob_hash_and_apply_to_world(pos)
        self.running_mutex.release()

    def _handle_clean_blob_hash_and_apply_to_world(
        self, pos: list[HashWithPosition]
    ) -> None:
        fixed_pos: dict[wrapper.chunkPos, list[int]] = {}
        sub_chunk_need_to_set_air: dict[wrapper.chunkPos, list[int]] = {}

        for i in pos:
            cp = wrapper.chunkPos(
                bwo.ChunkPos(i.sub_chunk_pos.x, i.sub_chunk_pos.z), i.dimension
            )
            if cp not in fixed_pos:
                fixed_pos[cp] = [i.sub_chunk_pos.y]
            else:
                fixed_pos[cp].append(i.sub_chunk_pos.y)

        for cp, multiple_y in fixed_pos.items():
            chunk_hashes = self.world.load_full_sub_chunk_blob_hash(
                cp.pos, bwo.Dimension(cp.dimension)
            )
            new_hashes: list[bwo.HashWithPosY] = []

            chunk_hashes_mapping = [False for _ in range(32)]
            for i in chunk_hashes:
                chunk_hashes_mapping[i.PosY + 4] = True

            multiple_y_mapping = [False for _ in range(32)]
            for y in multiple_y:
                multiple_y_mapping[y + 4] = True

            # These areas are empty (full of air),
            # but not record on the disk.
            for y in multiple_y:
                if chunk_hashes_mapping[y + 4]:
                    continue
                if cp not in sub_chunk_need_to_set_air:
                    sub_chunk_need_to_set_air[cp] = [y]
                else:
                    sub_chunk_need_to_set_air[cp].append(y)
                new_hashes.append(bwo.HashWithPosY(0, y))

            # These areas changed from not empty to full of air,
            # and should set to empty (full of air).
            for i in chunk_hashes:
                if i.Hash != 0 and multiple_y_mapping[i.PosY + 4]:
                    if cp not in sub_chunk_need_to_set_air:
                        sub_chunk_need_to_set_air[cp] = [y]
                    else:
                        sub_chunk_need_to_set_air[cp].append(y)
                    continue
                new_hashes.append(i)

            self.world.save_full_sub_chunk_blob_hash(
                cp.pos, new_hashes, bwo.Dimension(cp.dimension)
            )

        for cp, multiple_y in sub_chunk_need_to_set_air.items():
            for y in multiple_y:
                self.world.save_sub_chunk(
                    bwo.SubChunkPos(cp.pos.x, y, cp.pos.z),
                    bwo.new_sub_chunk(),
                    bwo.Dimension(cp.dimension),
                )

        if self.enable_debug and len(sub_chunk_need_to_set_air) > 0:
            success_count = 0
            for i in sub_chunk_need_to_set_air:
                success_count += len(sub_chunk_need_to_set_air[i])
            output_message = "服务者请求重置这些子区块为空气"
            output_message += (
                f"\n\t\t§e改变程度: §b{round(success_count / len(pos) * 100, 2)} §f%"
            )
            output_message += f"\n\t\t§e要变成空气的子区块: §f{pos}"
            output_message += (
                f"\n\t\t§e实际变成空气的子区块: §f{sub_chunk_need_to_set_air}"
            )
            fmts.print_suc(output_message + "\n")

    def _handle_server_disconnected(self) -> None:
        fmts.print_err(
            "世界の记忆: 当前结点已被 Blob hash 缓存数据集的服务者撤销镜像存档的持有人身份"
        )
        self._fatal_error(
            "fatal error: access point cancelled our mirror world holder status, reload"
        )


entry = plugin_entry(HoloPsychon, "世界の记忆")
