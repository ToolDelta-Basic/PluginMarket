import json
import uuid
import threading
from tooldelta import Plugin, constants, utils, Chat, Player, plugin_entry
from tooldelta.constants.netease import PYRPC_OP_SEND

if 0:
    from tooldelta.internal.types import Packet_CommandOutput


def find_key_from_value(dic, val):
    # A bad method!
    for k, v in dic.items():
        if v == val:
            return k


class BasicFunctionLib(Plugin):
    version = (0, 0, 12)
    name = "基本插件功能库"
    author = "SuperScript"
    description = "提供额外的方法用于获取游戏数据"

    def __init__(self, frame):
        super().__init__(frame)
        self.waitmsg_result = {}
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg

        if player in self.waitmsg_result:
            self.waitmsg_result[player](msg)

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        if player in self.waitmsg_result:
            self.waitmsg_result[player](EXC_PLAYER_LEAVE)

    # -------------- API ---------------
    def list_select(
        self,
        player: Player,
        choices_list: list[str],
        list_prefix: str,
        list_format: str = " %d - %s",
        list_end: str = "§7请选输入选项序号以选择：",
        waitmsg_timeout: int = 30,
        if_timeout: str = "§c输入超时， 已退出",
        if_not_int: str = "§c输入不是有效数字",
        if_not_in_range: str = "§c选项不在范围内， 已退出",
        if_list_empty: str = "§c列表空空如也...",
    ):
        """
        向玩家在聊天栏提出列表选择请求， 并获取选项值
        Args:
            player (str): 玩家名
            choices_list (list[str]): 选项列表
            list_prefix (str): 列表头提示
            list_format (str, optional): 列表格式, `%d` 和 `%s` 代表序号和选项. Defaults to " %d - %s".
            list_end (str, optional): 列表尾提示. Defaults to "§7请选输入选项序号以选择：".
            waitmsg_timeout (int, optional): 等待玩家选择的超时时间. Defaults to 30.
            if_timeout (str, optional): 超时时向玩家提示的文本. Defaults to "§c输入超时， 已退出".
            if_not_int (str, optional): 玩家输入的不是有效数字时的提示. Defaults to "§c输入不是有效数字".
            if_not_in_range (str, optional): 序号不在选项范围内的提示. Defaults to "§c选项不在范围内， 已退出".
            if_list_empty (str, optional): 列表空空如也的提示. Defaults to "§c列表空空如也...".
        Returns:
            str: 选项
            None: 无法获得选项
        """
        if choices_list == []:
            player.show(if_list_empty)
            return None
        player.show(list_prefix)
        for i, j in enumerate(choices_list):
            player.show(list_format % (i + 1, j))
        player.show(list_end)
        resp = player.input(timeout=waitmsg_timeout)
        if resp is None:
            player.show(if_timeout)
            return None
        elif (resp := utils.try_int(resp)) is None:
            player.show(if_not_int)
            return None
        elif resp not in range(1, len(choices_list) + 1):
            player.show(if_not_in_range)
            return None
        return choices_list[resp - 1]

    def multi_sendcmd_and_wait_resp(self, cmds: list[str], timeout: int):
        cbs: dict[str, "Packet_CommandOutput"] = {}
        evts: list[threading.Event] = []

        def _sendcmd2cb(cmd):
            evts.append(evt := threading.Event())
            cbs[cmd] = self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
            evt.set()

        for cmd in cmds:
            utils.createThread(_sendcmd2cb, args=(cmd,))
        for evt in evts:
            evt.wait()
        return cbs

    # -------------- Old API -----------
    def getScore(self, scoreboardNameToGet: str, targetNameToGet: str) -> int | list:
        "获取玩家计分板分数 (计分板名, 玩家/计分板项名) 获取失败引发异常"
        resultList = self.game_ctrl.sendwscmd(
            f"/scoreboard players list {targetNameToGet}", True
        ).OutputMessages  # type: ignore
        result = {}
        result2 = {}
        for i in resultList:
            Message = i.Message
            if Message == r"commands.scoreboard.players.list.player.empty":
                continue
            if Message == r"§a%commands.scoreboard.players.list.player.count":
                targetName = i.Parameters[1][1:]
            elif Message == "commands.scoreboard.players.list.player.entry":
                if targetName == "commands.scoreboard.players.offlinePlayerName":
                    continue
                scoreboardName = i.Parameters[2]
                targetScore = int(i.Parameters[0])
                if targetName not in result:
                    result[targetName] = {}
                result[targetName][scoreboardName] = targetScore
                if scoreboardName not in result2:
                    result2[scoreboardName] = {}
                result2[scoreboardName][targetName] = targetScore
        if not (result or result2):
            raise Exception("Failed to get the score.")
        try:
            if targetNameToGet == "*" or targetNameToGet.startswith("@"):
                if scoreboardNameToGet == "*":
                    raise ValueError("暂时无法获取 *ALL 计分板")
                return result2[scoreboardNameToGet]
            if scoreboardNameToGet == "*":
                return result[targetNameToGet]
            return result[targetNameToGet][scoreboardNameToGet]
        except KeyError as err:
            raise Exception(f"Failed to get score: {err}")

    def getPos(self, targetNameToGet: str, timeout: float = 1) -> dict:
        """
        获取租赁服内玩家坐标的函数
        参数:
            targetNameToGet: str -> 玩家名称
        返回: dict -> 获取结果
        包含了["x"], ["y"], ["z"]: float, ["dimension"](维度): int 和["yRot"]: float
        """
        if (
            (targetNameToGet not in self.game_ctrl.allplayers)
            and (targetNameToGet != self.game_ctrl.bot_name)
            and (not targetNameToGet.startswith("@a"))
        ):
            raise Exception("Player not found.")
        result = self.game_ctrl.sendwscmd_with_resp(
            "/querytarget " + targetNameToGet, timeout
        )
        if result.OutputMessages[0].Success is False:
            raise Exception(
                f"Failed to get the position: {result.OutputMessages[0].Parameters[0]}"
            )
        parameter = result.OutputMessages[0].Parameters[0]
        if isinstance(parameter, str):
            resultList = json.loads(parameter)
        else:
            resultList = parameter
        result = {}
        for i in resultList:
            targetName = find_key_from_value(self.game_ctrl.players_uuid, i["uniqueId"])
            x = (
                i["position"]["x"]
                if i["position"]["x"] >= 0
                else i["position"]["x"] - 1
            )
            y = i["position"]["y"] - 1.6200103759765
            z = (
                i["position"]["z"]
                if i["position"]["z"] >= 0
                else i["position"]["z"] - 1
            )
            position = {
                "x": float(f"{x:.2f}"),
                "y": float(f"{y:.2f}"),
                "z": float(f"{z:.2f}"),
            }
            dimension = i["dimension"]
            yRot = i["yRot"]
            result[targetName] = {
                "dimension": dimension,
                "position": position,
                "yRot": yRot,
            }
        if targetNameToGet == "@a":
            return result
        if len(result) != 1:
            raise Exception("Failed to get the position.")
        if targetNameToGet.startswith("@a"):
            return next(iter(result.values()))
        res = result.get(targetNameToGet)
        if res:
            return res
        else:
            raise ValueError(
                "error(debug): 找不到坐标-玩家, 结果表是",
                res,
                "目标选择器是",
                targetNameToGet,
            )

    def getItem(self, targetName: str, itemName: str, itemSpecialID: int = -1) -> int:
        "获取玩家背包内物品数量: 目标选择器, 物品ID, 特殊值 = 所有"
        if (
            (targetName not in self.game_ctrl.allplayers)
            and (targetName != self.game_ctrl.bot_name)
            and (not targetName.startswith("@a"))
        ):
            raise Exception("Player not found.")
        result = self.game_ctrl.sendwscmd_with_resp(
            f"/clear {targetName} {itemName} {itemSpecialID} 0"
        )
        if result.OutputMessages[0].Message == "commands.generic.syntax":
            raise Exception("Item name error.")
        if result.OutputMessages[0].Message == "commands.clear.failure.no.items":
            return 0
        return int(result.OutputMessages[0].Parameters[1])

    def getTarget(self, sth: str, timeout: bool | int = 5) -> list:
        "获取符合目标选择器实体的列表"
        if not sth.startswith("@"):
            raise Exception("Minecraft Target Selector is not correct.")
        result = (
            self.game_ctrl.sendwscmd_with_resp(f"/testfor {sth}", timeout)
            .OutputMessages[0]
            .Parameters
        )
        if result:
            result = result[0]
            return result.split(", ")
        return []

    def getBlockTile(self, x: int, y: int, z: int):
        "获取指定坐标的方块的ID"
        res = self.game_ctrl.sendwscmd_with_resp(f"/testforblock {x} {y} {z} air")
        if res.SuccessCount:
            return "air"
        return res.OutputMessages[0].Parameters[4].strip("%tile.").strip(".name")

    def waitMsg_with_actbar(self, who: Player, msg: str, timeout: int = 30, exc=None):
        """
        使用其来等待一个玩家的聊天栏回复, 超时则引发exc给定的异常, 没有给定时超时返回None
        当过程中玩家退出了游戏, 则引发异常(为IOError)
        """
        getter, setter = utils.create_result_cb()
        self.waitmsg_result[who] = setter
        res = getter(timeout)
        del self.waitmsg_result[who]
        if res is EXC_PLAYER_LEAVE:
            raise EXC_PLAYER_LEAVE
        return res

    def getPosXYZ(self, player, timeout=30) -> tuple[float, float, float]:
        "获取玩家坐标的X, Y, Z值"
        res = self.getPos(player, timeout=timeout)["position"]
        return res["x"], res["y"], res["z"]

    def getPosXYZ_Int(self, player, timeout=30) -> tuple[int, int, int]:
        "获取玩家坐标的X, Y, Z值"
        res = self.getPos(player, timeout=timeout)["position"]
        return int(res["x"]), int(res["y"]), int(res["z"])

    def sendresultcmd(self, cmd, timeout=30):
        "返回命令执行是否成功"
        res = self.game_ctrl.sendwscmd_with_resp(cmd, timeout).SuccessCount
        return bool(res)

    def sendaicmd(self, cmd: str):
        my_runtimeid = self.game_ctrl.players.getBotInfo().runtime_id
        pk = {
            "Value": [
                "ModEventC2S",
                [
                    "Minecraft",
                    "aiCommand",
                    "ExecuteCommandEvent",
                    {
                        "playerId": str(my_runtimeid),
                        "cmd": cmd,
                        "uuid": str(uuid.uuid4()),
                    },
                ],
                None,
            ],
            "OperationType": PYRPC_OP_SEND,
        }
        self.game_ctrl.sendPacket(constants.PacketIDS.PyRpc, pk)


EXC_PLAYER_LEAVE = OSError("Player left when waiting msg.")
entry = plugin_entry(BasicFunctionLib, "基本插件功能库")
