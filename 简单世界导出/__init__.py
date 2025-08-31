import threading
import time
import uuid
import numpy
from .uuid_safe_string import make_uuid_safe_string
from tooldelta.utils import tempjson
from tooldelta.utils.tooldelta_thread import ToolDeltaThread
from tooldelta import (
    FrameExit,
    Plugin,
    Frame,
    fmts,
    utils,
    plugin_entry,
)


class SimpleWorldExporter(Plugin):
    name = "简单世界导出"
    author = "YoRHa"
    version = (0, 0, 2)

    world_api: "GameInteractive | None"
    should_close: bool
    running_mutex: threading.Lock

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()

        self.world_api = None
        self.should_close = False
        self.running_mutex = threading.Lock()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.make_data_path()

    def need_upgrade_bwo(self) -> bool:
        version_path = self.format_data_path("bwo_version.json")
        loaded_dict = tempjson.load_and_read(
            version_path, need_file_exists=False, default={}
        )
        if "version" not in loaded_dict:
            return True
        if loaded_dict["version"] != "1.3.1":
            return True
        return False

    def save_bwo_version(self):
        version_path = self.format_data_path("bwo_version.json")
        tempjson.write(
            version_path,
            {"version": "1.3.1"},
        )
        tempjson.flush(version_path)

    def on_def(self):
        global bwo, nbtlib, GameInteractive
        if 0:
            from pip模块支持 import PipSupport
            from 前置_世界交互 import GameInteractive

            pip: PipSupport

        self.world_api: "GameInteractive | None" = self.GetPluginAPI(
            "前置-世界交互", (2, 0, 6)
        )

        pip = self.GetPluginAPI("pip")
        if self.need_upgrade_bwo():
            pip.upgrade("bedrock-world-operator")
            self.save_bwo_version()
        else:
            pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        import bedrockworldoperator as bwo
        import nbtlib

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["export/"],
            " ".join(
                [
                    "[导出起始坐标 | 形如(x,y,z)]",
                    "[导出终止坐标 | 形如(x,y,z)]",
                    "[存档名称]",
                ],
            ),
            "导出存档内的建筑物",
            self.runner,
        )

    def on_close(self, _: FrameExit):
        self.should_close = True
        self.running_mutex.acquire()
        self.running_mutex.release()

    def as_pos(self, string: str) -> tuple[int, int, int]:
        """
        e.g.
            as_pos(self, "(1,2,3)") -> (1, 2, 3)
        """
        s = string.replace("(", "", 1).replace(")", "", 1).split(",")
        return int(s[0]), int(s[1]), int(s[2])

    def get_start_and_end_pos(
        self, start: tuple[int, int, int], end: tuple[int, int, int]
    ) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """
        e.g.
            get_start_and_end_pos(self, (-1, -2, 9), (8, 6, -8))
            ->
            ((-1, -2, -8), (8, 6, 9))
        """
        min_pos = (min(start[0], end[0]), min(start[1], end[1]), min(start[2], end[2]))
        max_pos = (max(start[0], end[0]), max(start[1], end[1]), max(start[2], end[2]))
        return min_pos, max_pos

    @utils.thread_func("世界导出进程", thread_level=ToolDeltaThread.SYSTEM)
    def do_world_export(self, cmd: list[str]):
        if self.world_api is None:
            fmts.print_err("简单世界导出: Should nerver happened")
            return
        if not self.running_mutex.acquire(timeout=0):
            fmts.print_err("简单世界导出: 同一时刻最多处理一个任务")
            return
        if not self.should_close:
            self._do_world_export(cmd)
        self.running_mutex.release()

    def _do_world_export(self, cmd: list[str]):
        # Pre-check
        if self.world_api is None:
            fmts.print_err("简单世界导出: Should nerver happened (mark 0)")
            return

        # Parse command line
        try:
            start_pos, end_pos = self.get_start_and_end_pos(
                self.as_pos(cmd[0]), self.as_pos(cmd[1])
            )
            world_name = cmd[2]
            world_path = self.format_data_path(world_name)
        except Exception as err:
            fmts.print_err(f"简单世界导出: 命令参数不足或填写不正确: {err}")
            return

        # Fix position so that it is align with chunks
        start_pos = (
            (start_pos[0] >> 4) << 4,
            (start_pos[1] >> 4) << 4,
            (start_pos[2] >> 4) << 4,
        )
        end_pos = (
            ((end_pos[0] >> 4) << 4) + 15,
            ((end_pos[1] >> 4) << 4) + 15,
            ((end_pos[2] >> 4) << 4) + 15,
        )

        # Open mcworld
        world = bwo.new_world(world_path)
        if not world.is_valid():
            fmts.print_err(
                "简单世界导出: 无法打开存档, 请检查存档是否正被使用或 level.dat 文件是否正确"
            )
            return

        # Set world name
        ldt = world.get_level_dat()
        if ldt is not None:
            ldt.level_name = world_name
            ldt.show_coordinates = True
            world.modify_level_dat(ldt)

        # Prepare
        facing = -1
        size_x = end_pos[0] - start_pos[0] + 1
        size_y = end_pos[1] - start_pos[1] + 1
        size_z = end_pos[2] - start_pos[2] + 1

        # Get chunk count
        x_chunk_count = size_x // 16
        z_chunk_count = size_z // 16
        current_progress = 1
        total_chunks = x_chunk_count * z_chunk_count

        # Do export
        for relative_chunk_posz in range(z_chunk_count):
            # Check if should close
            if self.should_close:
                world.close_world()
                return

            # Prepare
            dump_start_z = start_pos[2] + (relative_chunk_posz << 4)
            facing *= -1

            # Compute range
            range_start, range_end = 0, x_chunk_count
            if facing == -1:
                range_start = x_chunk_count - 1
                range_end = -1

            # Do export
            for relative_chunk_posx in range(range_start, range_end, facing):
                # Check if should close
                if self.should_close:
                    world.close_world()
                    return

                # Prepare
                dump_start_x = start_pos[0] + (relative_chunk_posx << 4)
                task_percent = round(current_progress / total_chunks * 100, 2)
                self.game_ctrl.sendwscmd(
                    f"execute as @a[name={self.game_ctrl.bot_name}] at @s run tp "
                    + f"{dump_start_x} {start_pos[1]} {dump_start_z}",
                )

                # Chunk load checker
                while True:
                    # Check if should close
                    if self.should_close:
                        world.close_world()
                        return
                    # Check chunk load states
                    try:
                        structure_name = make_uuid_safe_string(str(uuid.uuid4()))
                        resp = self.game_ctrl.sendwscmd_with_resp(
                            f'execute as @a[name="{self.game_ctrl.bot_name}"] at @s '
                            + f"positioned {dump_start_x} ~ ~ positioned ~ {start_pos[1]} ~ positioned ~ ~ {dump_start_z} run "
                            + f'structure save "{structure_name}" ~ ~ ~ ~ {end_pos[1]} ~ '
                            + "false memory true",
                        )
                    except Exception:
                        continue
                    # If chunk was loaded
                    if resp.SuccessCount > 0:
                        self.game_ctrl.sendwocmd(f'structure delete "{structure_name}"')
                        fmts.print_suc(
                            f"简单世界导出: Chunk ({dump_start_x}, {dump_start_z}) "
                            + f"was loaded, and now we start to exporting... ({task_percent} %)"
                        )
                        break
                    # If chunk still loading
                    fmts.print_war(
                        f"简单世界导出: Chunk ({dump_start_x}, {dump_start_z}) "
                        + "is still loading, waiting to server to finish this chunk."
                    )
                    time.sleep(1)

                # Get structure
                try:
                    resp = self.world_api.get_structure(
                        (dump_start_x, start_pos[1], dump_start_z),
                        (16, size_y, 16),
                    )
                except Exception as e:
                    fmts.print_war(
                        f"简单世界导出: Request chunk ({dump_start_x}, {start_pos[1]}, {dump_start_z}) "
                        + f"with size (16, {size_y}, 16) failed due to {e}"
                    )
                    continue

                # Get block palette and block matrix
                block_palette: list[int | numpy.uint32] = []
                block_matrix_0: numpy.ndarray = resp.block_matrix(0)
                block_matrix_1: numpy.ndarray = resp.block_matrix(1)

                # Get block runtime ID block palette
                for i in resp.block_palette():
                    block_runtime_id = bwo.state_to_runtime_id(i.name, i.states)
                    if block_runtime_id == 0:
                        block_runtime_id = bwo.state_to_runtime_id("minecraft:unknown")
                    block_palette.append(block_runtime_id)

                # Init new empty chunk
                c = bwo.new_chunk()
                if not c.is_valid():
                    fmts.print_err("简单世界导出: Should nerver happened (mark 1)")
                    world.close_world()
                    return
                foreground_blocks = c.blocks(0)
                background_blocks = c.blocks(1)

                # Set block
                idx = 0
                for x in range(16):
                    for y in range(start_pos[1], end_pos[1] + 1):
                        for z in range(16):
                            # Get idx of block palette
                            idx_for_layer_0 = block_matrix_0[idx]
                            idx_for_layer_1 = block_matrix_1[idx]
                            # Set block
                            if idx_for_layer_0 != -1:
                                foreground_blocks.set_block(
                                    x, y, z, block_palette[idx_for_layer_0]
                                )
                            if idx_for_layer_1 != -1:
                                background_blocks.set_block(
                                    x, y, z, block_palette[idx_for_layer_1]
                                )
                            # Increase idx
                            idx += 1

                # Commit changes
                c.set_blocks(0, foreground_blocks)
                c.set_blocks(1, background_blocks)

                # Save changes
                chunk_pos = bwo.ChunkPos(dump_start_x >> 4, dump_start_z >> 4)
                world.save_chunk(chunk_pos, c)
                world.save_nbt(chunk_pos, resp.block_nbt_data())

                # Update progress
                current_progress += 1

        # Close world
        world.close_world()
        fmts.print_suc("简单世界导出: Task finished")

    def runner(self, cmd: list[str]):
        self.do_world_export(cmd)


entry = plugin_entry(SimpleWorldExporter)
