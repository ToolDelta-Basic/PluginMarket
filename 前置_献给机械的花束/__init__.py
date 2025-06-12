import base64
import json
import os
import subprocess
import threading
import time
import uuid
import requests
from io import BytesIO
from dataclasses import dataclass
from tooldelta import FrameExit, InternalBroadcast, Plugin, Frame, plugin_entry
from tooldelta import cfg as config
from tooldelta import utils
from tooldelta.utils import fmts
from tooldelta.utils.tooldelta_thread import ToolDeltaThread

RESPONSE_ERROR_TYPE_PARSE_ERROR = 0
RESPONSE_ERROR_TYPE_RUNTIME_ERROR = 1


@dataclass
class PlaceNBTBlockResult:
    success: bool = False
    can_fast: bool = True
    structure_unique_id: str = ""
    structure_name: str = ""
    offset: tuple[int, int, int] = (0, 0, 0)


class FlowersForMachine(Plugin):
    name = "献给机械の花束"
    author = "2B and 9S"
    version = (0, 0, 1)

    def __init__(self, frame: Frame):
        CFG_DEFAULT = {
            "租赁服号": "48285363",
            "租赁服密码": "",
            "我已经修改了操作台坐标": False,
            "操作台中心 X 轴坐标": 0,
            "操作台中心 Y 轴坐标": 0,
            "操作台中心 Z 轴坐标": 0,
            "本地服务器端口号": 8080,
        }
        cfg, _ = config.get_plugin_config_and_version(
            "献给机械の花束", config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )

        self.rsn = str(cfg["租赁服号"])
        self.rsp = str(cfg["租赁服密码"])
        self.set_console_pos = bool(cfg["我已经修改了操作台坐标"])
        self.ccx = int(cfg["操作台中心 X 轴坐标"])
        self.ccy = int(cfg["操作台中心 Y 轴坐标"])
        self.ccz = int(cfg["操作台中心 Z 轴坐标"])
        self.ssp = int(cfg["本地服务器端口号"])
        self.started_server = False

        if not self.set_console_pos:
            raise Exception(
                "献给机械の花束: 您需要设置操作台的中心坐标。如果您不知道这是什么，请阅读自述文件，否则后果自负"
            )

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.frame = frame
        self.game_ctrl = self.frame.get_game_control()
        self.make_data_path()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.ListenInternalBroadcast(
            "ffm:place_nbt_block_request", self.on_place_nbt_block_request
        )

    def on_def(self):
        global bwo, nbtlib, MarshalPythonNBTObjectToWriter
        pip = self.GetPluginAPI("pip")

        if 0:
            from pip模块支持 import PipSupport

            pip: PipSupport

        pip.require({"bedrock-world-operator": "bedrockworldoperator"})
        import nbtlib
        import bedrockworldoperator as bwo
        from bedrockworldoperator.utils.marshalNBT import MarshalPythonNBTObjectToWriter

    def on_inject(self):
        self.close_server()
        self.run_server()

    def on_close(self, _: FrameExit):
        if self.started_server:
            self.close_server()

    def run_server(self):
        server_path = self.format_data_path("std_server")

        if self.started_server:
            return

        fmts.print_inf("献给机械の花束: 开始下载相应配套软件，请坐和放宽")
        file_binary = requests.get(
            "https://github.tooldelta.top/github.com/Happy2018new/the-last-problem-of-the-humankind/releases/download/public-hacking/std_server"
        )
        if not file_binary.ok:
            fmts.print_err("献给机械の花束: 恢复工具下载失败")
            return
        with open(server_path, "wb") as file:
            file.write(file_binary.content)
            os.chmod(server_path, 0o755)
        fmts.print_suc("献给机械の花束: 相应配套软件下载成功")

        args: list[str] = [
            server_path,
            f"-rsn={self.rsn}",
            f"-rsp={self.rsp}",
            f"-ccx={self.ccx}",
            f"-ccy={self.ccy}",
            f"-ccz={self.ccz}",
            f"-ssp={self.ssp}",
        ]
        self.server = subprocess.Popen(args)

        self.started_server = True

    def close_server(self):
        if not self.started_server:
            return

        try:
            requests.get(f"http://127.0.0.1:{self.ssp}/process_exit")
        except Exception:
            pass
        time.sleep(2)

        self.server.terminate()
        self.started_server = False

    def create_err_log(self, args: dict):
        file_name = str(uuid.uuid4()) + ".log"
        with open(file_name, "w+", encoding="utf-8") as file:
            file.write(json.dumps(args, ensure_ascii=False))
        fmts.print_war(f"献给机械の花束: 错误日志已生成到文件 {file_name} 中")

    def place_nbt_block(
        self, block_name: str, block_states: str, block_nbt: "nbtlib.tag.Compound"
    ) -> PlaceNBTBlockResult:
        args = {
            "block_name": block_name,
            "block_states_string": block_states,
        }
        buf = BytesIO()
        MarshalPythonNBTObjectToWriter(buf, block_nbt, "")
        args["block_nbt_base64_string"] = base64.encodebytes(buf.getvalue()).decode(
            encoding="utf-8"
        )

        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.ssp}/place_nbt_block",
                json.dumps(args, ensure_ascii=False),
            )
        except Exception:
            fmts.print_war("献给机械の花束: 服务器似乎崩溃了")
            self.close_server()
            return PlaceNBTBlockResult(False)

        if resp.status_code != 200:
            fmts.print_err("献给机械の花束: 尝试放置 NBT 方块时配置软件惊慌")
            self.create_err_log(args)
            return PlaceNBTBlockResult()

        resp_json = json.loads(resp.content.decode())
        if not resp_json["success"]:
            error_info = resp_json["error_info"]
            fmts.print_war(
                f"献给机械の花束: 尝试放置 NBT 方块时失败，错误信息为 {error_info}"
            )
            if resp_json["error_type"] == RESPONSE_ERROR_TYPE_RUNTIME_ERROR:
                self.create_err_log(args)
            return PlaceNBTBlockResult()

        return PlaceNBTBlockResult(
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

    def on_place_nbt_block_request(self, event: InternalBroadcast):
        """
        API (ffm:place_nbt_block_request): 其他插件请求恢复一片区域

        调用方式:
            ```
            InternalBroadcast(
                "ffm:place_nbt_block_request",
                {
                    "request_id": "...",                     # 请求 UUID
                    "block_name": "...",                     # 要放置的 NBT 方块的方块名称
                    "block_states_string": "...",            # 要放置的 NBT 方块的方块状态的字符串表示
                    "block_nbt": nbtlib.tag.Compound(...),   # 这个 NBT 方块的方块实体数据
                    "posx": int(...),                        # 这个 NBT 方块的 X 坐标
                    "posy": int(...),                        # 这个 NBT 方块的 Y 坐标
                    "posz": int(...),                        # 这个 NBT 方块的 Z 坐标
                },
            )
            ```

        返回值:
            ```
            InternalBroadcast(
                "ffm:place_nbt_block_response",
                {
                    "request_id": "...",    # 请求 UUID
                    "success": bool(...),   # 是否成功
                    "posx": int(...),       # 这个 NBT 方块的 X 坐标
                    "posy": int(...),       # 这个 NBT 方块的 Y 坐标
                    "posz": int(...),       # 这个 NBT 方块的 Z 坐标
                }
            )
        """
        self.sync_place_nbt_block(event)

    @utils.thread_func("NBT 方块放置进程", thread_level=ToolDeltaThread.SYSTEM)
    def sync_place_nbt_block(self, event: InternalBroadcast):
        if not self.started_server:
            self.run_server()

        posx = event.data["posx"]
        posy = event.data["posy"]
        posz = event.data["posz"]
        block_name = event.data["block_name"]
        block_states_string = event.data["block_states_string"]

        resp = self.place_nbt_block(
            block_name,
            block_states_string,
            event.data["block_nbt"],
        )

        if not resp.success:
            self.BroadcastEvent(
                InternalBroadcast(
                    "ffm:place_nbt_block_response",
                    {
                        "request_id": event.data["request_id"],
                        "success": False,
                        "posx": event.data["posx"],
                        "posy": event.data["posy"],
                        "posz": event.data["posz"],
                    },
                ),
            )
            return

        if resp.can_fast:
            self.game_ctrl.sendwocmd(
                f"setblock {posx} {posy} {posz} {block_name} {block_states_string}"
            )
        else:
            self.game_ctrl.sendwocmd(
                f'structure load "{resp.structure_name}" {posx} {posy} {posz}'
            )
            self.game_ctrl.sendcmd_with_resp("")

        self.BroadcastEvent(
            InternalBroadcast(
                "ffm:place_nbt_block_response",
                {
                    "request_id": event.data["request_id"],
                    "success": True,
                    "posx": event.data["posx"],
                    "posy": event.data["posy"],
                    "posz": event.data["posz"],
                },
            ),
        )


entry = plugin_entry(FlowersForMachine, "献给机械の花束")
