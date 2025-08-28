from typing import TYPE_CHECKING
from .file import MCFProjectFile
from .define import GO_POSITION, Facing

if TYPE_CHECKING:
    from . import SilverwolfLoadAndExport


def load_from_file(
    sys: "SilverwolfLoadAndExport",
    file: MCFProjectFile,
    rel_x: int,
    rel_y: int,
    rel_z: int,
):
    intr = sys.intr
    sys.game_ctrl.sendcmd(f"tp {rel_x} {rel_y} {rel_z}")
    px = 0
    py = 0
    pz = 0
    for cb in file.cbs:
        intr.place_command_block(
            intr.make_packet_command_block_update(
                (rel_x + px, rel_y + py, rel_z + pz),
                cb.command,
                cb.type,
                cb.need_redstone,
                cb.tick_delay,
                cb.conditional,
                should_track_output=cb.should_track_output,
                execute_on_first_tick=cb.execute_on_first_tick,
            ),
            facing = cb.facing
        )
        facing = Facing(cb.facing)
        go_x, go_y, go_z = GO_POSITION[facing]
        px += go_x
        py += go_y
        pz += go_z
        sys.game_ctrl.sendcmd(f"tp {rel_x + px} {rel_y + py} {rel_z + pz}")
