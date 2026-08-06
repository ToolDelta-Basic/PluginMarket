"""Lyra在Linux中按需构建MCWorld依赖所需的环境检查"""

import shutil
import subprocess
import sysconfig
import tempfile
from pathlib import Path


def check_build_environment() -> str | None:
    """返回Linux原生扩展构建环境的问题；环境可用时返回None"""
    compiler = shutil.which("g++")
    if compiler is None:
        return "未找到g++编译器"

    python_header = Path(sysconfig.get_path("include")) / "Python.h"
    if not python_header.is_file():
        return f"未找到当前Python的开发头文件: {python_header}"

    source = "#include <zlib.h>\nint main() { return zlibVersion() == nullptr; }\n"
    try:
        with tempfile.TemporaryDirectory(prefix="lyra-leveldb-check-") as temp_dir:
            output = Path(temp_dir) / "zlib-check"
            result = subprocess.run(
                [compiler, "-x", "c++", "-", "-o", str(output), "-lz"],
                input=source,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
    except OSError as error:
        return f"无法执行g++编译器: {error}"
    if result.returncode != 0:
        return "zlib开发头文件或链接库不可用"
    return None


def dependency_error_message(problem: str) -> str:
    """生成MCWorld的Linux构建依赖错误提示"""
    return (
        f"MCWorld导入依赖安装环境不完整({problem}), 本次导入已取消"
        "请面板维护者使用最新的ToolDelta Docker镜像, 或在镜像中安装："
        "Debian/Ubuntu: g++ zlib1g-dev(使用系统Python时还需python3-dev)；"
        "Alpine: g++ musl-dev zlib-dev python3-dev；"
        "RHEL系: gcc-c++ zlib-devel python3-devel"
        "BDX、Litematic、MCStructure、Schem和Schematic导入不受影响"
    )
