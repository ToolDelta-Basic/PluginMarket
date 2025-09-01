from typing import Any
from io import BytesIO
import time
import uuid
from tooldelta import Frame, Plugin, utils, fmts, plugin_entry
from tooldelta.constants import PacketIDS
from tooldelta.mc_bytes_packet.base_bytes_packet import BaseBytesPacket
from tooldelta.mc_bytes_packet.structure_template_data_response import (
    StructureTemplateDataResponse,
)


# 使用 api = self.GetPluginAPI("前置-世界交互") 来获取到这个 api
class GameInteractive(Plugin):
    name = "前置-世界交互"
    author = "SuperScript and Happy2018new"
    description = "前置插件, 提供世界交互功能的数据包, etc."
    version = (2, 0, 7)

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.structure_callbacks: dict[str, Any] = {}

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenBytesPacket(
            PacketIDS.IDStructureTemplateDataResponse, self.on_structure_pkt
        )

    def on_def(self):
        global numpy, nbtlib
        global Block, Structure
        global make_uuid_safe_string, UnMarshalBufferToPythonNBTObject
        pip = self.GetPluginAPI("pip")

        if 0:
            from pip模块支持 import PipSupport

            pip = self.get_typecheck_plugin_api(PipSupport)

        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        import numpy
        import nbtlib
        from bedrockworldoperator.utils.unmarshalNBT import (
            UnMarshalBufferToPythonNBTObject,
        )
        from .structure import Structure, Block
        from .safe_uuid import make_uuid_safe_string

        self.Block = Block

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["getnbt"], "[x] [y] [z]", "获取指定坐标的方块的NBT", self.on_get_nbt
        )

    def on_structure_pkt(self, pk: BaseBytesPacket):
        if not isinstance(pk, StructureTemplateDataResponse):
            raise Exception("on_structure_pkt: Should nerver happened")

        structure_name = pk.StructureName
        if structure_name in self.structure_callbacks:
            callbacks: list = self.structure_callbacks[structure_name]

            callback = callbacks.pop()
            callback(pk)

            if callbacks == []:
                del self.structure_callbacks[structure_name]

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
                self.game_ctrl.sendwscmd_with_resp(
                    f"/execute at @s in {in_dim} run tp "
                    + " ".join(
                        [str(i) for i in command_block_update_packet["Position"]]
                    )
                ).SuccessCount
                == 0
            ):
                raise ValueError("无法tp至对应坐标")
            resp = self.game_ctrl.sendwscmd_with_resp(cmd)
            if (
                resp.SuccessCount == 0
                and "noChange" not in resp.OutputMessages[0].Message
            ):
                raise ValueError(
                    f"无法放置命令方块方块: {resp.OutputMessages[0].Message}"
                )
        time.sleep(limit_seconds2)
        self.game_ctrl.sendPacket(
            PacketIDS.CommandBlockUpdate, command_block_update_packet
        )

    def make_uuid_safe_string(self, unique_id: uuid.UUID) -> str:
        """
        make_uuid_safe_string 返回 unique_id 的安全化表示，
        这使得其不可能被网易屏蔽词所拦截

        Args:
            unique_id (str): 一个 UUID 实例

        Returns:
            str: 这个 UUID 的安全化字符串表示
        """
        return make_uuid_safe_string(unique_id)

    def get_structure(
        self, position: tuple[int, int, int], size: tuple[int, int, int]
    ) -> "Structure":
        """
        在 Bot 所处维度获取一个特定位置和大小的结构方块结构
        Args:
            position (tuple[int, int, int]): 坐标
            size (tuple[int, int, int]): 结构尺寸
        Returns:
            Structure: 结构数据类
        """
        structure = self._request_structure_and_get(position, size)
        if not isinstance(structure, StructureTemplateDataResponse):
            raise Exception("get_structure: Should nerver happend")

        nbt_bytes = structure.StructureTemplate
        buf = BytesIO(nbt_bytes)
        template: nbtlib.tag.Compound = UnMarshalBufferToPythonNBTObject(buf)[0]  # type: ignore

        return Structure(template)

    def on_get_nbt(self, args):
        try:
            x, y, z = (int(i) for i in args)
        except ValueError:
            fmts.print_err("参数错误")
            return

        try:
            res = self.get_structure((x, y, z), (1, 1, 1))
        except Exception as err:
            fmts.print_err(f"获取结构错误: {err}")
            return

        block = res.get_block((0, 0, 0))
        fmts.print_inf(f"目标方块数据: {block}")

    def get_block(self, x: int, y: int, z: int):
        return self.get_structure((x, y, z), (1, 1, 1)).get_block((0, 0, 0))

    def _request_structure_and_get(
        self, position: tuple[int, int, int], size: tuple[int, int, int], timeout=5.0
    ) -> StructureTemplateDataResponse:
        structure_name = "mystructure:" + make_uuid_safe_string(uuid.uuid4())

        getter, setter = utils.create_result_cb()
        self.structure_callbacks.setdefault(structure_name, [])
        self.structure_callbacks[structure_name].append(setter)

        pk = {
            "StructureName": structure_name,
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

        resp = getter(timeout)
        if not isinstance(resp, StructureTemplateDataResponse):
            raise ValueError(f"无法获取 {position} 的 {size} 结构")
        return resp

    @property
    def bot_ud(self):
        return (
            self.frame.get_players()
            .getPlayerByName(self.frame.game_ctrl.bot_name)
            .unique_id  # type: ignore
        )


entry = plugin_entry(GameInteractive, "前置-世界交互")
