from threading import Event
from tooldelta import utils, fmts
from .proc import (
    OutputType,
    get_port,
    get_proc,
    start_proc,
    set_port,
    is_ok,
    set_ok,
    get_output,
)
from .qlutils import ensure_execfile_exists

if 0:
    from . import QQLinkerLauncher

get_port = get_port


def has_proc():
    return get_proc() is not None


class ProcMgr:
    def __init__(self, sys: "QQLinkerLauncher"):
        self.sys = sys
        self.ok_event = Event()
        if is_ok():
            self.ok_event.set()

    def launch(self, openat_port: int = -1):
        path = ensure_execfile_exists(self.sys.data_path)
        if not has_proc():
            self.sys.print("GOCQ 进程正在启动..")
            start_proc(str(path), str(path.parent))
            set_port(openat_port)
        self.output_stdout()

    def get_proc(self):
        if (proc := get_proc()) is None:
            raise RuntimeError("CQ进程未启动")
        return proc

    @utils.thread_func("群服 CQ 启动器消息输出")
    def output_stdout(self):
        available_outputs = 2
        while True:
            r = get_output(1)
            if r is None:
                continue
            otype, odata = r
            if odata == "":
                available_outputs -= 1
                if available_outputs == 0:
                    break
            if otype is OutputType.STDOUT:
                self.handle_specific_msg(odata)
                fmts.print_inf(f"[CQ] {odata}")
            elif otype is OutputType.STDERR:
                fmts.print_err(f"[CQ] {odata}")
        fmts.print_war("CQ 进程输出已退出")

    def handle_specific_msg(self, msg: str):
        if "请选择提交滑块ticket方式" in msg:
            # What? 我真的要这么做吗?
            stdin = self.get_proc().stdin
            assert stdin
            stdin.write(b"1\n")
            stdin.flush()
        elif "アトリは、高性能ですから" in msg:
            self.ok_event.set()
            set_ok(True)

    def wait_ok(self):
        self.ok_event.wait()
