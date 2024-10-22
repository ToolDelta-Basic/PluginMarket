import os
from platform import uname
from tooldelta import Print, urlmethod
from . import utils

if 0:
    from .. import QQLinker


def download_gocq(self: "QQLinker", GOCQ_EXECFILE: str):
    Print.print_inf("正在下载 go-cqhttp 可执行文件..")
    platform = uname().system.lower()
    machine = uname().machine.lower()
    machine = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine, machine)
    fmt_name = "zip" if platform == "windows" else "tar.gz"
    gocq_file = f"go-cqhttp_{platform}_{machine}.{fmt_name}"
    download_path = os.path.join(self.data_path, f"gocqhttp_exec.{fmt_name}")
    exec_path = os.path.join(self.data_path, GOCQ_EXECFILE)
    # https://github.com/LagrangeDev/go-cqhttp/releases/download/v2.0.0-beta.1/go-cqhttp_windows_amd64.zip
    url = (
        "https://mirror.ghproxy.com/"
        "https://github.com/"
        "LagrangeDev/go-cqhttp/releases/download/v2.0.0-beta.1/" + gocq_file
    )
    tmp_dir = os.path.join(self.data_path, "gocqhttp-cachedir")
    urlmethod.download_file_singlethreaded(url, download_path)
    utils.extract_executable_file(download_path, tmp_dir)
    os.rename(os.path.join(tmp_dir, os.listdir(tmp_dir)[0]), exec_path)
    os.removedirs(tmp_dir)
