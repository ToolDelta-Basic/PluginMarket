"""包管理器 —— 依赖检查、安装（支持多镜像、失败回滚）+ v1.4.3 哈希验证"""
import hashlib
import importlib
import subprocess
import sys
import logging
import shutil
import os
from typing import Dict, List, Optional, Tuple

from qqlinker_framework.core.kernel.error_hints import hint


class PackageManager:
    """管理 Python 依赖包的检查、安装与回滚 + 哈希验证。"""

    def __init__(self):
        self._requirements: Dict[str, Tuple[str, Optional[str]]] = {}
        self._installed_target_dir: Optional[str] = None

    def set_target_dir(self, path: str):
        """设置 pip install --target 目录，并添加到 sys.path。"""
        self._installed_target_dir = path
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if path not in sys.path:
            sys.path.insert(0, path)

    def register_requirement(
        self, pkg_name: str, import_name: str = None,
        sha256: Optional[str] = None
    ):
        """注册一个依赖。

        Args:
            pkg_name: pip 包名。
            import_name: 导入名（默认同包名）。
            sha256: .whl 文件的 SHA-256 哈希（可选），安装后校验。
        """
        self._requirements[pkg_name] = (import_name or pkg_name, sha256)

    def register_requirements(
        self, reqs: dict, sha256_map: Optional[Dict[str, str]] = None
    ):
        """批量注册依赖。支持旧格式 {pkg: import_name} 和新格式。

        Args:
            reqs: {包名: 导入名} 或 [(包名, 导入名, sha256), ...]。
            sha256_map: 包名→SHA-256 哈希的映射（可选）。
        """
        if isinstance(reqs, dict):
            for pkg, imp in reqs.items():
                sha = sha256_map.get(pkg) if sha256_map else None
                self._requirements[pkg] = (imp, sha)

    def check_missing(self) -> Dict[str, Tuple[str, Optional[str]]]:
        """检查缺失的依赖，返回 {包名: (导入名, sha256)}。"""
        missing = {}
        for pkg, (imp, sha) in self._requirements.items():
            try:
                importlib.import_module(imp)
                logging.getLogger(__name__).debug(
                    "依赖已就绪: %s (导入 %s)", pkg, imp
                )
            except ImportError:
                logging.getLogger(__name__).info(
                    "缺失依赖: %s (导入 %s)", pkg, imp
                )
                missing[pkg] = (imp, sha)
        return missing

    @staticmethod
    def _verify_file_hash(filepath: str, expected_sha256: str) -> bool:
        """验证文件的 SHA-256 哈希。

        Args:
            filepath: 文件路径。
            expected_sha256: 期望的十六进制 SHA-256 值。

        Returns:
            True 匹配，False 不匹配或文件读取失败。
        """
        try:
            hasher = hashlib.sha256()
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
            actual = hasher.hexdigest()
            return actual == expected_sha256
        except OSError:
            return False

    @staticmethod
    def _verify_package_hash(
        target_dir: str, pkg_name: str, expected_sha256: str
    ) -> bool:
        """验证已安装包的哈希。

        策略：找到包的 .dist-info/RECORD 文件，对 RECORD 中列出的所有
        文件按路径排序后计算 SHA-256。RECORD 是 PEP 376 标准，pip 安装
        后必然存在。
        若 RECORD 不存在，回退到扫描 target_dir 下所有以 pkg_name
        开头的文件。
        """
        try:
            # 查找 .dist-info 目录
            dist_info = None
            pkg_norm = pkg_name.replace('-', '_')
            for entry in os.listdir(target_dir):
                if entry.endswith('.dist-info'):
                    base = entry.replace('.dist-info', '')
                    # 匹配: six-1.16.0.dist-info → six
                    name_part = base.rsplit('-', 1)[0]
                    if name_part == pkg_name or name_part == pkg_norm:
                        dist_info = entry
                        break

            hasher = hashlib.sha256()
            files = []

            if dist_info:
                record_path = os.path.join(target_dir, dist_info, 'RECORD')
                if os.path.isfile(record_path):
                    with open(record_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            # RECORD 格式: path,hash,size
                            parts = line.split(',')
                            fp = os.path.join(target_dir, parts[0].replace("/", os.sep))
                            if os.path.isfile(fp):
                                files.append(fp)

            if not files:
                # 回退：扫描所有匹配文件
                for entry in sorted(os.listdir(target_dir)):
                    entry_norm = entry.replace('_', '-').lower()
                    pkg_lower = pkg_name.replace('_', '-').lower()
                    if entry_norm.startswith(pkg_lower):
                        entry_path = os.path.join(target_dir, entry)
                        if os.path.isfile(entry_path):
                            files.append(entry_path)
                        elif os.path.isdir(entry_path):
                            for root, _, fnames in os.walk(entry_path):
                                for fn in sorted(fnames):
                                    files.append(os.path.join(root, fn))

            if not files:
                return False

            for fp in sorted(files):
                rel = os.path.relpath(fp, target_dir)
                hasher.update(rel.encode())
                with open(fp, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        hasher.update(chunk)
            actual = hasher.hexdigest()
            return actual == expected_sha256
        except OSError:
            return False

    def install_packages(
        self,
        packages: List[str],
        upgrade: bool = False,
        mirror_sources: List[str] = None,
    ) -> bool:
        """安装包列表，支持多镜像尝试、失败回滚和哈希验证。

        如果包注册时有 sha256，安装后自动验证。
        """
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
            logger.error(
                "未设置 pip 安装目标目录，安装中止。%s",
                hint["DEPENDENCY_TARGET_MISSING"],
            )
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
            _, expected_hash = self._requirements.get(pkg, (pkg, None))
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
                    pkg,
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
                        # ── v1.4.3: 哈希验证 ──
                        if expected_hash:
                            if not self._verify_package_hash(
                                target, pkg, expected_hash
                            ):
                                logger.error(
                                    "包 %s SHA-256 验证失败！期望 %s，"
                                    "已拒绝加载。可能原因：① 包被篡改 "
                                    "② 上游源投毒 ③ 网络传输错误。",
                                    pkg, expected_hash[:16] + "...",
                                )
                                self._cleanup_partial(target, installed_before)
                                pkg_ok = False
                                continue
                            logger.info(
                                "包 %s SHA-256 验证通过 (%s)",
                                pkg, expected_hash[:16] + "...",
                            )
                        logger.info("成功安装 %s (源: %s)", pkg, mirror)
                        pkg_ok = True
                        break
                    logger.warning(
                        "安装 %s 失败 (源 %s): %s。",
                        pkg, mirror, stderr.strip()[:200],
                    )
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    logger.error(
                        "安装 %s 超时 (源 %s)。", pkg, mirror,
                    )
                except Exception as e:
                    logger.error(
                        "安装 %s 异常 (源 %s): %s。%s",
                        pkg, mirror, e, hint["DEPENDENCY_INSTALL_FAILED"],
                    )

            if not pkg_ok:
                total_success = False
                logger.error(
                    "所有源均无法安装包: %s，尝试回滚。%s",
                    pkg, hint["DEPENDENCY_INSTALL_FAILED"],
                )
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
        """安装所有缺失的依赖（含哈希验证）。"""
        missing = self.check_missing()
        if not missing:
            return True
        return self.install_packages(list(missing.keys()))
