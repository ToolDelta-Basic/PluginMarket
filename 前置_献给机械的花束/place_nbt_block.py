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

RESPONSE_ERROR_TYPE_PARSE_ERROR = 0
RESPONSE_ERROR_TYPE_RUNTIME_ERROR = 1

if 0:
    import nbtlib


@dataclass
class PlaceNBTBlockResponse:
    success: bool = False
    can_fast: bool = True
    structure_unique_id: str = ""
    structure_name: str = ""
    offset: tuple[int, int, int] = (0, 0, 0)


class PlaceNBTBlock:
    server_running: FlowersForMachineServerRunning
    log_record: LogRecord

    def __init__(self, server_running: FlowersForMachineServerRunning):
        self.server_running = server_running
        self.log_record = LogRecord(self.server_running.base.plugin, "PlaceNBTBlock")

    def base(self) -> FlowersForMachineBase:
        return self.server_running.base

    def plugin(self) -> Plugin:
        return self.server_running.base.plugin

    def game_ctrl(self) -> GameCtrl:
        return self.server_running.base.plugin.game_ctrl

    def _send_request_to_server(
        self, block_name: str, block_states: str, block_nbt: "nbtlib.tag.Compound"
    ) -> PlaceNBTBlockResponse:
        with self.server_running.mu:
            if not self.base().server_started:
                fmts.print_war(
                    "献给机械の花束: 你没有启动服务器，请在打断导入后 (如通过 reload) 在控制台输入 ffm 以启动"
                )
                return PlaceNBTBlockResponse(False)

        nbt_marshal = self.base().nbt_marshal
        if nbt_marshal is None:
            raise Exception(
                "PlaceNBTBlock/_send_request_to_server: Should nerver happened"
            )

        args = {
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
                f"http://127.0.0.1:{self.base().ssp}/place_nbt_block",
                json.dumps(args, ensure_ascii=False),
            )
        except Exception:
            fmts.print_war("献给机械の花束: 服务器似乎崩溃了")
            return PlaceNBTBlockResponse(False)

        if resp.status_code != 200:
            fmts.print_err("献给机械の花束: 尝试放置 NBT 方块时配套软件惊慌")
            self.log_record.create_log(
                {
                    "error": "PlaceNBTBlock/_send_request_to_server: resp.status_code is not equal to 200",
                    "args": args,
                }
            )
            return PlaceNBTBlockResponse(False)

        resp_json = json.loads(resp.content.decode())
        if not resp_json["success"]:
            error_info = resp_json["error_info"]
            fmts.print_war(
                f"献给机械の花束: 尝试放置 NBT 方块时失败，错误信息为 {error_info}"
            )
            if resp_json["error_type"] == RESPONSE_ERROR_TYPE_RUNTIME_ERROR:
                self.log_record.create_log(
                    {
                        "error": f"PlaceNBTBlock/_send_request_to_server: Standard server runtime error; error_info = {error_info}",
                        "args": args,
                    }
                )
            return PlaceNBTBlockResponse(False)

        return PlaceNBTBlockResponse(
            True,
            resp_json["can_fast"],
            resp_json["structure_unique_id"],
            resp_json["structure_name"],
            (
                resp_json["offset_x"],
                resp_json["offset_y"],
                resp_json["offset_z"],
            ),
        )

    def place_nbt_block(
        self,
        block_pos: tuple[int, int, int],
        block_name: str,
        block_states: str,
        block_nbt: "nbtlib.tag.Compound",
    ) -> PlaceNBTBlockResponse:
        bot_name = self.game_ctrl().bot_name
        posx, posy, posz = block_pos[0], block_pos[1], block_pos[2]

        resp = self._send_request_to_server(
            block_name,
            block_states,
            block_nbt,
        )

        if not resp.success:
            return resp

        try:
            if resp.can_fast:
                self.game_ctrl().sendwocmd(
                    f'execute as @a[name="{bot_name}"] at @s run setblock {posx} {posy} {posz} {block_name} {block_states}'
                )
            else:
                self.game_ctrl().sendwocmd(
                    f'execute as @a[name="{bot_name}"] at @s run structure load "{resp.structure_name}" {posx} {posy} {posz}'
                )
        except Exception:
            pass

        return resp
