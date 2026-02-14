import json
import os
import time
import uuid
from typing import Any, Dict, Tuple, TYPE_CHECKING
from tooldelta.utils import tempjson
from tooldelta import constants
from tooldelta.constants.netease import PYRPC_OP_SEND
if TYPE_CHECKING:
    from . import MCAgent


class Utils:
    """Utility functions for file operations and data management.

    Provides helper methods for disk I/O, timestamp generation,
    and data file management.
    """

    def __init__(self, plugin: "MCAgent"):
        self.file_path = os.path.join(os.path.dirname(__file__), "data.json")
        self.plugin = plugin

    @staticmethod
    def disk_read(path: str) -> Dict[Any, Any]:
        data = tempjson.load_and_read(
            path, need_file_exists=False, default={}, timeout=2
        )
        tempjson.unload_to_path(path)
        return data

    @staticmethod
    def disk_read_need_exists(path: str) -> Dict[Any, Any]:
        data = tempjson.load_and_read(
            path, need_file_exists=True, default={}, timeout=2
        )
        tempjson.unload_to_path(path)
        return data

    @staticmethod
    def disk_write(path: str, data: Dict[Any, Any]) -> None:
        tempjson.load_and_write(
            path,
            data,
            need_file_exists=False,
            timeout=2,
        )
        tempjson.flush(path)
        tempjson.unload_to_path(path)

    @staticmethod
    def now() -> Tuple[int, str]:
        timestamp_now = int(time.time())
        date_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_now))
        return (timestamp_now, date_now)

    @staticmethod
    def make_data_file(plugin, filename: str) -> str:
        plugin.make_data_path()
        data_file_path = os.path.join(plugin.data_path, filename)

        if not os.path.exists(data_file_path):
            with open(data_file_path, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=4)

        return data_file_path

    def sendaicmd(self, cmd: str):
        my_runtimeid = self.plugin.game_ctrl.players.getBotInfo().runtime_id
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
        self.plugin.game_ctrl.sendPacket(constants.PacketIDS.PyRpc, pk)
