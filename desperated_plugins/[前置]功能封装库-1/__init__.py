from tooldelta import Frame, Plugin, Player, plugin_entry

from tooldelta.game_utils import getPosXYZ
from tooldelta.launch_cli import SysStatus
from tooldelta.constants import PacketIDS
from typing import Callable  # noqa: UP035
from dataclasses import dataclass
import time
import threading
@dataclass
class UpdatePlayerAttributes:
    player: str | None
    attributes: dict
    tick: int
class ToolDeltaFuncLib1(Plugin):
    name = "前置-功能封装库-1"
    author = "xingchen"
    version = (0, 0, 3)
    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.listener_players_update_attributes_listener: list[
            tuple[str | list[str], Callable[[UpdatePlayerAttributes], None]]
        ] = []
        self.tp_players_thread: threading.Thread = threading.Thread(
            target=self.__tp_player__, name="tp_player_thread"
        )
        self.tp_players_thread.start()
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenPacket(PacketIDS.IDUpdateAttributes, self.process_update_player_attributes)
    def update_player_attributes_listener(self, players: str | list[str]) -> Callable:
        """
        监听玩家属性更新事件
        该方法需要机器人持续 TP 跟踪玩家，因该方法所用数据包只能在目标玩家半径大约60格内获取，因此不适用于大范围的玩家属性更新监听。
        Args:
            players (str | list[str]): 玩家名称或玩家名称列表
            func (Callable[[UpdatePlayerAttributes], None]): 回调函数，参数为玩家属性字典
        """
        def deco(func: Callable[[UpdatePlayerAttributes], None]):
            if isinstance(players, str):
                if players in self.frame.link_game_ctrl.allplayers:
                    self.listener_players_update_attributes_listener.append(
                        (players, func)
                    )
            elif isinstance(players, list):
                for player in players:
                    if player in self.frame.link_game_ctrl.allplayers:
                        self.listener_players_update_attributes_listener.append(
                            (player, func)
                        )
        return deco

    def process_update_player_attributes(self, packet: dict) -> None:
        """
        处理玩家属性更新事件(29号数据包)
        Args:
            packet (dict): 玩家属性更新事件数据包
        """
        for player, func in self.listener_players_update_attributes_listener:
            if player == self.get_player_name_from_entity_runtime(
                packet["EntityRuntimeID"]
            ):
                func(
                    UpdatePlayerAttributes(
                        self.get_player_name_from_entity_runtime(
                            packet["EntityRuntimeID"]
                        ),
                        packet["Attributes"],
                        packet["Tick"],
                    )
                )
                if not self.tp_players_thread.is_alive():
                    self.tp_players_thread = threading.Thread(
                        target=self.__tp_player__, name="tp_player_thread"
                    )
                    self.tp_players_thread.start()
    def get_player_name_from_entity_runtime(self, runtimeid: int) -> str | None:
        """根据实体 runtimeid 获取玩家名
        Args:
            runtimeid (int): 实体 RuntimeID
        Returns:
            str | None: 玩家名
        """
        if not self.frame.link_game_ctrl.all_players_data:
            return None
        for player in self.frame.link_game_ctrl.all_players_data:
            if player.entity_runtime_id == runtimeid:
                return player.name
        return None
    def on_player_leave(self, player: Player):
        player_name = player.name
        """
        玩家离开游戏时触发，用于删除已退出玩家，防止异常报错
        Args:
            player_name (str): 玩家名
        """
        if player_name in [
            listener[0] for listener in self.listener_players_update_attributes_listener
        ]:
            self.listener_players_update_attributes_listener = [
                (name, func)
                for name, func in self.listener_players_update_attributes_listener
                if name != player_name
            ]
    def __tp_player__(self) -> None:
        """
        内部方法，循环 TP 到被监听事件的玩家位置（模糊）
        """
        while self.frame.link_game_ctrl.launcher.status == SysStatus.RUNNING:
            for listener in self.listener_players_update_attributes_listener:
                player_pos: tuple[float, float, float] = getPosXYZ(listener[0])
                self.frame.link_game_ctrl.sendwocmd(
                    f"tp {self.frame.link_game_ctrl.bot_name} {str(int(player_pos[0])) + ' ' + str(int(player_pos[1])+5) + ' ' + str(int(player_pos[2]))}"
                )
            time.sleep(0.0001)
entry = plugin_entry(ToolDeltaFuncLib1, "前置-功能封装库-1")