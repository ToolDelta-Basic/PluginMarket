import time
from typing import TYPE_CHECKING, Dict, Any, Tuple
if TYPE_CHECKING:
    from . import MCAgent

class CommandBlockTool:
    def __init__(self, plugin: "MCAgent"):
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl

    @staticmethod
    def make_packet_command_block_update(
        position: Tuple[int, int, int],
        command: str,
        mode: int = 0,
        need_redstone: bool = False,
        tick_delay: int = 0,
        conditional: bool = False,
        name: str = "",
        should_track_output: bool = True,
        execute_on_first_tick: bool = True,
    ) -> Dict[str, Any]:
        return {
            "Block": True,
            "Position": list(position),
            "Mode": mode,
            "NeedsRedstone": need_redstone,
            "Conditional": conditional,
            "MinecartEntityRuntimeID": 0,
            "Command": command,
            "LastOutput": "",
            "Name": name,
            "ShouldTrackOutput": should_track_output,
            "TickDelay": tick_delay,
            "ExecuteOnFirstTick": execute_on_first_tick,
        }

    def _place_command_block_internal(
        self,
        command_block_update_packet: Dict[str, Any],
        facing: int = 0,
        limit_seconds: float = 0.0,
        limit_seconds2: float = 0.0,
        in_dim: str = "overworld",
    ):
        mode_prefix = ["", "repeating_", "chain_"][command_block_update_packet["Mode"]]
        position = command_block_update_packet["Position"]
        cmd = f"/setblock {position[0]} {position[1]} {position[2]} {mode_prefix}command_block {facing}"

        tp_cmd = f"/execute at @s in {in_dim} run tp {position[0]} {position[1]} {position[2]}"

        if limit_seconds > 0:
            self.game_ctrl.sendcmd(tp_cmd)
            self.game_ctrl.sendcmd(cmd)
            time.sleep(limit_seconds)
        else:
            tp_result = self.game_ctrl.sendwscmd_with_resp(tp_cmd)
            if tp_result.SuccessCount == 0:
                raise ValueError("无法tp至对应坐标")

            setblock_result = self.game_ctrl.sendwscmd_with_resp(cmd)
            if setblock_result.SuccessCount == 0 and "noChange" not in setblock_result.OutputMessages[0].Message:
                raise ValueError(f"无法放置命令方块: {setblock_result.OutputMessages[0].Message}")

        time.sleep(limit_seconds2)
        self.game_ctrl.sendPacket(78, command_block_update_packet)

    def place_command_block(
        self,
        x: int,
        y: int,
        z: int,
        command: str,
        mode: int = 0,
        facing: int = 0,
        need_redstone: bool = False,
        tick_delay: int = 0,
        conditional: bool = False,
        name: str = "",
        should_track_output: bool = True,
        execute_on_first_tick: bool = True,
        in_dim: str = "overworld"
    ) -> Dict[str, Any]:
        try:
            packet = self.make_packet_command_block_update(
                position=(x, y, z),
                command=command,
                mode=mode,
                need_redstone=need_redstone,
                tick_delay=tick_delay,
                conditional=conditional,
                name=name,
                should_track_output=should_track_output,
                execute_on_first_tick=execute_on_first_tick
            )

            self._place_command_block_internal(
                command_block_update_packet=packet,
                facing=facing,
                limit_seconds=0.0,
                limit_seconds2=0.0,
                in_dim=in_dim
            )

            mode_names = {0: "脉冲", 1: "循环", 2: "连锁"}
            mode_name = mode_names.get(mode, "未知")

            return {
                "success": True,
                "message": f"已在 ({x}, {y}, {z}) 放置{mode_name}命令方块",
                "position": {"x": x, "y": y, "z": z},
                "command": command,
                "mode": mode_name,
                "facing": facing,
                "dimension": in_dim
            }

        except ValueError as e:
            return {
                "success": False,
                "error": f"放置命令方块失败: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"放置命令方块异常: {str(e)}"
            }

    def place_impulse_command_block(
        self,
        x: int,
        y: int,
        z: int,
        command: str,
        facing: int = 0,
        need_redstone: bool = False,
        name: str = "",
        in_dim: str = "overworld"
    ) -> Dict[str, Any]:
        return self.place_command_block(
            x=x, y=y, z=z,
            command=command,
            mode=0,
            facing=facing,
            need_redstone=need_redstone,
            name=name,
            in_dim=in_dim
        )

    def place_repeating_command_block(
        self,
        x: int,
        y: int,
        z: int,
        command: str,
        facing: int = 0,
        need_redstone: bool = False,
        tick_delay: int = 0,
        name: str = "",
        in_dim: str = "overworld"
    ) -> Dict[str, Any]:
        return self.place_command_block(
            x=x, y=y, z=z,
            command=command,
            mode=1,
            facing=facing,
            need_redstone=need_redstone,
            tick_delay=tick_delay,
            name=name,
            in_dim=in_dim
        )

    def place_chain_command_block(
        self,
        x: int,
        y: int,
        z: int,
        command: str,
        facing: int = 0,
        conditional: bool = False,
        tick_delay: int = 0,
        name: str = "",
        in_dim: str = "overworld"
    ) -> Dict[str, Any]:
        return self.place_command_block(
            x=x, y=y, z=z,
            command=command,
            mode=2,
            facing=facing,
            conditional=conditional,
            tick_delay=tick_delay,
            name=name,
            in_dim=in_dim
        )
