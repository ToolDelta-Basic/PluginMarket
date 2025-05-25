import json
from ..conversion import lua_table_to_python

class Builder:
    def __init__(self, omega):
        self.omega = omega
        self.game_ctrl = self.omega.game_ctrl
        self.world_interactive = self.omega.world_interactive
        self.command_modes = [
            "command_block",
            "repeating_command_block",
            "chain_command_block"
        ]
        self.dimensions = [
            "overworld",
            "nether",
            "the_end"
        ]

    def place_command_block(self, pos, block_name, block_data,
        need_red_stone, conditional,
        command, name,
        tick_delay, track_output, execute_on_first_tick
    ):
        pos = lua_table_to_python(pos)
        command_mode = block_name
        if block_name in self.command_modes:
            command_mode = self.command_modes.index(block_name)
        command_block_update_packet = self.world_interactive.make_packet_command_block_update(
            position = [pos["x"], pos["y"], pos["z"]],
            command = command,
            mode = command_mode,
            need_redstone = need_red_stone,
            tick_delay = tick_delay,
            conditional = conditional,
            name = name,
            should_track_output = track_output,
            execute_on_first_tick = execute_on_first_tick
        )
        dimension_id = json.loads(self.game_ctrl.sendwscmd("/querytarget @s", True).as_dict["OutputMessages"][0]["Parameters"][0])[0]["dimension"]
        dimension = f"dim{dimension_id}"
        if dimension_id < len(self.dimensions):
            dimension = self.dimensions[dimension_id]
        self.world_interactive.place_command_block(
            command_block_update_packet,
            facing = block_data,
            limit_seconds = 0.5,
            limit_seconds2 = 0.0,
            in_dim = dimension
        )