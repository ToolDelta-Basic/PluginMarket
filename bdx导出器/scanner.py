from typing import TYPE_CHECKING
from tooldelta import Print
from .BDXConverter import BDX, Operation, GeneralClass
from .utils import snake_folding, yield_4chunks
from .struct_loader import load_chest, load_command_block
from .state_dump import dump_block_states

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
    sys.game_ctrl.sendcmd_with_resp(f"tp {x} {y} {z}")
    return sys.intr.get_structure((x, y, z), (sizex, sizey, sizez))


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
    dy = endy - starty
    for x, z, rel_x, rel_z in yield_4chunks(startx, startz, endx, endz):
        sizex, sizez = min(64, endx - x + 1), min(64, endz - z + 1)
        Print.print_inf(
            f"正在导出 {x}, {starty}, {z} ~ {x + sizex}, {endy}, {z + sizez}       ", end = "\r"
        )
        structure = get_structure(sys, x, starty, z, sizex, dy, sizez)
        structures.append((structure, (rel_x, starty, rel_z)))
    return structures


def structures_to_bdx(structures: list[tuple["Structure", POS]]):
    def add_operation(op: GeneralClass):
        bdx.BDXContents.append(op)

    bdx = BDX()
    bdx.AuthorName = "TD-BdxExporter/Trim-BdxConverter"
    global_constants_pool: dict[str, int] = {}
    now_x, now_y, now_z = 0, None, 0
    for structure, (rel_x, rel_y, rel_z) in structures:
        if now_y is None:
            now_y = rel_y
        if (dx := rel_x - now_x) != 0:
            # if dx < -64 or dx > 64:
            #     raise ValueError(f"Error AddIntXValue: {dx}")
            (op := Operation.AddInt8XValue()).value = dx
            add_operation(op)
        if (dy := rel_y - now_y) != 0:
            (op := Operation.AddInt8YValue()).value = dy
            add_operation(op)
        if (dz := rel_z - now_z) != 0:
            # if dz < -64 or dz > 64:
            #     raise ValueError(f"Error AddIntZValue: {dz}")
            (op := Operation.AddInt8ZValue()).value = dz
            add_operation(op)
        now_x, now_y, now_z = write_structure_into_bdx(
            global_constants_pool, structure, (rel_x, rel_y, rel_z), bdx
        )
    return bdx


def write_structure_into_bdx(
    global_constants_pool: dict[str, int],
    structure: "Structure",
    relative_pos: POS,
    bdx: BDX,
):
    # 在使用该方法前
    # 请先把画笔移动至该区域的 (0, 0, 0) 处
    def add_operation(op: GeneralClass):
        bdx.BDXContents.append(op)

    def get_index(string: str):
        index = global_constants_pool.get(string)
        if index is None:
            index = len(global_constants_pool)
            global_constants_pool[string] = index
            (op := Operation.CreateConstantString()).constantString = string
            add_operation(op)
        return index

    rx, ry, rz = relative_pos
    now_x, now_y, now_z = 0, 0, 0
    for x, y, z in snake_folding(structure.sizex, structure.sizey, structure.sizez):
        sub_x_val = x - now_x
        sub_y_val = y - now_y
        sub_z_val = z - now_z
        if sub_x_val == 1:
            add_operation(Operation.AddXValue())
        elif sub_x_val == -1:
            add_operation(Operation.SubtractXValue())
        elif sub_x_val != 0:
            raise ValueError(f"SubXValue Error: {sub_x_val}")
        if sub_y_val == 1:
            add_operation(Operation.AddYValue())
        elif sub_y_val == -1:
            add_operation(Operation.SubtractYValue())
        elif sub_y_val != 0:
            raise ValueError(f"SubYValue Error: {sub_y_val}")
        if sub_z_val == 1:
            add_operation(Operation.AddZValue())
        elif sub_z_val == -1:
            add_operation(Operation.SubtractZValue())
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
            op = Operation.PlaceBlockWithChestData()
            op.blockConstantStringID = index
            op.blockData = block.val
            op.data = chest_data
            op.slotCount = chest_data.slotCount
        # 是命令方块
        elif bname.endswith("command_block"):
            op = load_command_block(block.metadata, block.states)
            op.mode = {
                "minecraft:command_block": 0,
                "minecraft:repeating_command_block": 1,
                "minecraft:chain_command_block": 2,
            }[block.name]
            op.data = block.val
            add_operation(op)
            print("add_op")
        # 其他的暂时当普通方块处理
        elif block.states:
            states_str = dump_block_states(block.states)
            op = Operation.PlaceBlockWithBlockStates()
            op.blockConstantStringID = index
            op.blockStatesConstantStringID = get_index(states_str)
            add_operation(op)
        else:
            op = Operation.PlaceBlock()
            op.blockConstantStringID = index
            op.blockData = block.val
            add_operation(op)

    return rx + now_x, ry + now_y, rz + now_z
