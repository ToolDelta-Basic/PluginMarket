"""插件核心功能"""

from tooldelta import fmts, utils, TYPE_CHECKING
import threading
import gzip
import os
import json

from . import nbt_parser as NBTParser

if TYPE_CHECKING:
    from .__init__ import SchematicLoader


class Core:
    def __init__(self, plugin: "SchematicLoader") -> None:
        self.plugin = plugin
        self.data_path = plugin.data_path
        self.running_mutex = threading.Lock()

    def entry(self) -> None:
        self.plugin.frame.add_console_cmd_trigger(
            ["schematic"], None, "schematic导入器", self.main
        )

    def main(self, _: list[str]) -> None:
        MAPPING_JSON_NAME = "Minecraft_BE_block_id.json"
        MAPPING_JSON_PATH = os.path.join(
            "插件文件", "ToolDelta类式插件", self.plugin.name, MAPPING_JSON_NAME
        )
        block_mapping = self.load_mapping(MAPPING_JSON_PATH)
        if not block_mapping:
            fmts.print_inf("§c❀ 警告: 未发现schematic文件的方块名称映射表")
            return
        files = self.get_files()
        if not files:
            fmts.print_inf(
                f"§c❀ 未发现任何schematic建筑文件! 请前往 {self.data_path} 上传您需要导入的建筑文件!"
            )
            return
        file_path = self.select_file(files)
        if file_path is None:
            return
        dim, x, y, z = self.get_pos()
        if dim is None or x is None or y is None or z is None:
            return
        try:
            root_name, root = NBTParser.parse_nbt_gzip(file_path)
            if root_name.lower() == "schematic":
                fmts.print_inf("§a❀ 文件格式: schematic")
            else:
                fmts.print_inf(
                    f"§6❀ 警告: 发现文件头 TAG_Compound(10) 后的 STRING 不是 schematic, 而是 {root_name}, 文件可能出现损坏!"
                )
        except gzip.BadGzipFile as error:
            fmts.print_inf(f"§c❀ 警告: GZIP格式错误: {error}")
            return
        except Exception as error:
            fmts.print_inf(
                f"§c❀ 警告: 无法解析您的schematic文件,请检查文件是否有效: {error}"
            )
            return
        try:
            blocks_info = NBTParser.load_blocks_from_root(root)
        except Exception as error:
            fmts.print_inf(f"§c❀ 警告: 读取文件NBT数据时出现异常: {error}")
            return
        self.chunk_paint_thread(blocks_info, block_mapping, dim, x, y, z)

    @utils.thread_func("schematic导入进程")
    def chunk_paint_thread(
        self, blocks_info: dict, block_mapping: dict, dim: str, x: int, y: int, z: int
    ) -> None:
        if not self.running_mutex.acquire(timeout=0):
            fmts.print_inf("§c❀ 警告: 同一时刻最多处理一个导入任务!")
            return
        try:
            self.plugin.chunk_painter.paint_chunked_blocks(
                blocks_info, block_mapping, dim, x, y, z
            )
        except Exception as error:
            fmts.print_inf(f"§c❀ 警告: 导入建筑时出现异常: {error}")
            return
        finally:
            self.running_mutex.release()

    @staticmethod
    def load_mapping(json_path: str) -> dict[str, dict[str, str]]:
        if not json_path or not os.path.exists(json_path):
            return {}
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
        mapping = {}
        for k, v in raw.items():
            try:
                key = int(k)
            except Exception:
                continue
            inner = {}
            for ik, iv in v.items():
                try:
                    inner[int(ik)] = str(iv)
                except Exception:
                    pass
            if inner:
                mapping[key] = inner
        return mapping

    def get_files(self) -> list[str]:
        file_ext = ".schematic"
        files = []
        for i in os.listdir(self.data_path):
            i_lower = i.lower()
            if i_lower.endswith(file_ext):
                files.append(i)
        return files

    def select_file(self, files: list[str]) -> str | None:
        fmts.print_inf("\n§a❀ 已发现以下建筑文件~")
        fmts.print_inf(
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        fmts.print_inf("§l§b[ §a序号§b ] §r§a建筑文件名称")
        for i, file in enumerate(files, 1):
            fmts.print_inf(f"§l§b[ §e{i}§b ] §r§e{file}")
        fmts.print_inf(
            "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
        )
        fmts.print_inf(
            f"§a❀ §b输入 §e[1-{len(files)}]§b 之间的数字以选择 需要导入的建筑文件"
        )
        try:
            choice = (
                int(input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出")).strip()) - 1
            )
            selected_file = files[choice]
        except (ValueError, IndexError):
            fmts.print_inf("§c❀ 您输入的内容无效,已退出")
            return None
        return os.path.join(self.data_path, selected_file)

    @staticmethod
    def get_pos() -> tuple[None, None, None, None] | tuple[str, int, int, int]:
        fmts.print_inf(
            "\n§a❀ §b请输入您想要导入到服务器的哪个维度? §e(输入0-20之间的整数)"
        )
        fmts.print_inf("§6· §f0 §e- 主世界")
        fmts.print_inf("§6· §f1 §e- 下界")
        fmts.print_inf("§6· §f2 §e- 末地")
        fmts.print_inf("§6· §f3 §e- dm3")
        fmts.print_inf("§6· §fN §e- dmN §7(最大为dm20)")
        try:
            dim_input = int(
                input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出")).strip()
            )
            if dim_input <= -1 or dim_input >= 21:
                raise ValueError(f"不存在维度: dm{dim_input}")
        except ValueError:
            fmts.print_inf("§c❀ 您输入的内容无效,已退出")
            return None, None, None, None
        if dim_input == 0:
            dim = "overworld"
        elif dim_input == 1:
            dim = "nether"
        elif dim_input == 2:
            dim = "the_end"
        else:
            dim = f"dm{dim_input}"
        fmts.print_inf(f"\n§a❀ §b请输入您想要导入到维度{dim}的X坐标 §e(输入整数)")
        try:
            x = int(input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出")).strip())
        except ValueError:
            fmts.print_inf("§c❀ 您输入的内容无效,已退出")
            return None, None, None, None
        fmts.print_inf(f"\n§a❀ §b请输入您想要导入到维度{dim}的Y坐标 §e(输入整数)")
        try:
            y = int(input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出")).strip())
        except ValueError:
            fmts.print_inf("§c❀ 您输入的内容无效,已退出")
            return None, None, None, None
        fmts.print_inf(f"\n§a❀ §b请输入您想要导入到维度{dim}的Z坐标 §e(输入整数)")
        try:
            z = int(input(fmts.fmt_info("§a❀ §b输入 §c其他内容 §b退出")).strip())
        except ValueError:
            fmts.print_inf("§c❀ 您输入的内容无效,已退出")
            return None, None, None, None
        return dim, x, y, z
