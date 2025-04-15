import sys
import importlib
import subprocess
from tooldelta import Plugin, utils, fmts, plugin_entry


class PipSupport(Plugin):
    name = "pip模块安装支持"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        sys.path.append(self.data_path)
        self.frame.add_console_cmd_trigger(
            ["pip-install"], "[模块名]", "安装 Python 模块", self.on_console_pip
        )

    # -------------------------  API  -----------------------------
    def install(self, packages: list[str]):
        proc = subprocess.Popen(
            ["pip", "install", "--target", self.data_path, *packages],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._readline_stdout(proc)
        self._readline_stderr(proc)
        returncode = proc.wait()
        if returncode != 0:
            fmts.print_err("pip安装模块时出现错误")
            raise SystemExit
        importlib.invalidate_caches()
        fmts.print_suc(f"模块 {', '.join(packages)} 安装成功")

    def require(self, packages: str | list[str]):
        if isinstance(packages, str):
            packages = [packages]
        for package in packages:
            try:
                importlib.import_module(package)
            except ImportError:
                self.install([package])

    # -----------------------------------------------------------
    def on_console_pip(self, args: list[str]):
        if len(args) == 0:
            fmts.print_err("请输入要安装的模块名")
            return
        try:
            self.install(args)
        except SystemExit:
            pass

    @utils.thread_func("pip安装模块标准输出")
    def _readline_stdout(self, proc: subprocess.Popen[bytes]):
        assert proc.stdout
        while True:
            line = proc.stdout.readline().decode().strip()
            if not line:
                break
            fmts.print_with_info(line, "§e pips §r")

    @utils.thread_func("pip安装模块错误输出")
    def _readline_stderr(self, proc: subprocess.Popen[bytes]):
        assert proc.stderr
        while True:
            line = proc.stderr.readline().decode().strip()
            if not line:
                break
            fmts.print_with_info(line, "§c pips §r")


entry = plugin_entry(PipSupport, "pip")
