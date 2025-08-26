import sys
import importlib
import subprocess
from tooldelta import Plugin, utils, fmts, plugin_entry


class PipSupport(Plugin):
    name = "pip模块安装支持"
    author = "ToolDelta"
    version = (0, 0, 5)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        sys.path.append(str(self.data_path))
        self.frame.add_console_cmd_trigger(
            ["pip-install"], "[模块名]", "安装 Python 模块", self.on_console_pip
        )

    # -------------------------  API  -----------------------------
    def install(self, packages: list[str], upgrade = False):
        pyexec = sys.executable
        if "py" not in pyexec:
            # 这不是 Python, 是 ToolDelta
            install_opts = ["pip", "install", "-i", "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple", "--target", self.data_path, *packages]
        else:
            install_opts = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-i",
                "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple",
                "--target",
                self.data_path,
                *packages,
            ]
        if upgrade:
            install_opts.append("--upgrade")

        proc = subprocess.Popen(
            install_opts,
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

    def require(self, module_pip_name_and_imp_name: dict[str, str] | str | list[str]):
        """
        显式需求一个 Python 模块。

        Args:
            package_pip_name_and_module_name (dict[str, str] | str): 模块的 pip 名与导入名
        """
        need_installed: list[str] = []
        if isinstance(module_pip_name_and_imp_name, list):
            # 多个库, 且库名与导入模块名相同
            # 向下兼容
            module_pip_name_and_imp_name = {
                module_pip_name_and_imp_name: module_pip_name_and_imp_name
                for module_pip_name_and_imp_name in module_pip_name_and_imp_name
            }
        if isinstance(module_pip_name_and_imp_name, str):
            # 单个库, 且库名与导入模块名相同
            # 向下兼容
            module_pip_name_and_imp_name = {
                module_pip_name_and_imp_name: module_pip_name_and_imp_name
            }
        for package_name, module_name in module_pip_name_and_imp_name.items():
            try:
                importlib.import_module(module_name)
            except ImportError:
                need_installed.append(package_name)
        if need_installed:
            self.install(need_installed)
            
    def upgrade(self, *modules: str):
        """
        更新库。
        
        Args:
            *modules (str): 需要更新的库的库名
        """
        self.install(list(modules), upgrade=True)

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
