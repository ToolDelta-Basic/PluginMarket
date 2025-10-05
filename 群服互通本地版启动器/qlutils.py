import os
import platform
from pathlib import Path
from tooldelta import fmts
from tooldelta.constants.tooldelta_cli import TDSPECIFIC_MIRROR
from tooldelta.utils.urlmethod import download_file_singlethreaded


def get_bin_name():
    sys_type = platform.system().lower()
    sys_machine = platform.machine().lower()
    arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
    if "TERMUX_VERSION" in os.environ:
        sys_type = "Android"
    else:
        sys_machine = arch_map.get(sys_machine, sys_machine)
    ret = f"gocq_{sys_type}_{sys_machine}"
    if sys_type == "windows":
        ret += ".exe"
    return ret


def get_bin_download_url():
    return (
        TDSPECIFIC_MIRROR
        + "/https://github.com/SuperScript-PRC/go-cqhttp/releases/latest/download/"
        + get_bin_name()
    )


def ensure_execfile_exists(datpath: Path):
    exec_path = datpath / get_bin_name()
    if not exec_path.exists():
        fmts.print_inf("正在下载 gocq...")
        download_file_singlethreaded(get_bin_download_url(), str(exec_path))
        fmts.print_inf("正在下载 gocq... 完成")
        if not exec_path.name.endswith(".exe"):
            os.chmod(exec_path, 0o755)
    return exec_path
