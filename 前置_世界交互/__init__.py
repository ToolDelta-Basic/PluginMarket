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
        """
        生成数据包包体

        Args:
            position (tuple[int, int, int]): 坐标
            command (str): 指令
            mode (int, optional): 模式 (0: 脉冲, 1: 循环, 2: 连锁). Defaults to 0.
            need_redstone (bool, optional): 是否需要红石. Defaults to False.
            tick_delay (int, optional): 刻度延迟. Defaults to 0.
            conditional (bool, optional): 是否有条件. Defaults to False.
            name (str, optional): 名称. Defaults to "".
            should_track_output (bool, optional): 是否显示输出. Defaults to True.
            execute_on_first_tick (bool, optional): 是否在第一刻执行. Defaults to True.

        Returns:
            _type_: _description_
        """
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
        self,
        command_block_update_packet,
        facing=0,
        limit_seconds=0.5,
        limit_seconds2=0.5,
    ):
        """
        发出放置方块数据包

        Args:
            command_block_update_packet (_type_): 数据包包体
            facing (int, optional): 朝向. Defaults to 0.
            limit_seconds (float, optional): 从tp到放置方块的延迟. Defaults to 0.5.
            limit_seconds2 (float, optional): 从放置方块到写入命令的延迟. Defaults to 0.5.

        Raises:
            ValueError: _description_
        """
        cmd = (
            "/setblock "
            + " ".join([str(i) for i in command_block_update_packet["Position"]])
            + " "
            + ["", "repeating_", "chain_"][command_block_update_packet["Mode"]]
            + "command_block "
            + str(facing)
        )
        # 传入参数: 为 make_packet_command_block_update 方法的返回的第二个值
        if limit_seconds > 0:
            self.game_ctrl.sendcmd(
                "/tp "
                + " ".join([str(i) for i in command_block_update_packet["Position"]])
            )
            self.game_ctrl.sendwocmd(cmd)
            time.sleep(limit_seconds)
        else:
            self.game_ctrl.sendcmd_with_resp(
                "/tp "
                + " ".join([str(i) for i in command_block_update_packet["Position"]])
            )
            resp = self.game_ctrl.sendcmd_with_resp(cmd)
            if resp.SuccessCount == 0:
                raise ValueError(f"无法放置命令方块方块: {resp.OutputMessages[0].Message}")
        time.sleep(limit_seconds2)
        self.game_ctrl.sendPacket(78, command_block_update_packet)
