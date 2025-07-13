from typing import TYPE_CHECKING
from time import time
from tooldelta import fmts
from .bdx_utils.writer import BDXContentWriter
from .utils import snake_folding, yield_4chunks
from .struct_loader import load_chest
from .state_dump import dump_block_states
from .progress_bar import progress_bar

if TYPE_CHECKING:
    from . import BDXExporter
    from . import Structure

POS = tuple[int, int, int]


def get_structure(
    sys: "BDXExporter",
    x: int,
    y: int,
    z: int,
    sizex: int,
    sizey: int,
    sizez: int,
):
    sys.game_ctrl.sendcmd(f"tp {x} {y} {z}")
    fmts.print_inf(
        f"正在获取 {x}, {y}, {z} ~ {x + sizex}, {y + sizey}, {z + sizez}       ",
        end="\r",
    )
    r = sys.intr._request_structure_and_get((x, y, z), (sizex, sizey, sizez))
    fmts.print_inf(
        f"正在解析结构 {x}, {y}, {z} ~ {x + sizex}, {y + sizey}, {z + sizez}       ",
        end="\r",
    )
    return sys.intr.Structure(r)


def export_to_structures(
    sys: "BDXExporter",
    startx: int,
    starty: int,
    startz: int,
    endx: int,
    endy: int,
    endz: int,
):
    structures: list[tuple["Structure", POS]] = []
    startx, endx = min(startx, endx), max(startx, endx)
    starty, endy = min(starty, endy), max(starty, endy)
    startz, endz = min(startz, endz), max(startz, endz)
    dy = endy - starty + 1
    for x, z, rel_x, rel_z in yield_4chunks(startx, startz, endx, endz):
        sizex, sizez = min(64, endx - x + 1), min(64, endz - z + 1)
        res = sys.game_ctrl.sendwscmd_with_resp(f"tp {x} 0 {z}")
        if res.SuccessCount == 0:
            raise ValueError("Error RequestStructure: TP")
        structure = get_structure(sys, x, starty, z, sizex, dy, sizez)
        structures.append((structure, (rel_x, starty, rel_z)))
    return structures


# 241 -60 11
# 769 317 -206


def structures_to_bdx(structures: list[tuple["Structure", POS]]) -> BDXContentWriter:
    bdx_content = BDXContentWriter()
    global_constants_pool: dict[str, int] = {}
    now_x, now_y, now_z = 0, None, 0
    for structure, (rel_x, rel_y, rel_z) in structures:
        fmts.print_inf(
            f"正在转换结构 {structure.x}, {structure.y}, {structure.z} ~ {structure.x + structure.sizex}, {structure.y + structure.sizey}, {structure.z + structure.sizez}       ",
            end="\r",
        )
        if now_y is None:
            now_y = rel_y
        if (dx := rel_x - now_x) != 0:
            if dx <= -128 or dx >= 128:
                raise ValueError(f"Error AddIntXValue: {dx}")
            bdx_content.AddInt8XValue(dx)
        if (dy := rel_y - now_y) != 0:
            if dy <= -128 or dy >= 128:
                bdx_content.AddInt16YValue(dy)
            else:
                bdx_content.AddInt8YValue(dy)
        if (dz := rel_z - now_z) != 0:
            if dz <= -128 or dz >= 128:
                raise ValueError(f"Error AddIntZValue: {dz}")
            bdx_content.AddInt8ZValue(dz)
        now_x, now_y, now_z = write_structure_into_bdx(
            global_constants_pool, structure, (rel_x, rel_y, rel_z), bdx_content
        )
    return bdx_content


def write_structure_into_bdx(
    global_constants_pool: dict[str, int],
    structure: "Structure",
    relative_pos: POS,
    bdx_content: BDXContentWriter,
):
    # 在使用该方法前
    # 请先把画笔移动至该区域的 (0, 0, 0) 处

    def get_index(string: str):
        index = global_constants_pool.get(string)
        if index is None:
            index = len(global_constants_pool)
            global_constants_pool[string] = index
            bdx_content.CreateConstantString(string)
        return index

    rx, ry, rz = relative_pos
    now_x, now_y, now_z = 0, 0, 0
    wtime = time()
    counter = 0
    last_1s_counter = 0
    size = structure.sizex * structure.sizey * structure.sizez
    for x, y, z in snake_folding(structure.sizex, structure.sizey, structure.sizez):
        counter += 1
        if (ntime := time()) - wtime >= 1:
            wtime = ntime
            fmts.print_inf(f"正在转换结构 {progress_bar(counter, size)} {counter - last_1s_counter}操作/s", end="\r")
            last_1s_counter = counter

        sub_x_val = x - now_x
        sub_y_val = y - now_y
        sub_z_val = z - now_z
        if sub_x_val == 1:
            bdx_content.AddXValue()
        elif sub_x_val == -1:
            bdx_content.SubtractXValue()
        elif sub_x_val != 0:
            raise ValueError(f"SubXValue Error: {sub_x_val}")
        if sub_y_val == 1:
            bdx_content.AddYValue()
        elif sub_y_val == -1:
            bdx_content.SubtractYValue()
        elif sub_y_val != 0:
            raise ValueError(f"SubYValue Error: {sub_y_val}")
        if sub_z_val == 1:
            bdx_content.AddZValue()
        elif sub_z_val == -1:
            bdx_content.SubtractZValue()
        elif sub_z_val != 0:
            raise ValueError(f"SubZValue Error: {sub_z_val}")
        now_x, now_y, now_z = x, y, z
        block = structure.get_block((x, y, z))
        bname = block.name
        if bname == "minecraft:air":
            continue
        index = get_index(bname)
        # 是箱子类容器
        if (
            bname == "minecraft:chest"
            or bname == "minecraft:trapped_chest"
            or bname == "minecraft:barrel"
            or bname.endswith("shulker_box")
        ):
            chest_data = load_chest(block.metadata)
            bdx_content.PlaceBlockWithChestData(index, block.val, 27, chest_data)
        # 是命令方块
        elif bname.endswith("command_block"):
            cb_data = block.metadata
            cb_states = block.states
            mode = {
                "minecraft:command_block": 0,
                "minecraft:repeating_command_block": 1,
                "minecraft:chain_command_block": 2,
            }[block.name]
            bdx_content.PlaceCommandBlockWithCommandBlockData(
                block.val, mode, cb_data["Command"], cb_data["CustomName"], cb_data["LastOutput"],
                cb_data["TickDelay"], cb_data["ExecuteOnFirstTick"],  cb_data["TrackOutput"],
                cb_states["conditional_bit"], not cb_data["auto"]
            )
        # 其他的暂时当普通方块处理
        elif block.states:
            states_str = dump_block_states(block.states)
            bdx_content.PlaceBlockWithBlockStates(index, get_index(states_str))
        else:
            bdx_content.PlaceBlock(index, block.val)

    return rx + now_x, ry + now_y, rz + now_z
