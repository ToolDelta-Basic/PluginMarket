import json
import os
import time
import requests
import threading
import subprocess
from .define import FlowersForMachineBase
from tooldelta import Frame, FrameExit, Plugin
from tooldelta.utils import fmts, thread_func


class FlowersForMachineServerRunning:
    base: FlowersForMachineBase
    mu: threading.Lock
    closed: bool

    def __init__(self, base: FlowersForMachineBase):
        self.base = base
        self.mu = threading.Lock()
        self.closed = False

    def plugin(self) -> Plugin:
        return self.base.plugin

    def frame(self) -> Frame:
        return self.base.plugin.frame

    def on_close(self, _: FrameExit):
        with self.mu:
            self._close_server()
            self.closed = True

    def on_inject(self):
        self.auto_keep_alive()
        self.plugin().frame.add_console_cmd_trigger(
            ["ffm"],
            None,
            "启动 献给机械の花束 所使用的第二个机器人",
            self.run_server,
        )

    def check_config(self):
        if not self.base.read_v1_readme:
            raise Exception(
                "献给机械の花束: 请阅读版本 v2 的自述文件，因为我们更新了它"
            )
        if not self.base.set_console_pos:
            raise Exception(
                "献给机械の花束: 您需要设置操作台的中心坐标。如果您不知道这是什么，请阅读自述文件，否则后果自负"
            )
        if len(self.base.asa) == 0:
            raise Exception("献给机械の花束: 请设置验证服务地址")
        if len(self.base.rsn) == 0:
            raise Exception("献给机械の花束: 请设置租赁服号")
        if self.base.ssp == 0:
            raise Exception("献给机械の花束: 服务器端口号不得为 0")

    def _auto_keep_alive(self):
        need_restart = False
        error_info = ""

        if not self.base.server_started:
            return

        try:
            resp = requests.get(f"http://127.0.0.1:{self.base.ssp}/check_alive")
            if resp.status_code != 200:
                need_restart = True
            else:
                resp_json = json.loads(resp.content.decode())
                if not resp_json["alive"]:
                    need_restart = True
                    error_info = resp_json["error_info"]
        except Exception:
            need_restart = True

        if need_restart:
            if int(time.time()) - self.base.server_start_time < 90:
                return

            fmts.print_war("献给机械の花束: 服务器似乎已崩溃，正在试图重启")
            if len(error_info) > 0:
                fmts.print_war(f"献给机械の花束: 崩溃原因为 {error_info}")

            self._close_server()
            self._run_server()
        else:
            self.base.server_start_time = 0

    @thread_func(usage="献给机械の花束: 检查机器人是否已经死亡")
    def auto_keep_alive(self):
        while True:
            with self.mu:
                if self.closed:
                    return
                self._auto_keep_alive()
            time.sleep(30)

    def _download_server(self, server_path: str) -> bool:
        file_binary = requests.get(
            "https://gh-proxy.com/github.com/OmineDev/flowers-for-machines/releases/download/v1.2.3/standard-server_linux_amd64"
        )

        if not file_binary.ok:
            fmts.print_err("献给机械の花束: 配套软件下载失败")
            return False
        else:
            fmts.print_suc("献给机械の花束: 相应配套软件下载成功")

        with open(server_path, "wb") as file:
            file.write(file_binary.content)
            os.chmod(server_path, 0o755)

        return True

    def _run_server(self):
        self.check_config()

        server_path = self.plugin().format_data_path("standard-server_linux_amd64")
        if self.base.server_started:
            return

        fmts.print_inf("献给机械の花束: 开始下载相应配套软件，请坐和放宽")
        if not self._download_server(server_path):
            return

        args: list[str] = [
            server_path,
            f"-asa={self.base.asa}",
            f"-ast={self.base.ast}",
            f"-rsn={self.base.rsn}",
            f"-rsp={self.base.rsp}",
            f"-cdi={self.base.cdi}",
            f"-ccx={self.base.ccx}",
            f"-ccy={self.base.ccy}",
            f"-ccz={self.base.ccz}",
            f"-ssp={self.base.ssp}",
        ]

        self.base.server = subprocess.Popen(args)
        self.base.server_start_time = int(time.time())
        self.base.server_started = True

    def _close_server(self):
        if not self.base.server_started:
            return

        try:
            requests.get(f"http://127.0.0.1:{self.base.ssp}/process_exit")
        except Exception:
            pass
        time.sleep(2)

        if self.base.server is not None:
            self.base.server.terminate()
        self.base.server_start_time = 0
        self.base.server_started = False

    def run_server(self, _: list[str]):
        with self.mu:
            if not self.closed:
                self._run_server()

    def close_server(self):
        with self.mu:
            self._close_server()
