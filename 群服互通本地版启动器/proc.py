import subprocess
from pathlib import Path
from enum import IntEnum
from tooldelta import utils
from queue import Queue, Empty

class OutputType(IntEnum):
    STDOUT = 0
    STDERR = 1

OutputData = tuple[OutputType, str]
PROC = subprocess.Popen[bytes]
proc: PROC | None = None
port: int = -1
ok = False
output_queue: Queue[OutputData] = Queue()
output_thread_started = False


def get_proc() -> PROC | None:
    return proc


def set_proc(p: PROC):
    global proc
    proc = p


def get_port():
    return port


def set_port(p: int):
    if p not in range(0, 65536):
        raise ValueError(f"Invalid port number {p}")
    global port
    port = p


def is_ok():
    return ok


def set_ok(b: bool):
    global ok
    ok = b


def start_proc(execfile_path: Path):
    if not execfile_path.is_file():
        raise FileNotFoundError(f"{execfile_path} is not a file")
    p = subprocess.Popen(
        ["./" + execfile_path.name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=execfile_path.parent,
        stdin=subprocess.PIPE,
    )
    set_proc(p)
    _read_stdout(p)
    _read_stderr(p)
    return p


@utils.thread_func("群服 CQ 标准输出", thread_level=utils.ToolDeltaThread.SYSTEM)
def _read_stdout(p: PROC):
    assert p.stdout
    while msg := p.stdout.readline().decode().strip():
        output_queue.put((OutputType.STDOUT, msg))
    output_queue.put((OutputType.STDOUT, ""))


@utils.thread_func("群服 CQ 标准错误", thread_level=utils.ToolDeltaThread.SYSTEM)
def _read_stderr(p: PROC):
    assert p.stderr
    while msg := p.stderr.readline().decode().strip():
        output_queue.put((OutputType.STDERR, msg))
    output_queue.put((OutputType.STDERR, ""))


def get_output(timeout: float = 5) -> OutputData | None:
    try:
        return output_queue.get(timeout=timeout)
    except Empty:
        return None

