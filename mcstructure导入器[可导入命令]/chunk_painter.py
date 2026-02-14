"""区块绘制器"""

from tooldelta import fmts, TYPE_CHECKING
import math
import time

if TYPE_CHECKING:
    from .__init__ import MCStructureLoader

CHUNK_SIZE = 16


class ChunkPainter:
    def __init__(self, plugin: "MCStructureLoader") -> None:
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr
        self.sendanycmd = plugin.core.sendanycmd

    def paint_chunked_blocks(
        self,
        mcstructure_data: dict,
        dim: str,
        start_x: int,
        start_y: int,
        start_z: int,
    ) -> None:
        size = mcstructure_data["size"]
        block_primary = mcstructure_data["block_primary"]
        block_secondary = mcstructure_data["block_secondary"]
        block_palette = mcstructure_data["block_palette"]
        command_data = mcstructure_data["command_data"]
        AIR_INDEX = mcstructure_data["air_index"]
        sizeX = size["X"]
        sizeY = size["Y"]
        sizeZ = size["Z"]

        num_chunks_x = math.ceil(sizeX / CHUNK_SIZE)
        num_chunks_z = math.ceil(sizeZ / CHUNK_SIZE)

        total_chunks = num_chunks_x * num_chunks_z
        chunk_counter = 0

        fmts.print_inf(
            f"§emcstructure建筑大小: {sizeX} x {sizeY} x {sizeZ}, 区块数: {num_chunks_x} x {num_chunks_z} = {total_chunks}"
        )

        start_time = time.perf_counter()
        palette_len = len(block_palette)
        sleep_time = 1 / self.cfg.BLOCK_LOAD_SPEED

        for cx in range(num_chunks_x):
            # 在 Z轴区块 上进行蛇形遍历
            if cx % 2 == 0:
                cz_range = range(num_chunks_z)
            else:
                cz_range = range(num_chunks_z - 1, -1, -1)

            for cz in cz_range:
                chunk_counter += 1
                chunk_x_start = cx * CHUNK_SIZE
                chunk_z_start = cz * CHUNK_SIZE
                chunk_x_size = min(CHUNK_SIZE, sizeX - chunk_x_start)
                chunk_z_size = min(CHUNK_SIZE, sizeZ - chunk_z_start)

                # 计算并tp预导入区块的坐标
                tp_x = start_x + chunk_x_start
                tp_y = start_y
                tp_z = start_z + chunk_z_start

                fmts.print_inf(
                    f"§e当前区块位置 ({cx},{cz}), 区块数 ({chunk_counter}/{total_chunks})"
                )
                self.sendanycmd(
                    f'/execute in {dim} run tp @a[name="{self.game_ctrl.bot_name}"] {tp_x} {tp_y} {tp_z}'
                )
                self.game_ctrl.sendwscmd_with_resp(
                    f"/testforblock {tp_x} {tp_y} {tp_z} air"
                )

                # 如果配置要求导入空气方块, 则先用/fill以区块为单位填充成空气
                if self.cfg.INCLUDE_AIR:
                    x1 = start_x + chunk_x_start
                    z1 = start_z + chunk_z_start
                    x2 = start_x + chunk_x_start + chunk_x_size - 1
                    z2 = start_z + chunk_z_start + chunk_z_size - 1
                    for local_y_top in range(sizeY - 1, -1, -CHUNK_SIZE):
                        local_y_low = max(0, local_y_top - (CHUNK_SIZE - 1))
                        y_low = start_y + local_y_low
                        y_high = start_y + local_y_top
                        y1 = min(y_low, y_high)
                        y2 = max(y_low, y_high)
                        self.sendanycmd(f"/fill {x1} {y1} {z1} {x2} {y2} {z2} air")
                    fmts.print_inf(f"§a区块 ({cx},{cz}) 清理已完成")

                set_count = 0

                for y_local in range(sizeY):
                    for x_local in range(chunk_x_size):
                        for z_local in range(chunk_z_size):
                            idx_x = chunk_x_start + x_local
                            idx_y = y_local
                            idx_z = chunk_z_start + z_local

                            world_x = start_x + idx_x
                            world_y = start_y + idx_y
                            world_z = start_z + idx_z

                            # 先放置 block_secondary (水/岩浆), 再放置 block_primary (一般方块)
                            sec_idx = int(block_secondary[idx_x, idx_y, idx_z])
                            pri_idx = int(block_primary[idx_x, idx_y, idx_z])

                            # 如果 block_secondary 具有有效索引(>=0), 则输出对应 /setblock
                            if sec_idx != AIR_INDEX and 0 <= sec_idx < palette_len:
                                sec_name_states = block_palette[sec_idx]
                                self.sendanycmd(
                                    f"/setblock {world_x} {world_y} {world_z} {sec_name_states}"
                                )
                                set_count += 1
                                time.sleep(sleep_time)

                            # 如果 block_primary 具有有效索引(>=0), 则输出对应 /setblock
                            if pri_idx != AIR_INDEX and 0 <= pri_idx < palette_len:
                                pri_name_states = block_palette[pri_idx]
                                self.sendanycmd(
                                    f"/setblock {world_x} {world_y} {world_z} {pri_name_states}"
                                )
                                set_count += 1
                                time.sleep(sleep_time)

                # 导入进度显示(按区块)
                pct = (chunk_counter / total_chunks) * 100
                fmts.print_inf(
                    f"§a区块 ({cx},{cz}) 导入已完成:  已成功导入区块内 {set_count} 方块, 当前区块进度: {chunk_counter}/{total_chunks} ({pct:.1f}%)"
                )

        elapsed = time.perf_counter() - start_time
        fmts.print_inf(f"\n§a已完成方块导入, 共耗时 {elapsed:.6f} 秒")

        if self.cfg.INCLUDE_CMD:
            self.plugin.command_loader.load_command(
                command_data, dim, start_x, start_y, start_z
            )
