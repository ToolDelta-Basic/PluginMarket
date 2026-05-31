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
import importlib
import logging
import pkgutil
from typing import Dict, List, Optional, Type
from .module import Module
from .error_hints import hint

logger = logging.getLogger(__name__)


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
                logger.exception("导入子包 %s 失败: %s。%s", modname, e, hint.MODULE_IMPORT_FAILED)
        else:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                logger.exception("导入模块 %s 失败: %s。%s", modname, e, hint.MODULE_IMPORT_FAILED)
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
        logger.warning("检测到循环依赖，将使用原始顺序。%s", hint.MODULE_INIT_FAILED)
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
    """从单个 .py 文件加载 Module 子类。"""
    mod_name = _os.path.splitext(_os.path.basename(filepath))[0]
    # 加唯一后缀防止重名
    unique_name = f"_extmod.{mod_name}.{_os.path.getmtime(filepath):.0f}"
    try:
        spec = _importlib_util.spec_from_file_location(unique_name, filepath)
        if spec is None or spec.loader is None:
            return None
        mod = _importlib_util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        logger.exception("加载外部模块 %s 失败: %s。%s", filepath, e, hint.MODULE_IMPORT_FAILED)
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
        logger.error("下载模块失败: %s → %s。%s", url, e, hint.MARKET_DOWNLOAD_FAILED)
        return None

    fname = url.split("/")[-1].split("?")[0]

    if fname.endswith(".zip"):
        # ZIP: 解压到子目录
        base = fname[:-4]
        target = _os.path.join(mod_dir, base)
        try:
            with _zipfile.ZipFile(_BytesIO(data)) as zf:
                zf.extractall(target)
            logger.info("模块 %s 已安装到 %s", base, target)
            return base
        except Exception as e:
            logger.error("解压模块失败: %s。可能原因：① ZIP 文件损坏 ② 磁盘空间不足。%s", e, hint.MARKET_DOWNLOAD_FAILED)
            return None

    elif fname.endswith(".py"):
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
    """删除已安装的外部模块。"""
    mod_dir = _get_modules_dir(data_path)

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
