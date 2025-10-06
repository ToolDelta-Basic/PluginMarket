"""区块绘制器"""

from tooldelta import fmts, TYPE_CHECKING
import math
import time

if TYPE_CHECKING:
    from .__init__ import SchematicLoader

CHUNK_SIZE = 16


class ChunkPainter:
    def __init__(self, plugin: "SchematicLoader"):
        self.game_ctrl = plugin.game_ctrl
        self.cfg = plugin.config_mgr

    def paint_chunked_blocks(
        self,
        blocks_info,
        block_mapping,
        dim,
        start_x,
        start_y,
        start_z,
    ):
        width = blocks_info["width"]
        height = blocks_info["height"]
        length = blocks_info["length"]
        blocks = blocks_info["blocks"]
        data = blocks_info["data"]

        num_chunks_x = math.ceil(width / CHUNK_SIZE)
        num_chunks_z = math.ceil(length / CHUNK_SIZE)

        total_chunks = num_chunks_x * num_chunks_z
        chunk_counter = 0

        fmts.print_inf(
            f"§eSchematic建筑大小: {width} x {height} x {length}, 区块数: {num_chunks_x} x {num_chunks_z} = {total_chunks}"
        )

        start_time = time.perf_counter()
        for cz in range(num_chunks_z):
            # 在 X轴区块 上进行蛇形遍历
            if cz % 2 == 0:
                cx_range = range(num_chunks_x)
            else:
                cx_range = range(num_chunks_x - 1, -1, -1)

            for cx in cx_range:
                chunk_counter += 1
                chunk_x_start = cx * CHUNK_SIZE
                chunk_z_start = cz * CHUNK_SIZE
                chunk_x_size = min(CHUNK_SIZE, width - chunk_x_start)
                chunk_z_size = min(CHUNK_SIZE, length - chunk_z_start)

                # 计算并tp预导入区块的坐标
                tp_x = start_x + chunk_x_start
                tp_y = start_y
                tp_z = start_z + chunk_z_start

                fmts.print_inf(
                    f"§e当前区块位置 ({cx},{cz}), 区块数 ({chunk_counter}/{total_chunks})"
                )
                self.game_ctrl.sendwocmd(
                    f'/execute in {dim} run tp @a[name="{self.game_ctrl.bot_name}"] {tp_x} {tp_y} {tp_z}'
                )
                self.game_ctrl.sendwscmd_with_resp("/testforblock ~ ~ ~ air")

                # 如果配置要求导入空气方块, 则先用/fill以区块为单位填充成空气
                if self.cfg.INCLUDE_AIR:
                    x1 = start_x + chunk_x_start
                    z1 = start_z + chunk_z_start
                    x2 = start_x + chunk_x_start + chunk_x_size - 1
                    z2 = start_z + chunk_z_start + chunk_z_size - 1
                    for local_y_top in range(height - 1, -1, -CHUNK_SIZE):
                        local_y_low = max(0, local_y_top - (CHUNK_SIZE - 1))
                        y_low = start_y + local_y_low
                        y_high = start_y + local_y_top
                        y1 = min(y_low, y_high)
                        y2 = max(y_low, y_high)
                        self.game_ctrl.sendwocmd(
                            f"/fill {x1} {y1} {z1} {x2} {y2} {z2} air"
                        )
                    fmts.print_inf(f"§a区块 ({cx},{cz}) 清理已完成")

                # 遍历并放置方块（注意：一律跳过单个空气块，因为已由 /fill 处理或因为配置要求不导入空气）
                set_count = 0
                skip_count = 0
                total_in_chunk = 0
                for y in range(height):
                    for lz in range(chunk_z_size):
                        for lx in range(chunk_x_size):
                            x_local = chunk_x_start + lx
                            z_local = chunk_z_start + lz
                            idx = self.calc_index(x_local, y, z_local, width, length)
                            if idx < 0 or idx >= len(blocks):
                                continue

                            block_val = blocks[idx]
                            data_val = data[idx] if idx < len(data) else 0
                            name_entry = block_mapping.get(block_val, None)
                            if name_entry:
                                block_name = name_entry.get(data_val, None)
                                if not block_name:
                                    block_name = name_entry.get(0)

                            # 跳过空气的/setblock
                            if block_val == 0:
                                continue

                            total_in_chunk += 1

                            # 找不到对应的映射, 跳过导入并弹出警告
                            if not name_entry or not block_name:
                                fmts.print_inf(
                                    f"§6警告: 找不到方块(Blocks:{block_val},Data:{data_val})对应的名称映射"
                                )
                                skip_count += 1
                                continue

                            # 计算方块放置坐标
                            gx = start_x + x_local
                            gy = start_y + y
                            gz = start_z + z_local

                            self.game_ctrl.sendwocmd(
                                f"/setblock {gx} {gy} {gz} {block_name}"
                            )
                            set_count += 1
                            time.sleep(1 / self.cfg.LOAD_SPEED)

                # 导入进度显示(按区块)
                pct = (chunk_counter / total_chunks) * 100
                fmts.print_inf(
                    f"§a区块 ({cx},{cz}) 导入已完成: 共成功 {set_count} 方块, 失败 {skip_count} 方块, 处理了区块内 {total_in_chunk} 方块, 当前区块进度: {chunk_counter}/{total_chunks} ({pct:.1f}%)"
                )

        elapsed = time.perf_counter() - start_time
        fmts.print_inf(f"\n§a已完成导入, 共耗时 {elapsed:.6f} 秒")

    @staticmethod
    def calc_index(x, y, z, width, length):
        return x + (z * width) + (y * width * length)
