import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from tooldelta import fmts
from tooldelta.constants import PacketIDS
from .lib import YieldCommand

if TYPE_CHECKING:
    from . import BDX_BDump


def do_operations(
    sys: "BDX_BDump",
    base_pos: tuple[int, int, int],
    progress_bar_func: Callable[[int], None],
    progress_delay: float = 1.0,
    speed: float = 1000,
):
    fmts.print("开始导入 (进度显示于游戏内)")
    bot_selector = sys.game_ctrl.players.getBotInfo().getSelector()
    sendwocmd = sys.game_ctrl.sendwocmd
    pos_x, pos_y, pos_z = base_pos
    bot_x, bot_y, bot_z = pos_x, pos_y, pos_z
    string_pool: list[str] = []
    timer = 0
    build_blocks = 0
    sleeptime = 1 / speed

    def speed_limit():
        time.sleep(sleeptime)

    def ensure_pos():
        nonlocal pos_x, pos_y, pos_z, bot_x, bot_y, bot_z
        if abs(pos_x - bot_x) > 32 or abs(pos_z - bot_z) > 32:
            sendwocmd(f"execute as {bot_selector} at @s run tp {pos_x} {pos_y} {pos_z}")
            bot_x, bot_y, bot_z = pos_x, pos_y, pos_z
            time.sleep(0.02)

    def setblock_here(block_id: str, block_state_or_data: str | int):
        nonlocal build_blocks
        speed_limit()
        cmd = f"execute as {bot_selector} at @s run setblock {pos_x} {pos_y} {pos_z} {block_id} {block_state_or_data}"
        sendwocmd(cmd)
        build_blocks += 1

    for id, operation in YieldCommand():
        match id:
            case 1:
                string = operation["ConstantString"]
                string_pool.append(string)
            case 5:
                BlockConstantStringID = operation["BlockConstantStringID"]
                BlockStatesConstantStringID = operation["BlockStatesConstantStringID"]
                ensure_pos()
                setblock_here(
                    string_pool[BlockConstantStringID],
                    string_pool[BlockStatesConstantStringID],
                )
            case 6:
                Value = operation["Value"]
                pos_z += Value
            case 7:
                BlockConstantStringID = operation["BlockConstantStringID"]
                BlockData = operation["BlockData"]
                ensure_pos()
                setblock_here(string_pool[BlockConstantStringID], BlockData)
            case 8:
                pos_z += 1
            case 9:
                pass
            case 12:
                Value = operation["Value"]
                pos_z += Value
            case 13:
                BlockConstantStringID = operation["BlockConstantStringID"]
                BlockStatesString = operation["BlockStatesString"]
                ensure_pos()
                setblock_here(string_pool[BlockConstantStringID], BlockStatesString)
            case 14:
                pos_x += 1
            case 15:
                pos_x -= 1
            case 16:
                pos_y += 1
            case 17:
                pos_y -= 1
            case 18:
                pos_z += 1
            case 19:
                pos_z -= 1
            case 20 | 21 | 28:
                Value = operation["Value"]
                pos_x += Value
            case 22 | 23 | 29:
                Value = operation["Value"]
                pos_y += Value
            case 24 | 25 | 30:
                Value = operation["Value"]
                pos_z += Value
            case 26 | 27 | 36:
                CommandBlockData = operation["CommandBlockData"]
                Mode = CommandBlockData["Mode"]
                Command = CommandBlockData["Command"]
                CustomName = CommandBlockData["CustomName"]
                # LastOutput = CommandBlockData["LastOutput"]
                TickDelay = CommandBlockData["TickDelay"]
                ExecuteOnFirstTick = CommandBlockData["ExecuteOnFirstTick"]
                TrackOutput = CommandBlockData["TrackOutput"]
                Conditional = CommandBlockData["Conditional"]
                NeedsRedstone = CommandBlockData["NeedsRedstone"]
                pk = sys.interact.make_packet_command_block_update(
                    (pos_x, pos_y, pos_z),
                    Command,
                    Mode,
                    NeedsRedstone,
                    TickDelay,
                    Conditional,
                    CustomName,
                    TrackOutput,
                    ExecuteOnFirstTick,
                )
                ensure_pos()
                if id == 27 or id == 36:
                    if id == 27:
                        BlockConstantStringID = operation["BlockConstantStringID"]
                        BlockID = string_pool[BlockConstantStringID]
                    else:
                        BlockID = "command_block"
                    BlockData = operation["BlockData"]
                    setblock_here(BlockID, BlockData)
                    time.sleep(0.05)
                else:
                    speed_limit()
                sys.game_ctrl.sendPacket(PacketIDS.CommandBlockUpdate, pk)
            case 31:
                sys.print("§6未实现: UseRuntimeIDPool")
            case 32:
                sys.print("§6未实现: PlaceRuntimeBlock")
            case 33:
                sys.print("§6未实现: PlaceRuntimeBlockWithUint32RuntimeID")
            case 34:
                sys.print("§6未实现: PlaceRuntimeBlockWithCommandBlockData")
            case 35:
                raise NotImplementedError(
                    "PlaceRuntimeBlockWithCommandBlockDataAndUint32RuntimeID"
                )
            case 37:
                sys.print("§6未实现: PlaceRuntimeBlockWithChestData")
            case 38:
                sys.print(
                    "§6未实现: PlaceRuntimeBlockWithChestDataAndUint32RuntimeID"
                )
            case 39:
                sys.print(f"bdx 的 debug 信息: {operation['Data']}")
            case 40:
                sys.print("§6未实现: PlaceBlockWithChestData")
            case 41:
                BlockConstantStringID = operation["BlockConstantStringID"]
                BlockStatesConstantStringID = operation["BlockStatesConstantStringID"]
                setblock_here(string_pool[BlockConstantStringID], string_pool[BlockStatesConstantStringID])
            case 88:
                break
        if (nowtime := time.time()) - timer > progress_delay:
            timer = nowtime
            progress_bar_func(build_blocks)
