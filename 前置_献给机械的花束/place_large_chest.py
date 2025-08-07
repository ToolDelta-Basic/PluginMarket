import json
import requests
from dataclasses import dataclass
from .define import FlowersForMachineBase
from .server_running import FlowersForMachineServerRunning
from .log_record import LogRecord
from .chest_cache import ChestCache, PairChest
from tooldelta import GameCtrl, Plugin
from tooldelta.utils import fmts


@dataclass
class PlaceLargeChestResponse:
    success: bool = False
    error_info: str = ""
    structure_unique_id: str = ""
    structure_name: str = ""


class PlaceLargeChest:
    server_running: FlowersForMachineServerRunning
    log_record: LogRecord

    def __init__(self, server_running: FlowersForMachineServerRunning):
        self.server_running = server_running
        self.log_record = LogRecord(self.server_running.base.plugin, "PlaceLargeChest")

    def base(self) -> FlowersForMachineBase:
        return self.server_running.base

    def plugin(self) -> Plugin:
        return self.server_running.base.plugin

    def game_ctrl(self) -> GameCtrl:
        return self.server_running.base.plugin.game_ctrl

    def chest_cache(self) -> ChestCache:
        return self.server_running.base.chest_cache

    def _send_request_to_server(
        self,
        chest_block_name: str,
        chest_block_states: str,
        pairlead_chest: PairChest,
        paired_chest: PairChest,
    ) -> PlaceLargeChestResponse:
        with self.server_running.mu:
            if not self.base().server_started:
                fmts.print_war(
                    "献给机械の花束: 你没有启动服务器，请在打断导入后 (如通过 reload) 在控制台输入 ffm 以启动"
                )
                return PlaceLargeChestResponse(False)

        args: dict = {
            "block_name": chest_block_name,
            "block_states_string": chest_block_states,
            "paired_chest_offset_x": paired_chest.current_pos[0]
            - pairlead_chest.current_pos[0],
            "paired_chest_offset_z": paired_chest.current_pos[2]
            - pairlead_chest.current_pos[2],
        }

        pairlead_structure_id = pairlead_chest.get_structure_unique_id()
        if pairlead_structure_id is None:
            args["pairlead_chest_structure_exist"] = False
            args["pairlead_chest_unique_id"] = ""
        else:
            args["pairlead_chest_structure_exist"] = True
            args["pairlead_chest_unique_id"] = pairlead_structure_id

        paired_structure_id = paired_chest.get_structure_unique_id()
        if paired_structure_id is None:
            args["paired_chest_structure_exist"] = False
            args["paired_chest_unique_id"] = ""
        else:
            args["paired_chest_structure_exist"] = True
            args["paired_chest_unique_id"] = paired_structure_id

        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.base().ssp}/place_large_chest",
                json.dumps(args, ensure_ascii=False),
            )
        except Exception:
            fmts.print_war("献给机械の花束: 服务器似乎崩溃了")
            return PlaceLargeChestResponse(False)

        if resp.status_code != 200:
            fmts.print_err("献给机械の花束: 尝试放置大箱子时配套软件惊慌")
            self.log_record.create_log(
                {
                    "error": "PlaceLargeChest/_send_request_to_server: resp.status_code is not equal to 200",
                    "args": args,
                }
            )
            return PlaceLargeChestResponse(False)

        resp_json = json.loads(resp.content.decode())
        if not resp_json["success"]:
            error_info = resp_json["error_info"]
            fmts.print_war(
                f"献给机械の花束: 尝试放置大箱子时失败，错误信息为 {error_info}"
            )
            self.log_record.create_log(
                {
                    "error": f"PlaceLargeChest/_send_request_to_server: Standard server runtime error; error_info = {error_info}",
                    "args": args,
                }
            )
            return PlaceLargeChestResponse(False, error_info)

        return PlaceLargeChestResponse(
            True,
            "",
            resp_json["structure_unique_id"],
            resp_json["structure_name"],
        )

    def place_large_chest(
        self,
        requester: str,
        chest_block_name: str,
        chest_block_states: str,
        oneOfTwoChests: PairChest,
    ) -> PlaceLargeChestResponse:
        pairlead_chest = self.chest_cache().find_chest(requester, oneOfTwoChests, True)
        paired_chest = self.chest_cache().find_chest(requester, oneOfTwoChests, False)
        if pairlead_chest is None or paired_chest is None:
            return PlaceLargeChestResponse(
                False,
                f"place_large_chest: Can not find pairlead or paired chest for {oneOfTwoChests}",
            )

        bot_name = self.game_ctrl().bot_name
        posx = min(pairlead_chest.current_pos[0], paired_chest.current_pos[0])
        posy = pairlead_chest.current_pos[1]
        posz = min(pairlead_chest.current_pos[2], paired_chest.current_pos[2])

        resp = self._send_request_to_server(
            chest_block_name,
            chest_block_states,
            pairlead_chest,
            paired_chest,
        )
        if not resp.success:
            return resp

        try:
            self.game_ctrl().sendwocmd(
                f'execute as @a[name="{bot_name}"] at @s run structure load "{resp.structure_name}" {posx} {posy} {posz}'
            )
        except Exception:
            pass

        return resp
