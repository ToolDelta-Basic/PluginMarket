import time
import numpy
from typing import Any
from json import dumps as stringfy
from dataclasses import dataclass
from tooldelta import plugins, Frame, Plugin, Utils, Print
from tooldelta.constants import PacketIDS
from tooldelta.launch_cli import FrameEulogistLauncher

plugins.checkSystemVersion((0, 3, 20))


@dataclass
class Block:
    "记录了结构中某一坐标的方块的数据"

    name: str
    "方块ID"
    states: dict[str, Any]
    "方块状态数据"
    val: int
    "方块特殊值"
    version: int
    "此方块的世界版本"
    metadata: Any
    "方块的 NBT 信息"


class Structure:
    "记录了获取的世界结构 (暂未实现获取实体数据)"

    def __init__(self, structure_json):
        structure = structure_json["StructureTemplate"]["structure"]
        block_matrix = structure["block_indices"][0]
        block_palettes = structure["palette"]["default"]["block_palette"]
        self.x, self.y, self.z = structure_json["StructureTemplate"][
            "structure_world_origin"
        ]
        self._block_matrix = numpy.array(block_matrix, dtype=numpy.uint16)
        self._palette = [
            (i["name"], i["states"], i["val"], i["version"]) for i in block_palettes
        ]
        self.sizex, self.sizey, self.sizez = structure_json["StructureTemplate"]["size"]
        self._pos_block_data = {}
        for v in structure["palette"]["default"]["block_position_data"].values():
            v = v["block_entity_data"]
            self._pos_block_data[
                (v["x"] - self.x, v["y"] - self.y, v["z"] - self.z)
            ] = v

    def get_block(self, position: tuple[int, int, int]) -> Block:
        """
        获取该结构中的一个方块的数据。

        Args:
            position (tuple[int, int, int]): 此方块在结构内的相对坐标

        Raises:
            ValueError: 超出结构尺寸

        Returns:
            Block: 方块数据类
        """
        x, y, z = position
        if (
            x not in range(self.sizex)
            or y not in range(self.sizey)
            or z not in range(self.sizez)
        ):
            raise ValueError(f"超出结构尺寸: ({x}, {y}, {z})")
        index = self._block_matrix[x * self.sizey * self.sizez + y * self.sizez + z]
        name, states, val, version = self._palette[index]
        metadata = self._pos_block_data.get((x, y, z))
        return Block(name, states, val, version, metadata)


# 使用 api = plugins.get_plugin_api("前置-世界交互") 来获取到这个api
@plugins.add_plugin_as_api("前置-世界交互")
class GameInteractive(Plugin):
    name = "前置-世界交互"
    author = "SuperScript"
    description = "前置插件, 提供世界交互功能的数据包, etc."
    version = (0, 0, 5)

    Structure = Structure
    Block = Block

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.structure_cbs = {}

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["getnbt"], "[x] [y] [z]", "获取指定坐标的方块的NBT", self.on_get_nbt
        )

    @plugins.add_packet_listener(PacketIDS.IDStructureTemplateDataResponse)
    def on_structure_pkt(self, pk):
        xyz = tuple(pk["StructureTemplate"]["structure_world_origin"])
        if xyz in self.structure_cbs.keys():
            self.structure_cbs[xyz].pop()(pk)
            if self.structure_cbs[xyz] == []:
                del self.structure_cbs[xyz]
        return False

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
        limit_seconds=0.0,
        limit_seconds2=0.0,
        in_dim="overworld",
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
                f"/execute at @s in {in_dim} run tp "
                + " ".join([str(i) for i in command_block_update_packet["Position"]])
            )
            self.game_ctrl.sendcmd(cmd)
            time.sleep(limit_seconds)
        else:
            if (
                self.game_ctrl.sendcmd_with_resp(
                    f"/execute at @s in {in_dim} run tp "
                    + " ".join(
                        [str(i) for i in command_block_update_packet["Position"]]
                    )
                ).SuccessCount
                == 0
            ):
                raise ValueError("无法tp至对应坐标")
            resp = self.game_ctrl.sendcmd_with_resp(cmd)
            if (
                resp.SuccessCount == 0
                and "noChange" not in resp.OutputMessages[0].Message
            ):
                raise ValueError(
                    f"无法放置命令方块方块: {resp.OutputMessages[0].Message}"
                )
        time.sleep(limit_seconds2)
        self.game_ctrl.sendPacket(78, command_block_update_packet)

    def get_structure(
        self, position: tuple[int, int, int], size: tuple[int, int, int]
    ) -> Structure:
        """
        在 Bot 所处维度获取一个特定位置和大小的结构方块结构

        Args:
            position (tuple[int, int, int]): 坐标
            size (tuple[int, int, int]): 结构尺寸

        Returns:
            Structure: 结构数据类
        """
        structure = self._request_structure_and_get(position, size)
        return Structure(structure)

    def on_get_nbt(self, args):
        try:
            x, y, z = (int(i) for i in args)
        except ValueError:
            Print.print_err("参数错误")
            return
        try:
            res = self.get_structure((x, y, z), (2, 2, 2))
        except Exception as err:
            Print.print_err(f"获取结构错误: {err}")
            return
        block = res.get_block((0, 0, 0))
        Print.print_inf(f"目标方块ID: {block.name}, 特殊值: {block.val}, 状态: {block.states} NBT数据:")
        Print.print_inf(stringfy(block.metadata, indent=2, ensure_ascii=False))

    def _request_structure_and_get(
        self, position: tuple[int, int, int], size: tuple[int, int, int], timeout=5.0
    ):
        pk = {
            "StructureName": "mystructure:a",
            "Position": list(position),
            "Settings": {
                "PaletteName": "default",
                "IgnoreEntities": True,
                "IgnoreBlocks": False,
                "Size": list(size),
                "Offset": [0, 0, 0],
                "LastEditingPlayerUniqueID": self.bot_ud,
                "Rotation": 0,
                "Mirror": 0,
                "Integrity": 100,
                "Seed": 0,
                "AllowNonTickingChunks": False,
            },
            "RequestType": 1,
        }
        self.game_ctrl.sendPacket(PacketIDS.IDStructureTemplateDataRequest, pk)
        getter, setter = Utils.create_result_cb()
        self.structure_cbs.setdefault(position, [])
        self.structure_cbs[position].append(setter)
        resp = getter(timeout)
        if resp is None:
            raise ValueError(f"无法获取 {position} 的结构")
        return resp

    @property
    def bot_ud(self):
        if isinstance(self.frame.launcher, FrameEulogistLauncher):
            return self.frame.launcher.eulogist.bot_unique_id
        else:
            return self.frame.launcher.omega.get_bot_unique_id()
