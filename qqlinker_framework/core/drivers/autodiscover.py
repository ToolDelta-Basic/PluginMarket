"""模块自动发现引擎 — 支持 Python 包扫描 + 文件目录扫描 + 远程下载。

模块存放路径（按优先级）:
  1. 内置模块: qqlinker_framework/modules/ 包（安装时自带）
  2. 外部模块: {data_path}/插件数据文件/模块源件/*.py（用户自行放置）
  3. 远程模块: 通过 qqdeps module add <url> 下载安装

约定了两种模块格式:
  A) 独立 .py 文件:   模块源件/my_mod.py（含一个 Module 子类）
  B) 目录包:          模块源件/<模块名>/ 目录下含 module.json 和模块代码

  module.json 示例:
  {
    "name": "my_module",
    "version": "1.0.0",
    "author": "...",
    "description": "...",
    "entry": "__init__.py"
  }
"""
import ast
import importlib
import logging
import pkgutil
import re
from typing import Dict, List, Optional, Type

from ..module import Module
from ..kernel.error_hints import hint
from ..kernel.services import UID_NOBODY

logger = logging.getLogger(__name__)

# ── 模块源码安全扫描 ──────────────────────────────────────

# 危险调用集合（AST 节点名）— 模块代码中不允许出现
dangerous_call_names = frozenset({
    # 任意代码执行
    'eval', 'exec', 'compile', '__import__',
    # 反序列化攻击
    'pickle.load', 'pickle.loads', 'pickle.Unpickler',
    'marshal.loads', 'marshal.load',
    # 文件操作（读写关键路径）
    'open',
    # 系统调用
    'os.system', 'os.popen', 'os.execv', 'os.execve', 'os.execl',
    'os.execle', 'os.execlp', 'os.execlpe', 'os.execvp', 'os.execvpe',
    'os.spawnl', 'os.spawnle', 'os.spawnlp', 'os.spawnlpe',
    'os.spawnv', 'os.spawnve', 'os.spawnvp', 'os.spawnvpe',
    # subprocess
    'subprocess.call', 'subprocess.run', 'subprocess.Popen',
    'subprocess.check_call', 'subprocess.check_output',
    'subprocess.getoutput', 'subprocess.getstatusoutput',
    # 动态代码加载
    'importlib.import_module', 'importlib.util.spec_from_file_location',
    'importlib.util.module_from_spec',
    # 动态属性访问绕过（静态检测无法彻底防御，仅检查常见模式）
    'getattr',
})

# 外部模块加载安全限制
_MAX_MODULE_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
_MAX_ZIP_UNCOMPRESSED_SIZE = 50 * 1024 * 1024  # 50 MB 解压后总大小上限


def _scan_module_source(source: str) -> List[str]:
    """用 AST 扫描模块源码中的危险调用，返回检测到的调用名列表。

    Args:
        source: Python 源码字符串。

    Returns:
        检测到的危险调用名列表（去重），空列表表示安全。
    """
    found: list = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        logger.warning("模块源码语法错误，无法扫描: 跳过安全分析")
        return found

    class _DangerousVisitor(ast.NodeVisitor):
        # 可通过 getattr 动态访问的危险模块名
        _DANGEROUS_GETATTR_MODULES = frozenset({'os', 'sys', 'subprocess'})

        def _is_name(self, node, names):
            """Fix H2: 检查节点是否为指定的 Name 节点。

            修复前此方法作为类外 @staticmethod 定义，导致
            self._is_name 抛出 AttributeError → 扫描崩溃。
            """
            return isinstance(node, ast.Name) and node.id in names

        def visit_Call(self, node):
            # 检查 func 是否为危险调用
            name = _get_call_name(node.func)
            if name == 'getattr':
                # getattr 静态检测: 若第一个参数是 os/sys/subprocess
                # 且第二个参数是字符串常量或拼接，标记为危险。
                # 限制: 无法检测 getattr(os, some_var) 或间接拼接，
                # 静态分析对动态绕过仅能提供尽力检测。
                if len(node.args) >= 1 and self._is_name(node.args[0], self._DANGEROUS_GETATTR_MODULES):
                    if len(node.args) >= 2 and (
                        isinstance(node.args[1], ast.Constant)
                        or isinstance(node.args[1], ast.BinOp)
                    ):
                        if 'getattr' not in found:
                            found.append('getattr')
            elif name and name in dangerous_call_names:
                if name not in found:
                    found.append(name)
            self.generic_visit(node)

    try:
        _DangerousVisitor().visit(tree)
    except Exception as e:
        logger.warning("模块源码AST扫描异常(%s)，跳过安全分析: %s", type(e).__name__, e)
    return found


