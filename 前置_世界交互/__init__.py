from tooldelta import plugins, Frame, Plugin
import time

plugins.checkSystemVersion((0, 3, 20))


# 使用 api = plugins.get_plugin_api("前置-世界交互") 来获取到这个api
@plugins.add_plugin_as_api("前置-世界交互")
class GameInteractive(Plugin):
    name = "前置-世界交互"
    author = "SuperScript"
    description = "前置插件, 提供世界交互功能的数据包, etc."
    version = (0, 0, 4)

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()

    @staticmethod
    def make_packet_command_block_update(
        position: tuple[int, int, int],
        command: str,
        mode: int = 0,
        need_redstone: bool = False,
        tick_delay: int = 0,
        conditional: bool = False,
        name: str = "",
        should_track_output: bool = True,
        execute_on_first_tick: bool = True,
    ):
        myPacket = {
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
        return myPacket

    def place_command_block(
        self, command_block_update_packet, facing=0, limit_seconds=0.5
    ):
        cmd = (
            "/setblock "
            + " ".join([str(i) for i in command_block_update_packet["Position"]])
            + " "
            + ["", "repeating_", "chain_"][command_block_update_packet["Mode"]]
            + "command_block "
            + str(facing)
        )
        # 传入参数: 为 make_packet_command_block_update 方法的返回的第二个值
        self.game_ctrl.sendwocmd(
            "/tp " + " ".join([str(i) for i in command_block_update_packet["Position"]])
        )
        self.game_ctrl.sendwocmd(cmd)
        time.sleep(limit_seconds)
        self.game_ctrl.sendPacket(78, command_block_update_packet)
