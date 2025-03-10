import os
import json
import ctypes
from dataclasses import dataclass
from tooldelta import Plugin, game_utils, Config, Print, utils, plugin_entry

from tooldelta.neo_libs.neo_conn import LIB

LIB.RenameItemWithAnvil.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int32,
    ctypes.c_int,
    ctypes.c_char_p,
]
LIB.RenameItemWithAnvil.restype = ctypes.c_char_p
LIB.GetBlockRuntimeID.restype = ctypes.c_int32


@dataclass
class Item:
    name: str
    id: str
    data: int
    tag: dict | None


def PyString(n: bytes):
    return n.decode() if n is not None else None


class TDItemMaker(Plugin):
    name = "特殊物品制作器"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["mkitem", "制作物品"], None, "以制作物品", self.on_menu
        )

    def on_menu(self, _):
        fs = os.listdir(self.data_path)
        if fs == []:
            Print.print_inf("物品数据文件夹空空如也...")
            Print.print_inf("可在插件管理器界面选择该插件， 选择查看手册以查看教程")
            return
        for i, file in enumerate(fs):
            Print.print_inf(f"{i + 1} - {file}")
        resp = utils.try_int(input(Print.fmt_info("请输入序号以选择:")))
        if resp is None or resp not in range(1, len(fs) + 1):
            Print.print_err("无效选项")
            return
        with open(os.path.join(self.data_path, fs[resp - 1]), encoding="utf-8") as f:
            content = f.read()
        try:
            items = self.parse_to_items(fs[resp - 1], content)
        except Exception as err:
            Print.print_err(str(err))
            return
        self.make_items(items)

    @utils.thread_func("制作特殊物品")
    def make_items(self, items: list[Item]):
        x, y, z = game_utils.getPosXYZ(self.game_ctrl.bot_name)
        x, y, z = int(x), int(y), int(z)
        self.game_ctrl.sendwocmd(f"setblock {x} {y - 1} {z} bedrock")
        self.game_ctrl.sendwocmd(f"setblock {x} {y} {z} anvil")
        for item in items:
            if not item.name.startswith("§r"):
                item.name = "§r" + item.name
            self.create_new_item_and_drop(
                (x, y, z), item.id, item.name, item.data, item.tag
            )
        Print.print_suc("全部物品制作完成")

    def parse_to_items(self, filename: str, content: str):
        STD = Config.JsonList(
            {"名称": str, "ID": str, "特殊值": int, "标签属性": (dict, type(None))}
        )
        try:
            Config.check_auto(STD, ct := json.loads(content))
        except (json.JSONDecodeError, Config.ConfigError) as err:
            raise ValueError(f"解析 {filename} 失败: {err}")
        items: list[Item] = []
        for c in ct:
            items.append(Item(c["名称"], c["ID"], c["特殊值"], c["标签属性"]))
        return items

    def rename_item(self, item_new_name: str, pos: tuple[int, int, int]):
        x, y, z = pos
        anvil_runtimeid = LIB.GetBlockRuntimeID(b"anvil")
        assert anvil_runtimeid != -1
        return PyString(
            LIB.RenameItemWithAnvil(
                x,
                y,
                z,
                anvil_runtimeid,
                0,
                item_new_name.encode(),
            )
        )

    def create_new_item_and_drop(
        self,
        pos: tuple[int, int, int],
        item_id: str,
        name: str,
        item_data: int,
        item_tags: dict | None,
    ):
        tag_str = json.dumps(item_tags, ensure_ascii=False) if item_tags else ""
        result = self.game_ctrl.sendcmd_with_resp(
            f"replaceitem entity @a[name={self.game_ctrl.bot_name}] slot.hotbar 0 {item_id} 1 {item_data} {tag_str}"
        )
        if result.SuccessCount == 0:
            Print.print_err("§c物品制作： 制作失败, 无法执行replaceitem指令")
            return
        if err := self.rename_item(name, pos):
            Print.print_err(f"物品制作失败: {err}")
            return


entry = plugin_entry(TDItemMaker)
