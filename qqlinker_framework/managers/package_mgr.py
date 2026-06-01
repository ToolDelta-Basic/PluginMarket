"""包管理器 —— 依赖检查、安装（支持多镜像、失败回滚）"""
import importlib
import subprocess
import sys
import logging
import shutil
import os
from typing import Dict, List, Optional

from ..core.error_hints import hint


class PackageManager:
    """管理 Python 依赖包的检查、安装与回滚。"""

    def __init__(self):
        """初始化包管理器，内部记录依赖映射和目标安装目录。"""
        self._requirements: Dict[str, str] = {}
        self._installed_target_dir: Optional[str] = None

    def set_target_dir(self, path: str):
        """设置 pip install --target 目录，并添加到 sys.path。"""
        self._installed_target_dir = path
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if path not in sys.path:
            sys.path.insert(0, path)

    def register_requirement(self, pkg_name: str, import_name: str = None):
        """注册一个依赖：包名 -> 导入名。"""
        self._requirements[pkg_name] = import_name or pkg_name

    def register_requirements(self, reqs: dict[str, str]):
        """批量注册依赖。"""
        self._requirements.update(reqs)

    def check_missing(self) -> dict[str, str]:
        """检查缺失的依赖，返回 {包名: 导入名}。"""
        missing = {}
        for pkg, imp in self._requirements.items():
            try:
                importlib.import_module(imp)
                logging.getLogger(__name__).debug(
                    "依赖已就绪: %s (导入 %s)", pkg, imp
                )
            except ImportError:
                logging.getLogger(__name__).info(
                    "缺失依赖: %s (导入 %s)", pkg, imp
                )
                missing[pkg] = imp
        return missing

    def install_packages(
        self,
        packages: list[str],
        upgrade: bool = False,
        mirror_sources: list[str] = None,
    ) -> bool:
        """安装包列表，支持多镜像尝试和失败回滚。"""
        if not packages:
            return True

        if mirror_sources is None:
            mirror_sources = [
                "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple",
                "https://mirrors.aliyun.com/pypi/simple/",
                "https://pypi.org/simple/",
            ]

        logger = logging.getLogger(__name__)
        target = self._installed_target_dir
        if not target:
            logger.error("未设置 pip 安装目标目录，安装中止。%s", hint["DEPENDENCY_TARGET_MISSING"])
            return False

        pyexec = sys.executable
        if "py" not in pyexec.lower():
            pyexec = (
                shutil.which("python3")
                or shutil.which("python")
                or sys.executable
            )

        installed_before = set(os.listdir(target))

        total_success = True
        for pkg in packages:
            pkg_ok = False
            for mirror in mirror_sources:
                cmd = [
                    pyexec,
                    "-m",
                    "pip",
                    "install",
                    "--target",
                    target,
                    "-i",
                    mirror,
                    pkg,                    # 移除 --no-deps
                ]
                if upgrade:
                    cmd.append("--upgrade")
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    _, stderr = proc.communicate(timeout=60)
                    if proc.returncode == 0:
                        logger.info("成功安装 %s (源: %s)", pkg, mirror)
                        pkg_ok = True
                        break
                    logger.warning(
                        "安装 %s 失败 (源 %s): %s。可能是 pip 源暂时不可用。",
                        pkg, mirror, stderr.strip(),
                    )
                except subprocess.TimeoutExpired:
                    proc.kill()
                    logger.error("安装 %s 超时 (源 %s)。可能原因：① 网络连接慢 ② pip 源响应延迟。", pkg, mirror)
                except Exception as e:
                    logger.error(
                        "安装 %s 异常 (源 %s): %s。%s",
                        pkg, mirror, e, hint["DEPENDENCY_INSTALL_FAILED"],
                    )

            if not pkg_ok:
                total_success = False
                logger.error("所有源均无法安装包: %s，尝试回滚。%s", pkg, hint["DEPENDENCY_INSTALL_FAILED"])
                self._cleanup_partial(target, installed_before)
                break

        if total_success:
            importlib.invalidate_caches()
            logger.info("依赖安装成功，请重载插件以使新模块生效")
        return total_success

    @staticmethod
    def _cleanup_partial(target: str, before_set: set):
        """清理部分安装的残留文件。"""
        try:
            after = set(os.listdir(target))
            new_items = after - before_set
            for item in new_items:
                item_path = os.path.join(target, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    try:
                        os.remove(item_path)
                    except OSError:
                        pass
            logging.getLogger(__name__).warning("已清理部分安装残留")
        except Exception as e:
            logging.getLogger(__name__).error("清理残留失败: %s", e)

    def install_missing(self) -> bool:
        """安装所有缺失的依赖。"""
        missing = self.check_missing()
        if not missing:
            return True
        return self.install_packages(list(missing.keys()))
