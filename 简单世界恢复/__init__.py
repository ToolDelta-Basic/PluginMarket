import os
import json
import threading
import time
from tooldelta import (
    FrameExit,
    InternalBroadcast,
    Plugin,
    Frame,
    fmts,
    utils,
    plugin_entry,
)
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta.utils.tooldelta_thread import ToolDeltaThread


class SimpleWorldRecover(Plugin):
    name = "简单世界恢复"
    author = "YoRHa"
    version = (0, 0, 3)

    chunk_we_want: tuple[int, int, int]
    chunk_we_get: list[dict]

    not_update_got_chunk: threading.Lock
    chunk_waiter: threading.Event

    should_close: bool
    running_mutex: threading.Lock

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.make_data_path()

        self.chunk_we_want = (-1, 0, 0)
        self.chunk_we_get = []

        self.not_update_got_chunk = threading.Lock()
        self.not_update_got_chunk.acquire()
        self.chunk_waiter = threading.Event()

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.ListenInternalBroadcast("scq:publish_chunk_data", self.on_chunk_data)

    def on_def(self):
        global bwo
        pip = self.GetPluginAPI("pip")
        _ = self.GetPluginAPI("主动区块请求", (0, 1, 1))

        if 0:
            from pip模块支持 import PipSupport

            pip: PipSupport

        pip.require({"bedrock-world-operator": "bedrockworldoperator"})
        import bedrockworldoperator as bwo

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["recover/"],
            " ".join(
                [
                    "[存档文件夹名(位于 插件数据文件/简单世界恢复/)]",
                    "[要恢复区域的起始坐标 | 形如(x,y,z)]",
                    "[要恢复区域的终止坐标 | 形如(x,y,z)]",
                ],
            ),
            "导入存档内的建筑物",
            self.runner,
        )

    def on_close(self, _: FrameExit):
        self.should_close = True
        self.chunk_waiter.set()
        self.running_mutex.acquire()
        self.running_mutex.release()

    def on_chunk_data(self, event: InternalBroadcast):
        chunk_pos_x = event.data[0]["sub_chunk_pos_x"]
        chunk_pos_z = event.data[0]["sub_chunk_pos_z"]
        dimension = event.data[0]["dimension"]

        if (dimension, chunk_pos_x, chunk_pos_z) == self.chunk_we_want:
            if not self.not_update_got_chunk.acquire(timeout=0):
                return
        else:
            return

        self.chunk_we_get = event.data
        self.chunk_waiter.set()

    def get_chunk(
        self, dim: int, chunk_pox_x: int, chunk_pos_z: int
    ) -> tuple["bwo.Chunk", bool]:
        if self.should_close:
            return bwo.Chunk(), False

        self.game_ctrl.sendwocmd(
            f'execute as @a[name="{self.game_ctrl.bot_name}"] at @s run tp {(chunk_pox_x << 4)} {0} {chunk_pos_z << 4}'
        )
        self.game_ctrl.sendwscmd_with_resp("")

        self.chunk_we_want = (dim, chunk_pox_x, chunk_pos_z)
        self.not_update_got_chunk.release()

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
            return bwo.Chunk(), False

        for i in self.chunk_we_get:
            code = i["result_code"]
            if (
                code != SUB_CHUNK_RESULT_SUCCESS
                and code != SUB_CHUNK_RESULT_SUCCESS_ALL_AIR
            ):
                return bwo.Chunk(), False

        sub_chunks: list[bwo.SubChunk] = []
        r = bwo.Dimension(dim).range()

        for i in self.chunk_we_get:
            if i["result_code"] == SUB_CHUNK_RESULT_SUCCESS:
                sub_chunk_with_index = bwo.from_sub_chunk_network_payload(
                    i["blocks"], r
                )
                sub_chunks.append(sub_chunk_with_index.sub_chunk)
            else:
                sub_chunks.append(bwo.new_sub_chunk())

        c = bwo.new_chunk(r)
        c.set_sub(sub_chunks)
        return c, True

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
        self.game_ctrl.sendwocmd(
            f"setblock {pos[0]} {pos[1]} {pos[2]} {block_states.Name} {self.as_block_states_string(block_states.States)}"
        )

    def get_bot_dimension(self) -> int:
        result = self.game_ctrl.sendwscmd_with_resp("querytarget @s")
        if result.SuccessCount == 0:
            return -1
        content = json.loads(result.OutputMessages[0].Parameters[0])
        return int(content[0]["dimension"])

    def do_world_recover(self, cmd: list[str]):
        if not self.running_mutex.acquire(timeout=0):
            fmts.print_err("同一时刻最多处理一个恢复任务")
            return
        if not self.should_close:
            self._do_world_recover(cmd)
        self.running_mutex.release()

    @utils.thread_func("世界恢复进程", thread_level=ToolDeltaThread.SYSTEM)
    def _do_world_recover(self, cmd: list[str]):
        dim_id = self.get_bot_dimension()
        if dim_id == -1:
            fmts.print_err("无法获取机器人当前维度")
            return
        dm = bwo.Dimension(dim_id)

        try:
            filename = cmd[0]

            if not filename.endswith(".mcworld"):
                filename.removesuffix(".mcworld")
            world_path = self.format_data_path(filename)

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

        for chunk_pos in bot_path:
            if self.should_close:
                world.close_world()
                return

            finish_ratio = round(progress / (len(bot_path)) * 100)
            fmts.print_inf(f"正在处理 {chunk_pos} 处的区块 ({finish_ratio}%)")
            progress += 1

            if not world.load_chunk(chunk_pos, dm).is_valid():
                fmts.print_war(f"位于 {chunk_pos} 的区块没有找到, 跳过")
                continue

            server_chunk: bwo.Chunk
            success = False

            for i in range(3):
                if self.should_close:
                    world.close_world()
                    return

                server_chunk, success = self.get_chunk(
                    int(dm), chunk_pos.x, chunk_pos.z
                )

                if not success:
                    fmts.print_war(
                        f"位于 {chunk_pos} 的区块未能从服务器请求得到, 尝试重试 (第 {i}/3 次尝试)"
                    )
                    continue
                else:
                    break

            if not success:
                fmts.print_war(f"位于 {chunk_pos} 的区块确实无法从服务器请求得到, 跳过")
                continue

            pen_x = chunk_pos.x << 4
            pen_z = chunk_pos.z << 4

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

                    y = comb_pos >> 8
                    z = (comb_pos - ((comb_pos >> 8) << 8)) >> 4
                    x = comb_pos - ((comb_pos >> 4) << 4)

                    chunk_sub_block_0 = chunk_sub_blocks_0.block(x, y, z)
                    server_sub_block_0 = server_sub_blocks_0.block(x, y, z)
                    chunk_sub_block_1 = chunk_sub_blocks_1.block(x, y, z)
                    server_sub_block_1 = server_sub_blocks_1.block(x, y, z)

                    if chunk_sub_block_1 != server_sub_block_1:
                        self.send_build_command(
                            (pen_x + x, pen_y + y, pen_z + z), chunk_sub_block_1
                        )
                        recover_block_count += 1
                        time.sleep(0.001)

                    if chunk_sub_block_0 != server_sub_block_0:
                        self.send_build_command(
                            (pen_x + x, pen_y + y, pen_z + z), chunk_sub_block_0
                        )
                        recover_block_count += 1
                        time.sleep(0.001)

        world.close_world()
        fmts.print_suc(f"已完成恢复工作, 一共恢复了 {recover_block_count} 个方块")

    def runner(self, cmd: list[str]):
        self.do_world_recover(cmd)


entry = plugin_entry(SimpleWorldRecover, "简单世界恢复")
