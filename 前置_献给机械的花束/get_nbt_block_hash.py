import json
import base64
import requests
from io import BytesIO
from dataclasses import dataclass
from tooldelta import GameCtrl, Plugin
from tooldelta.utils import fmts
from .define import FlowersForMachineBase
from .server_running import FlowersForMachineServerRunning
from .log_record import LogRecord

if 0:
    import nbtlib

REQUEST_TYPE_FULL_HASH = 0
REQUEST_TYPE_NBT_HASH = 1
REQUEST_TYPE_CONTAINER_SET_HASH = 2


@dataclass
class GetNBTBlockHashResponse:
    success: bool = False
    error_info: str = ""
    hash: int = 0


class GetNBTBlockHash:
    server_running: FlowersForMachineServerRunning
    log_record: LogRecord

    def __init__(self, server_running: FlowersForMachineServerRunning):
        self.server_running = server_running
        self.log_record = LogRecord(self.server_running.base.plugin, "GetNBTBlockHash")

    def base(self) -> FlowersForMachineBase:
        return self.server_running.base

    def plugin(self) -> Plugin:
        return self.server_running.base.plugin

    def game_ctrl(self) -> GameCtrl:
        return self.server_running.base.plugin.game_ctrl

    def _send_request_to_server(
        self,
        request_type: int,
        block_name: str,
        block_states: str,
        block_nbt: "nbtlib.tag.Compound",
    ) -> GetNBTBlockHashResponse:
        with self.server_running.mu:
            if not self.base().server_started:
                fmts.print_war(
                    "献给机械の花束: 你没有启动服务器，请在打断导入后 (如通过 reload) 在控制台输入 ffm 以启动"
                )
                return GetNBTBlockHashResponse(False)

        nbt_marshal = self.base().nbt_marshal
        if nbt_marshal is None:
            raise Exception(
                "GetNBTBlockHashResponse/_send_request_to_server: Should nerver happened"
            )

        args = {
            "request_type": request_type,
            "block_name": block_name,
            "block_states_string": block_states,
        }
        buf = BytesIO()
        nbt_marshal(buf, block_nbt, "")
        args["block_nbt_base64_string"] = base64.encodebytes(buf.getvalue()).decode(
            encoding="utf-8"
        )

        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.base().ssp}/get_nbt_block_hash",
                json.dumps(args, ensure_ascii=False),
            )
        except Exception:
            fmts.print_war("献给机械の花束: 服务器似乎崩溃了")
            return GetNBTBlockHashResponse(False)

        if resp.status_code != 200:
            fmts.print_err("献给机械の花束: 尝试获取 NBT 方块的校验和时配套软件惊慌")
            self.log_record.create_log(
                {
                    "error": "GetNBTBlockHashResponse/_send_request_to_server: resp.status_code is not equal to 200",
                    "args": args,
                }
            )
            return GetNBTBlockHashResponse(False)

        resp_json = json.loads(resp.content.decode())
        if not resp_json["success"]:
            error_info = resp_json["error_info"]
            fmts.print_war(
                f"献给机械の花束: 尝试获取 NBT 方块的校验和时失败，错误信息为 {error_info}"
            )
            self.log_record.create_log(
                {
                    "error": f"GetNBTBlockHashResponse/_send_request_to_server: Standard server runtime error; error_info = {error_info}",
                    "args": args,
                }
            )
            return GetNBTBlockHashResponse(False, error_info)

        return GetNBTBlockHashResponse(True, "", resp_json["hash"])

    def get_nbt_block_full_hash(
        self, block_name: str, block_states: str, block_nbt: "nbtlib.tag.Compound"
    ) -> GetNBTBlockHashResponse:
        return self._send_request_to_server(
            REQUEST_TYPE_FULL_HASH,
            block_name,
            block_states,
            block_nbt,
        )

    def get_nbt_block_nbt_hash(
        self, block_name: str, block_states: str, block_nbt: "nbtlib.tag.Compound"
    ) -> GetNBTBlockHashResponse:
        return self._send_request_to_server(
            REQUEST_TYPE_NBT_HASH,
            block_name,
            block_states,
            block_nbt,
        )

    def get_container_set_hash(
        self, block_name: str, block_states: str, block_nbt: "nbtlib.tag.Compound"
    ) -> GetNBTBlockHashResponse:
        return self._send_request_to_server(
            REQUEST_TYPE_CONTAINER_SET_HASH,
            block_name,
            block_states,
            block_nbt,
        )
