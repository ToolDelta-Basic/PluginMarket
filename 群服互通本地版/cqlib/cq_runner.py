import os
import subprocess
from websocket import WebSocketApp
from tooldelta import Print

running_proc: subprocess.Popen | None = None

first_create_ws: WebSocketApp | None = None

class ProcMana:
    def get_cq_proc(self, exec_fp: str):
        global running_proc
        Print.print_inf(f"当前工作目录: {os.getcwd()}")
        Print.print_inf(f"正在启动 GoCQ 进程 ({exec_fp})")
        if not running_proc:
            self.proc = running_proc = subprocess.Popen(
                f"{exec_fp} --faststart",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True,
            )
        else:
            Print.print_inf("重载插件时， 不需要再次启动GoCQ进程.")
            self.proc = running_proc

    def write(self, msg: str):
        assert self.proc.stdin, "don't have a stdin???"
        self.proc.stdin.write((msg + "\n").encode())
        self.proc.stdin.flush()

    def readline(self):
        assert self.proc.stdout, "don't have a stdout???"
        return self.proc.stdout.readline().decode()
