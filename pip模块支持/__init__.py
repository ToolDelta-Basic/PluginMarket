import importlib
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

from tooldelta import Plugin, fmts, plugin_entry, utils

PYPI_INDEX_URL = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"


def decode_bytes(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "cp936", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class PipSupport(Plugin):
    name = "pip模块安装支持"
    author = "ToolDelta"
    version = (0, 0, 8)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        sys.path.append(str(self.data_path))
        self.frame.add_console_cmd_trigger(
            ["pip-install"], "[模块名]", "安装 Python 模块", self.on_console_pip
        )

    # -------------------------  API  -----------------------------
    def install(self, packages: list[str], upgrade: bool = False):
        if not packages:
            return
        pending: list[str] = []
        for spec in packages:
            name, sep, pinned = spec.partition("==")
            try:
                installed = version(name)
            except PackageNotFoundError:
                pending.append(spec)
                continue
            if not sep or installed == pinned:
                continue  # 版本满足，跳过
            pending.append(spec)  # 版本不满足，继续安装
        if not pending:
            return
        packages = pending

        install_opts = self._build_install_command(packages, upgrade)
        proc = subprocess.Popen(
            install_opts,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )
        self._readline_stdout(proc)
        self._readline_stderr(proc)
        returncode = proc.wait()
        if returncode != 0:
            fmts.print_err("模块安装时出现错误")
            raise SystemExit
        importlib.invalidate_caches()
        fmts.print_suc(f"模块 {', '.join(packages)} 安装成功")

    def _build_install_command(
        self, packages: list[str], upgrade: bool = False
    ) -> list[str]:
        """Build the command used to install Python packages."""
        install_args = [
            "install",
            "--index-url",
            PYPI_INDEX_URL,
            "--target",
            str(self.data_path),
        ]
        if upgrade:
            install_args.append("--upgrade")
        install_args.extend(packages)

        if self._current_python_has_pip():
            return [sys.executable, "-m", "pip", *install_args]

        uv_exec = shutil.which("uv")
        if uv_exec:
            uv_args = ["pip", *install_args]
            if self._can_run_current_python():
                uv_args[2:2] = ["--python", sys.executable]
            return [uv_exec, *uv_args]

        pip_exec = shutil.which("pip")
        if pip_exec:
            return [pip_exec, *install_args]

        fmts.print_err("未找到可用的 pip 或 uv 命令")
        raise SystemExit

    @staticmethod
    def _can_run_current_python() -> bool:
        """Return whether the current Python executable can be started."""
        try:
            proc = subprocess.run(
                [sys.executable, "-c", "import sys"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return False
        return proc.returncode == 0

    @classmethod
    def _current_python_has_pip(cls) -> bool:
        """Return whether the current Python executable can run pip."""
        if not cls._can_run_current_python():
            return False
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return False
        return proc.returncode == 0

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
            raw = proc.stdout.readline()
            if not raw:
                break
            line = decode_bytes(raw).strip()
            if not line:
                continue
            fmts.print_with_info(line, "§e pips §r")

    @utils.thread_func("pip安装模块错误输出")
    def _readline_stderr(self, proc: subprocess.Popen[bytes]):
        assert proc.stderr
        while True:
            raw = proc.stderr.readline()
            if not raw:
                break
            line = decode_bytes(raw).strip()
            if not line:
                continue
            fmts.print_with_info(line, "§c pips §r")


entry = plugin_entry(PipSupport, "pip")