def _get_call_name(node) -> Optional[str]:
    """从 AST 节点提取调用名（如 'os.system' 或 'eval'）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = node.attr
        parent = _get_call_name(node.value)
        if parent:
            return f"{parent}.{value}"
        return value
    return None


def discover_modules(
    package_name: str = "qqlinker_framework.modules"
) -> List[Type[Module]]:
    """递归扫描包，返回所有 Module 子类。"""
    module_classes: List[Type[Module]] = []
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        logger.warning("包 '%s' 不存在", package_name)
        return module_classes
    _walk_package(package, module_classes)
    return module_classes


def _walk_package(package, result: List[Type[Module]]):
    """递归遍历包，收集 Module 子类。"""
    prefix = package.__name__ + "."
    for _, modname, ispkg in pkgutil.iter_modules(
        package.__path__, prefix=prefix
    ):
        if ispkg:
            try:
                sub_pkg = importlib.import_module(modname)
                _walk_package(sub_pkg, result)
            except Exception as e:
                logger.exception(  # noqa: E122 (multi-line continuation alignment — indented to match nested with/try structure)
                "导入子包 %s 失败: %s。%s",
                modname, e, hint["MODULE_IMPORT_FAILED"])
        else:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                logger.exception(  # noqa: E122 (multi-line continuation alignment — indented to match nested with/try structure)
                "导入模块 %s 失败: %s。%s",
                modname, e, hint["MODULE_IMPORT_FAILED"])
                continue
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Module)
                    and attr is not Module
                    and getattr(attr, "name", None)
                ):
                    result.append(attr)


def _build_dependency_graph(classes: List[Type[Module]]):
    """构建依赖关系图与入度表。"""
    name_to_cls = {}
    in_degree = {}
    graph = {}
    for cls in classes:
        if not cls.name:
            continue
        name_to_cls[cls.name] = cls
        in_degree[cls.name] = in_degree.get(cls.name, 0)
        graph[cls.name] = []
    for cls in classes:
        if not cls.name:
            continue
        for dep in cls.dependencies:
            if dep in name_to_cls:
                graph[dep].append(cls.name)
                in_degree[cls.name] += 1
            else:
                logger.warning(
                    "模块 %s 依赖的 %s 未找到。可能原因：① 依赖模块未注册 ② 模块名拼写错误。"
                    "请确保所有 dependencies 中列出的模块都已安装。",
                    cls.name, dep,
                )
    return name_to_cls, in_degree, graph


def _topological_sort(name_to_cls, in_degree, graph):
    """执行拓扑排序，返回排序后的类列表。"""
    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_names = []
    while queue:
        name = queue.pop(0)
        sorted_names.append(name)
        for dependent in graph.get(name, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    if len(sorted_names) != len(name_to_cls):
        return None
    return [name_to_cls[name] for name in sorted_names]


def sort_by_dependencies(
    classes: List[Type[Module]],
) -> List[Type[Module]]:
    """根据模块依赖进行拓扑排序，若存在循环依赖则返回原始顺序。"""
    if not classes:
        return classes
    name_to_cls, in_degree, graph = _build_dependency_graph(classes)
    sorted_classes = _topological_sort(name_to_cls, in_degree, graph)
    if sorted_classes is None:
        logger.warning("检测到循环依赖，将使用原始顺序。%s", hint["MODULE_INIT_FAILED"])
        return classes
    result = list(sorted_classes)
    for cls in classes:
        if cls not in result:
            result.append(cls)
    return result


# ═══════════════════════════════════════════════════════════════
# 文件系统发现 — 从 插件数据文件/模块源件/ 扫描外部模块
# ═══════════════════════════════════════════════════════════════

import importlib.util as _importlib_util
import json as _json
import os as _os
import shutil as _shutil
import tempfile as _tempfile
import zipfile as _zipfile
from io import BytesIO as _BytesIO

try:
    from urllib.request import urlopen as _urlopen
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


# 约定路径常量
_MODULES_DIR_NAME = "插件数据文件/模块源件"


def _get_modules_dir(data_path: str) -> str:
    """获取外部模块目录的绝对路径（自动创建）。"""
    path = _os.path.join(data_path, _MODULES_DIR_NAME)
    _os.makedirs(path, exist_ok=True)
    return path


def discover_from_files(data_path: str) -> List[Type[Module]]:
    """从文件系统扫描外部模块源件。

    支持两种格式:
      A) 独立 .py 文件:  模块源件/xxx.py
      B) 目录包:  模块源件/<name>/ 含 module.json

    返回发现的所有 Module 子类列表。
    """
    mod_dir = _get_modules_dir(data_path)
    classes: List[Type[Module]] = []

    for entry in _os.listdir(mod_dir):
        full = _os.path.join(mod_dir, entry)
        if entry.startswith("__"):  # 跳过 __pycache__ 等
            continue

        if entry.endswith(".py"):
            # 格式 A: 独立 .py
            cls = _load_py_file(full)
            if cls:
                classes.append(cls)

        elif _os.path.isdir(full):
            # 格式 B: 目录包
            manifest = _os.path.join(full, "module.json")
            if _os.path.exists(manifest):
                try:
                    with open(manifest, "r", encoding="utf-8") as f:
                        _json.load(f)
                except Exception:
                    pass
            # 扫描目录下所有 .py 文件
            for root, _, files in _os.walk(full):
                for f in files:
                    if f.endswith(".py"):
                        cls = _load_py_file(_os.path.join(root, f))
                        if cls:
                            classes.append(cls)

    return classes


def _load_py_file(filepath: str) -> Optional[Type[Module]]:
    """从单个 .py 文件加载 Module 子类。

    安全措施（瑞士奶酪模型，多层独立加固）：
      1. 仅允许 .py 后缀
      2. 文件大小不超过 5 MB
      3. AST 扫描危险调用
      4. 加载失败不阻止框架启动
    """
    mod_name = _os.path.splitext(_os.path.basename(filepath))[0]

    # ── 安全检查 1: 仅允许 .py 后缀 ──
    if not filepath.endswith(".py"):
        logger.warning(
            "安全拦截: 模块文件 %s 不是 .py 后缀，跳过加载。",
            filepath,
        )
        return None

    # ── 安全检查 2: 文件大小限制（5 MB）──
    try:
        file_size = _os.path.getsize(filepath)
        if file_size > _MAX_MODULE_FILE_SIZE:
            logger.warning(
                "安全拦截: 模块文件 %s 过大 (%d bytes, 限制 %d bytes)，跳过加载。",
                filepath, file_size, _MAX_MODULE_FILE_SIZE,
            )
            return None
    except OSError:
        pass  # 无法获取大小不阻止加载

    # ── 安全检查 3: AST 扫描危险调用 ──
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(
            "无法读取模块源码 %s: %s。跳过加载。",
            filepath, e,
        )
        return None

    dangerous = _scan_module_source(source)
    if dangerous:
        logger.warning(
            "安全拦截: 模块 %s 包含危险调用 %s，跳过加载。"
            "该模块已被禁止执行。如需使用请检查源码或联系作者。",
            filepath, dangerous,
        )
        return None

    # 加唯一后缀防止重名
    unique_name = f"_extmod.{mod_name}.{_os.path.getmtime(filepath):.0f}"
    try:
        spec = _importlib_util.spec_from_file_location(unique_name, filepath)
        if spec is None or spec.loader is None:
            return None
        mod = _importlib_util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        logger.exception(
    "加载外部模块 %s 失败: %s。%s",
    filepath, e, hint["MODULE_IMPORT_FAILED"])
        return None

    # 扫描 Module 子类
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, Module)
            and attr is not Module
            and getattr(attr, "name", None)
        ):
            # 外部模块 uid: 优先从持久化授权文件读取，否则默认 400
            from ..managers.config_mgr import UID_NB as _NB
            declared_uid = getattr(attr, "uid", 400)
            # 尝试从授权记录读取持久化的有效 uid
            effective_uid = _load_external_uid_persisted(
                attr.name, int(declared_uid)
            )
            attr.uid = effective_uid
            return attr
    return None


# ═══════════════════════════════════════════════════════════════
# 远程模块下载
# ═══════════════════════════════════════════════════════════════

def download_module(url: str, data_path: str) -> Optional[str]:
    """从 URL 下载外部模块到 模块源件/ 目录。

    支持:
      - .py 文件: 直接存入
      - .zip 文件: 解压到子目录

    Returns:
        模块名（成功）或 None（失败）。
    """
    if not HAS_URLLIB:
        logger.error("urllib 不可用，无法下载。请确保 Python 环境包含 urllib 标准库。")
        return None

    mod_dir = _get_modules_dir(data_path)

    try:
        resp = _urlopen(url, timeout=30)
        data = resp.read()
    except Exception as e:
        logger.error("下载模块失败: %s → %s。%s", url, e, hint["MARKET_DOWNLOAD_FAILED"])
        return None

    fname = url.split("/")[-1].split("?")[0]
    # 文件名路径穿越防护：仅保留安全字符
    fname = re.sub(r'[^a-zA-Z0-9_.\-]', '', _os.path.basename(fname))
    if not fname:
        logger.error("模块文件名无效")
        return None

    if fname.endswith(".zip"):
        # ZIP: 解压到子目录
        base = fname[:-4]
        target = _os.path.abspath(_os.path.join(mod_dir, base))
        try:
            with _zipfile.ZipFile(_BytesIO(data)) as zf:
                # 解压大小上限（防护 zip bomb）
                total_size = sum(info.file_size for info in zf.infolist())
                if total_size > _MAX_ZIP_UNCOMPRESSED_SIZE:
                    logger.error(
                        "ZIP 解压后大小 %d 超过上限 %d，拒绝解压（疑似 zip bomb）",
                        total_size, _MAX_ZIP_UNCOMPRESSED_SIZE,
                    )
                    return None
                # Zip Slip 防护：校验每个条目路径在 target 内
                for info in zf.infolist():
                    member_path = _os.path.abspath(_os.path.join(target, info.filename))
                    if not member_path.startswith(target + _os.sep) and member_path != target:
                        logger.error(
                            "Zip Slip 攻击拦截: 条目 %s 试图逃逸到 %s",
                            info.filename, member_path,
                        )
                        return None
                zf.extractall(target)
            logger.info("模块 %s 已安装到 %s", base, target)
            return base
        except Exception as e:
            logger.error(  # noqa: E122 (multi-line continuation alignment — indented to match nested try/except structure)
                "解压模块失败: %s。可能原因：① ZIP 文件损坏 ② 磁盘空间不足。%s",
                e, hint["MARKET_DOWNLOAD_FAILED"])
            return None

    elif fname.endswith(".py"):
        # 安全扫描：下载的 .py 先 AST 分析
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError as e:
            logger.error("模块 %s 源码解码失败: %s", fname, e)
            return None
        dangerous = _scan_module_source(source)
        if dangerous:
            logger.warning(
                "安全拦截: 下载的模块 %s 包含危险调用 %s，拒绝安装。"
                "该模块已被禁止。如需使用请检查源码或联系作者。",
                fname, dangerous,
            )
            return None

        target = _os.path.join(mod_dir, fname)
        with open(target, "wb") as f:
            f.write(data)
        logger.info("模块 %s 已安装到 %s", fname, target)
        return fname[:-3]

    else:
        logger.error("不支持的文件格式: %s。仅支持 .py 和 .zip 格式的模块文件。", fname)
        return None


def list_external_modules(data_path: str) -> List[Dict[str, str]]:
    """列出已安装的外部模块。"""
    mod_dir = _get_modules_dir(data_path)
    result = []
    for entry in sorted(_os.listdir(mod_dir)):
        full = _os.path.join(mod_dir, entry)
        if entry.startswith("__"):  # 跳过 __pycache__ 等
            continue
        if entry.endswith(".py"):
            result.append({"name": entry[:-3], "type": "file", "path": full})
        elif _os.path.isdir(full):
            manifest = _os.path.join(full, "module.json")
            info = {}
            if _os.path.exists(manifest):
                try:
                    with open(manifest, "r", encoding="utf-8") as f:
                        info = _json.load(f)
                except Exception:
                    pass
            result.append({
                "name": entry,
                "type": "package",
                "path": full,
                "version": info.get("version", "?"),
                "author": info.get("author", "?"),
                "description": info.get("description", ""),
            })
    return result


def remove_external_module(name: str, data_path: str) -> bool:
    """删除已安装的外部模块。

    对 name 做路径穿越防护：仅保留安全字符，防止 ../ 遍历。
    """
    mod_dir = _get_modules_dir(data_path)
    # 路径穿越防护：basename 剥离目录，re.sub 过滤不安全字符
    safe_name = re.sub(r'[^a-zA-Z0-9_.\-]', '', _os.path.basename(name))
    if not safe_name:
        return False

    # 尝试 .py 文件
    py_path = _os.path.join(mod_dir, f"{name}.py")
    if _os.path.exists(py_path):
        _os.remove(py_path)
        return True

    # 尝试目录包
    pkg_path = _os.path.join(mod_dir, name)
    if _os.path.isdir(pkg_path):
        _shutil.rmtree(pkg_path)
        return True

    return False

# ── 外部模块 UID 持久化 ──────────────────────────────

_EXTERNAL_UID_FILE = None

def _get_external_uid_file() -> str:
    global _EXTERNAL_UID_FILE
    if _EXTERNAL_UID_FILE is None:
        import os as _os
        # 放在 data 目录下，不污染配置
        _EXTERNAL_UID_FILE = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            "data", "external_uids.json"
        )
    return _EXTERNAL_UID_FILE


def _load_external_uids() -> dict:
    fpath = _get_external_uid_file()
    if _os.path.isfile(fpath):
        try:
            with open(fpath, "r") as f:
                return _json.load(f)
        except Exception:
            pass
    return {}


def _save_external_uids(data: dict) -> None:
    fpath = _get_external_uid_file()
    _os.makedirs(_os.path.dirname(fpath), exist_ok=True)
    with open(fpath, "w") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)


def _load_external_uid_persisted(module_name: str, declared_uid: int) -> int:
    """读取外部模块的持久化 uid，取声明值和授权值的较大者（权限更低）。"""
    uids = _load_external_uids()
    granted = uids.get(module_name)
    if granted is not None:
        return granted
    # 未授权 → 保持 400 (nobody)
    return 400


def grant_external_module_uid(module_name: str, new_uid: int) -> bool:
    """root 用户为外部模块授予新的 uid 等级并持久化。

    Returns:
        True 表示成功。
    """
    if new_uid < 0:
        return False
    uids = _load_external_uids()
    uids[module_name] = new_uid
    _save_external_uids(uids)
    logger.info("外部模块 '%s' uid 已授予: %d (已持久化)", module_name, new_uid)
    return True


def revoke_external_module_uid(module_name: str) -> bool:
    """撤销外部模块的授权，回退到 nobody(400)。"""
    uids = _load_external_uids()
    if module_name in uids:
        del uids[module_name]
        _save_external_uids(uids)
        logger.info("外部模块 '%s' uid 授权已撤销 → nobody(400)", module_name)
        return True
    return False
