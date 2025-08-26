from io import BytesIO
import os
import json
import threading
import time
from dataclasses import dataclass
import uuid
from tooldelta.utils.tooldelta_thread import ToolDeltaThread
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta import (
    FrameExit,
    InternalBroadcast,
    Plugin,
    Frame,
    fmts,
    utils,
    plugin_entry,
)


@dataclass(frozen=True)
class chunkPos:
    dim: int = -1
    chunk_pos_x: int = 0
    chunk_pos_z: int = 0


class SimpleWorldRecover(Plugin):
    name = "简单世界恢复"
    author = "YoRHa"
    version = (0, 4, 2)

    waiting_chunk_pos: chunkPos
    waiting_chunk_data: list[dict]
    waiting_chunk_arrived: threading.Lock
    chunk_waiter: threading.Event

    chunk_cache_mu: threading.Lock
    all_waiting_chunk: set[chunkPos]
    chunk_cache: dict[chunkPos, list[dict]]

    flowers_for_machines: "FlowersForMachine | None"
    _chest_cache_requester: str

    should_close: bool
    running_mutex: threading.Lock

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.make_data_path()

        self.waiting_chunk_pos = chunkPos()
        self.waiting_chunk_data = []
        self.waiting_chunk_arrived = threading.Lock()
        self.waiting_chunk_arrived.acquire()
        self.chunk_waiter = threading.Event()

        self.chunk_cache_mu = threading.Lock()
        self.all_waiting_chunk = set()
        self.chunk_cache = {}

        self.flowers_for_machines = None
        self._chest_cache_requester = str(uuid.uuid4())

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.ListenInternalBroadcast("scq:publish_chunk_data", self.on_chunk_data)
        self.ListenInternalBroadcast("swr:recover_request", self.on_event)

    def on_def(self):
        global nbtlib, bwo, FlowersForMachine, UnMarshalBufferToPythonNBTObject

        pip = self.GetPluginAPI("pip")
        _ = self.GetPluginAPI("主动区块请求", (0, 2, 5))
        self.flowers_for_machines = self.GetPluginAPI("献给机械の花束", (1, 2, 4))

        if 0:
            from pip模块支持 import PipSupport
            from 前置_献给机械的花束 import FlowersForMachine

            pip: PipSupport
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        import nbtlib
        import bedrockworldoperator as bwo
        from bedrockworldoperator.utils.unmarshalNBT import (
            UnMarshalBufferToPythonNBTObject,
        )

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["recover/"],
            " ".join(
                [
                    "[存档文件夹名(位于 插件数据文件/简单世界恢复/)]",
                    "[要恢复区域的起始坐标 | 形如(x,z)]",
                    "[要恢复区域的终止坐标 | 形如(x,z)]",
                ],
            ),
            "导入存档内的建筑物",
            self.runner,
        )

    def on_close(self, _: FrameExit):
        self.should_close = True
        self.chunk_cache_mu.acquire()
        self.all_waiting_chunk.clear()
        self.chunk_cache = {}
        self.chunk_cache_mu.release()
        self.chunk_waiter.set()
        self.running_mutex.acquire()
        self.running_mutex.release()

    def check_is_completely_chunk(self, data: list[dict]) -> bool:
        for i in data:
            code = i["result_code"]
            if (
                code != SUB_CHUNK_RESULT_SUCCESS
                and code != SUB_CHUNK_RESULT_SUCCESS_ALL_AIR
            ):
                return False
        return True

    def on_chunk_data(self, event: InternalBroadcast):
        chunk_pos_x = event.data[0]["sub_chunk_pos_x"]
        chunk_pos_z = event.data[0]["sub_chunk_pos_z"]
        dimension = event.data[0]["dimension"]
        cp = chunkPos(dimension, chunk_pos_x, chunk_pos_z)

        self.chunk_cache_mu.acquire()
        if (
            cp in self.all_waiting_chunk
            and cp not in self.chunk_cache
            and self.check_is_completely_chunk(event.data)
        ):
            cache_count = len(self.chunk_cache)
            if cache_count >= 1024:
                for _ in range(cache_count - 1023):
                    for key in self.chunk_cache:
                        break
                    del self.chunk_cache[key]
            self.chunk_cache[cp] = event.data
        self.chunk_cache_mu.release()

        if self.waiting_chunk_pos == cp:
            if not self.waiting_chunk_arrived.acquire(timeout=0):
                return
        else:
            return

        self.waiting_chunk_data = event.data
        self.chunk_waiter.set()

    def on_event(self, event: InternalBroadcast):
        """
        API (swr:recover_request): 其他插件请求恢复一片区域

        调用方式:
            ```
            InternalBroadcast(
                "swr:recover_request",
                [
                    "...",   # 存档文件夹名(位于 插件数据文件/简单世界恢复/)
                    "...",   # 要恢复区域的起始坐标, 形如(x,z)
                    "...",   # 要恢复区域的终止坐标, 形如(x,z)
                ],
            )
            ```
        """
        self.do_world_recover(event.data, True)

    def get_chunk(
        self, dim: int, chunk_pox_x: int, chunk_pos_z: int
    ) -> tuple["bwo.Chunk", list["nbtlib.tag.Compound"], bool]:
        if self.should_close:
            return bwo.Chunk(), [], False

        try:
            self.game_ctrl.sendwocmd(
                f'execute as @a[name="{self.game_ctrl.bot_name}"] at @s run tp {(chunk_pox_x << 4)} {0} {chunk_pos_z << 4}'
            )
            self.game_ctrl.sendwscmd_with_resp("")
        except Exception:
            pass

        cp = chunkPos(dim, chunk_pox_x, chunk_pos_z)
        result_chunk: list[dict] = []

        self.chunk_cache_mu.acquire()
        if cp in self.chunk_cache:
            result_chunk = self.chunk_cache[cp]
            self.chunk_cache_mu.release()
        else:
            self.chunk_cache_mu.release()
            self.waiting_chunk_pos = chunkPos(dim, chunk_pox_x, chunk_pos_z)
            self.waiting_chunk_arrived.release()

            self.BroadcastEvent(
                InternalBroadcast(
                    "scq:must_get_chunk",
                    {
                        "dimension": dim,
                        "request_chunks": [
                            {
                                "chunk_pos_x": chunk_pox_x,
                                "chunk_pos_z": chunk_pos_z,
                            }
                        ],
                    },
                )
            )

            self.chunk_waiter.wait()
            self.chunk_waiter.clear()

            if self.should_close:
                return bwo.Chunk(), [], False

            result_chunk = self.waiting_chunk_data

        if not self.check_is_completely_chunk(result_chunk):
            return bwo.Chunk(), [], False

        sub_chunks: list[bwo.SubChunk] = []
        nbts: list[nbtlib.tag.Compound] = []
        r = bwo.Dimension(dim).range()

        for i in result_chunk:
            if i["result_code"] == SUB_CHUNK_RESULT_SUCCESS:
                sub_chunk_with_index = bwo.from_sub_chunk_network_payload(
                    i["blocks"], r
                )
                sub_chunks.append(sub_chunk_with_index.sub_chunk)

                nbt_data: bytes = i["nbts"]
                nbt_data_length = len(nbt_data)
                buf = BytesIO(nbt_data)

                while buf.seek(0, 1) != nbt_data_length:
                    nbts.append(UnMarshalBufferToPythonNBTObject(buf)[0])  # type: ignore
            else:
                sub_chunks.append(bwo.new_sub_chunk())

        c = bwo.new_chunk(r)
        c.set_sub(sub_chunks)
        return c, nbts, True

    def as_pos(self, string: str) -> tuple[int, int]:
        s = string.replace("(", "", 1).replace(")", "", 1).split(",")
        return int(s[0]), int(s[1])

    def get_start_and_end_pos(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        min_pos = (min(start[0], end[0]), min(start[1], end[1]))
        max_pos = (max(start[0], end[0]), max(start[1], end[1]))
        return min_pos, max_pos

    def compute_path(self, start: tuple[int, int], end: tuple[int, int]):
        result: list[bwo.ChunkPos] = []

        start_chunk_pos = (start[0] >> 4, start[1] >> 4)
        end_chunk_pos = (end[0] >> 4, end[1] >> 4)
        direction = 1

        for z in range(start_chunk_pos[1], end_chunk_pos[1] + 1):
            if direction == 1:
                for x in range(start_chunk_pos[0], end_chunk_pos[0] + 1):
                    result.append(bwo.ChunkPos(x, z))
            else:
                for x in range(end_chunk_pos[0], start_chunk_pos[0] - 1, -1):
                    result.append(bwo.ChunkPos(x, z))
            direction *= -1

        return result

    def as_block_states_string(self, states) -> str:  # type: ignore
        states: bwo.Compound
        out = ""

        for i in states:
            v = states[i]
            match type(v):
                case bwo.Int | bwo.String:
                    out += (
                        ","
                        + json.dumps(i, ensure_ascii=False)
                        + "="
                        + json.dumps(v, ensure_ascii=False)
                    )
                case bwo.Byte:
                    if v == 1:
                        out += "," + json.dumps(i, ensure_ascii=False) + "=true"
                    else:
                        out += "," + json.dumps(i, ensure_ascii=False) + "=false"

        return "[" + out[1:] + "]"

    def send_build_command(self, pos: tuple[int, int, int], block_runtime_id):
        block_states = bwo.runtime_id_to_state(block_runtime_id)
        try:
            self.game_ctrl.sendwocmd(
                f'execute as @a[name="{self.game_ctrl.bot_name}"] at @s run setblock {pos[0]} {pos[1]} {pos[2]} {block_states.Name} {self.as_block_states_string(block_states.States)}'
            )
        except Exception:
            pass

    def get_bot_dimension(self) -> int:
        try:
            result = self.game_ctrl.sendwscmd_with_resp("querytarget @s")
            if result.SuccessCount == 0:
                return -1
            content = json.loads(result.OutputMessages[0].Parameters[0])
            return int(content[0]["dimension"])
        except Exception:
            return -1

    @utils.thread_func("世界恢复进程", thread_level=ToolDeltaThread.SYSTEM)
    def do_world_recover(self, cmd: list[str], called_by_api: bool):
        if self.flowers_for_machines is None:
            fmts.print_err("do_world_recover: Should nerver happened")
            return

        if not called_by_api:
            cmd[0] = self.format_data_path(cmd[0])

        if not self.running_mutex.acquire(timeout=0):
            fmts.print_err("同一时刻最多处理一个恢复任务")
            return

        if not self.should_close:
            self._do_world_recover(cmd)

            self.chunk_cache_mu.acquire()
            self.all_waiting_chunk.clear()
            self.chunk_cache = {}
            self.chunk_cache_mu.release()

            self.flowers_for_machines.get_chest_cache().remove_all_chests(
                self._chest_cache_requester
            )

        self.running_mutex.release()

    def _do_world_recover(self, cmd: list[str]):
        if self.flowers_for_machines is None:
            fmts.print_err("_do_world_recover: Should nerver happened")
            return

        dim_id = self.get_bot_dimension()
        if dim_id == -1:
            fmts.print_err("无法获取机器人当前维度")
            return
        dm = bwo.Dimension(dim_id)

        try:
            world_path = cmd[0]
            start_pos, end_pos = self.get_start_and_end_pos(
                self.as_pos(cmd[1]), self.as_pos(cmd[2])
            )
        except Exception as err:
            fmts.print_err(f"命令参数不足或填写不正确: {err}")
            return

        if not os.path.isdir(world_path):
            fmts.print_err(f"未找到路径为 {world_path} 的存档文件夹")
            return

        world = bwo.new_world(world_path)
        if not world.is_valid():
            fmts.print_err(
                "无法打开存档, 请检查存档是否正被使用或 level.dat 文件是否正确"
            )
            return

        bot_path = self.compute_path(
            (start_pos[0], start_pos[1]),
            (end_pos[0], end_pos[1]),
        )

        progress = 0
        recover_block_count = 0

        self.chunk_cache_mu.acquire()
        for i in bot_path:
            self.all_waiting_chunk.add(chunkPos(int(dm), i.x, i.z))
        self.chunk_cache_mu.release()

        for chunk_pos in bot_path:
            if self.should_close:
                world.close_world()
                return

            pen_x = chunk_pos.x << 4
            pen_z = chunk_pos.z << 4
            server_chunk: bwo.Chunk

            finish_ratio = round(progress / (len(bot_path)) * 100)
            fmts.print_inf(f"正在处理 {chunk_pos} 处的区块 ({finish_ratio}%)")
            progress += 1

            if not world.load_chunk(chunk_pos, dm).is_valid():
                fmts.print_war(f"位于 {chunk_pos} 的区块没有找到, 跳过")
                continue

            while True:
                if self.should_close:
                    world.close_world()
                    return

                server_chunk, server_nbts, success = self.get_chunk(
                    int(dm), chunk_pos.x, chunk_pos.z
                )

                if not success:
                    continue
                else:
                    break

            chunk_nbts = world.load_nbt(chunk_pos, dm)
            block_pos_to_chunk_nbt: dict[tuple[int, int, int], nbtlib.tag.Compound] = {}
            block_pos_to_server_nbt: dict[tuple[int, int, int], nbtlib.tag.Compound] = (
                {}
            )
            for i in chunk_nbts:
                posx, posy, posz = int(i["x"]), int(i["y"]), int(i["z"])
                block_pos_to_chunk_nbt[(posx, posy, posz)] = i
            for i in server_nbts:
                posx, posy, posz = int(i["x"]), int(i["y"]), int(i["z"])
                block_pos_to_server_nbt[(posx, posy, posz)] = i

            for index in range(dm.height() >> 4):
                if self.should_close:
                    world.close_world()
                    return

                pen_y = server_chunk.sub_y(index)

                chunk_sub = world.load_sub_chunk(
                    bwo.SubChunkPos(chunk_pos.x, pen_y >> 4, chunk_pos.z), dm
                )
                server_sub = server_chunk.sub_chunk(pen_y)

                if not chunk_sub.is_valid():
                    fmts.print_war(
                        f"位于 ({chunk_pos.x}, {pen_y >> 4}, {chunk_pos.z}) 的子区块没有找到, 跳过"
                    )
                    continue

                if chunk_sub.empty() and server_sub.empty():
                    continue

                chunk_sub_blocks_0 = chunk_sub.blocks(0)
                server_sub_blocks_0 = server_sub.blocks(0)
                chunk_sub_blocks_1 = chunk_sub.blocks(1)
                server_sub_blocks_1 = server_sub.blocks(1)

                for comb_pos in range(4096):
                    if self.should_close:
                        world.close_world()
                        return

                    nbt_block_structure_id = ""
                    is_chest_block = False
                    place_nbt_block_success = False

                    y = comb_pos >> 8
                    z = (comb_pos - ((comb_pos >> 8) << 8)) >> 4
                    x = comb_pos - ((comb_pos >> 4) << 4)
                    final_pos = (pen_x + x, pen_y + y, pen_z + z)

                    need_rebuild = False
                    chunk_sub_block_0 = chunk_sub_blocks_0.block(x, y, z)
                    server_sub_block_0 = server_sub_blocks_0.block(x, y, z)
                    chunk_sub_block_1 = chunk_sub_blocks_1.block(x, y, z)
                    server_sub_block_1 = server_sub_blocks_1.block(x, y, z)

                    if chunk_sub_block_1 != server_sub_block_1:
                        need_rebuild = True
                    if chunk_sub_block_0 != server_sub_block_0:
                        need_rebuild = True
                    else:
                        in_chunk_nbts = final_pos in block_pos_to_chunk_nbt
                        in_server_nbts = final_pos in block_pos_to_server_nbt

                        if in_chunk_nbts and not in_server_nbts:
                            need_rebuild = True
                        if not in_chunk_nbts and in_server_nbts:
                            need_rebuild = True

                        if in_chunk_nbts and in_server_nbts:
                            states = bwo.runtime_id_to_state(chunk_sub_block_0)
                            states_string = self.as_block_states_string(states.States)

                            if "chest" in states.Name:
                                pair_chest = self.flowers_for_machines.get_chest_cache().nbt_to_chest(
                                    final_pos, block_pos_to_chunk_nbt[final_pos]
                                )
                                if pair_chest is not None:
                                    need_rebuild = True

                            resp_for_origin = self.flowers_for_machines.get_nbt_block_hash.get_nbt_block_full_hash(
                                states.Name,
                                states_string,
                                block_pos_to_chunk_nbt[final_pos],
                            )
                            resp_for_current = self.flowers_for_machines.get_nbt_block_hash.get_nbt_block_full_hash(
                                states.Name,
                                states_string,
                                block_pos_to_server_nbt[final_pos],
                            )

                            if resp_for_origin.hash != resp_for_current.hash:
                                need_rebuild = True

                    if not need_rebuild:
                        continue

                    if chunk_sub_block_1 != bwo.AIR_BLOCK_RUNTIME_ID:
                        self.send_build_command(final_pos, chunk_sub_block_1)
                        recover_block_count += 1
                        time.sleep(0.001)

                    if final_pos in block_pos_to_chunk_nbt:
                        states = bwo.runtime_id_to_state(chunk_sub_block_0)
                        if "chest" in states.Name:
                            is_chest_block = True

                        resp = (
                            self.flowers_for_machines.place_nbt_block.place_nbt_block(
                                final_pos,
                                states.Name,
                                self.as_block_states_string(states.States),
                                block_pos_to_chunk_nbt[final_pos],
                            )
                        )
                        if not resp.success:
                            fmts.print_war(
                                f"简单世界恢复: 处理 {final_pos} 处的 NBT 方块时出现错误"
                            )

                        place_nbt_block_success = resp.success
                        if resp.success and not resp.can_fast:
                            nbt_block_structure_id = resp.structure_unique_id
                    else:
                        self.send_build_command(
                            (pen_x + x, pen_y + y, pen_z + z), chunk_sub_block_0
                        )

                    if is_chest_block and place_nbt_block_success:
                        chest_cache = self.flowers_for_machines.get_chest_cache()
                        pair_chest = chest_cache.nbt_to_chest(
                            final_pos, block_pos_to_chunk_nbt[final_pos]
                        )

                        if pair_chest is not None:
                            pair_chest.set_structure_unique_id(nbt_block_structure_id)
                            chest_cache.add_chest(
                                self._chest_cache_requester, pair_chest
                            )

                            if (
                                chest_cache.find_chest(
                                    self._chest_cache_requester, pair_chest, True
                                )
                                is not None
                            ):
                                states = bwo.runtime_id_to_state(chunk_sub_block_0)

                                resp = self.flowers_for_machines.place_large_chest.place_large_chest(
                                    self._chest_cache_requester,
                                    states.Name,
                                    self.as_block_states_string(states.States),
                                    pair_chest,
                                )
                                if not resp.success:
                                    fmts.print_war(
                                        f"简单世界恢复: 处理 {final_pos} 处的大箱子时出现错误"
                                    )

                                chest_cache.remove_chest_and_its_pair(
                                    self._chest_cache_requester, pair_chest
                                )

                    recover_block_count += 1
                    time.sleep(0.001)

        world.close_world()
        fmts.print_suc(f"已完成恢复工作, 一共恢复了 {recover_block_count} 个方块")

    def runner(self, cmd: list[str]):
        self.do_world_recover(cmd, False)


entry = plugin_entry(SimpleWorldRecover, "简单世界恢复")
