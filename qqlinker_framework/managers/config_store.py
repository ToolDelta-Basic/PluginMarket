import json
import logging
import os
import tempfile
import threading
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)


class ConfigStore:
    """统一配置存储 — namespace → JSON 文件映射 (v6)。

    内部维护 namespace → 文件路径的注册表，
    支持点号分隔的路径查找 (get/set) 和配置节注册。
    """

    def __init__(self, data_path: str):
        self._data_path = os.path.abspath(data_path)
        self._lock = threading.Lock()
        # namespace → JSON 文件路径映射
        self._registry: Dict[str, str] = {}
        # namespace → loaded data cache
        self._cache: Dict[str, dict] = {}
        os.makedirs(self._data_path, exist_ok=True)

    # ── 核心 API ──

    def get(self, key: str, default: Any = None) -> Any:
        """点号分隔的路径查找。

        Examples:
            store.get("core.消息转发.游戏到群.是否启用")
            store.get("module.forwarder.链接的群聊")
        """
        parts = key.split(".", 1)
        if len(parts) < 2:
            return default
        namespace = parts[0]
        path = parts[1]
        data = self._load_namespace(namespace)
        return self._traverse(data, path, default)

    def set(self, key: str, value: Any) -> None:
        """写入配置值并持久化。

        Examples:
            store.set("module.forwarder.链接的群聊", [123456])
        """
        parts = key.split(".", 1)
        if len(parts) < 2:
            raise ValueError(f"配置键必须包含 namespace: {key}")
        namespace = parts[0]
        path = parts[1]
        data = self._load_namespace(namespace)
        self._assign(data, path, value)
        self._save_namespace(namespace, data)

    def register_section(
        self, namespace: str, defaults: Dict[str, Any]
    ) -> None:
        """注册模块配置节 — 写默认值（不覆盖已有值）。

        文件路径自动推导: data_path/<namespace-replaced>.json
        例如 namespace="module.forwarder" → 数据/模块/forwarder.json
        """
        with self._lock:
            filepath = self._namespace_to_path(namespace)
            self._registry[namespace] = filepath
            # 加载已有数据
            existing = self._load_json_file(filepath)
            # 合并默认值（不覆盖已有键）
            merged = _deep_merge(defaults, existing)
            # 写回磁盘
            self._save_json_file(filepath, merged)
            self._cache[namespace] = merged

    def get_data_dir(self) -> str:
        """返回数据根目录路径。"""
        return self._data_path

    def _resolve_section_path(self, namespace: str) -> str:
        """返回 namespace 对应的 JSON 文件路径。"""
        return self._namespace_to_path(namespace)

    # ── 内部实现 ──

    def _load_namespace(self, namespace: str) -> dict:
        """加载 namespace 对应的配置数据（缓存）。"""
        with self._lock:
            if namespace in self._cache:
                return self._cache[namespace]
            filepath = self._registry.get(namespace)
            if filepath is None:
                # 尝试推导路径
                filepath = self._namespace_to_path(namespace)
            data = self._load_json_file(filepath)
            self._cache[namespace] = data
            return data

    def _save_namespace(self, namespace: str, data: dict) -> None:
        """保存 namespace 配置到磁盘。"""
        filepath = self._registry.get(
            namespace, self._namespace_to_path(namespace)
        )
        self._save_json_file(filepath, data)
        with self._lock:
            self._cache[namespace] = data

    def _namespace_to_path(self, namespace: str) -> str:
        """将 namespace 转换为 JSON 文件路径。

        映射规则:
          "core" → "数据/配置/核心.json"
          "module.X" → "数据/配置/模块/X.json"
          "admin.X" → "数据/配置/管理工具/X.json"
          "tool.X" → "数据/配置/工具/X.json"
          其他 → "数据/配置/<namespace>.json"
        """
        parts = namespace.split(".", 1)
        root = parts[0]
        sub = parts[1] if len(parts) > 1 else ""

        if root == "core":
            return os.path.join(self._data_path, "配置", "核心.json")
        elif root == "module" and sub:
            safe = sub.replace("..", "").replace("/", "_")
            return os.path.join(self._data_path, "配置", "模块", f"{safe}.json")
        elif root == "admin" and sub:
            safe = sub.replace("..", "").replace("/", "_")
            return os.path.join(self._data_path, "配置", "管理工具", f"{safe}.json")
        elif root == "tool" and sub:
            safe = sub.replace("..", "").replace("/", "_")
            return os.path.join(self._data_path, "配置", "工具", f"{safe}.json")
        else:
            safe = namespace.replace("..", "").replace("/", "_")
            return os.path.join(self._data_path, "配置", f"{safe}.json")

    @staticmethod
    def _load_json_file(filepath: str) -> dict:
        """从 JSON 文件加载数据。"""
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("config_store._load_json_file: %s", e)
        return {}

    @staticmethod
    def _save_json_file(filepath: str, data: dict) -> None:
        """原子写入 JSON 文件。"""
        dirname = os.path.dirname(filepath) or "."
        os.makedirs(dirname, exist_ok=True)
        tmpfd, tmppath = tempfile.mkstemp(
            dir=dirname,
            prefix=os.path.basename(filepath) + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmpfd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmppath, filepath)
        except Exception:
            try:
                os.unlink(tmppath)
            except OSError as e:
                _log.warning("config_store._save_json_file: %s", e)
            raise

    @staticmethod
    def _traverse(data: dict, path: str, default: Any = None) -> Any:
        """按点号分隔路径遍历字典。"""
        keys = path.replace("..", ".").split(".")
        current = data
        for k in keys:
            if not k:
                continue
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current

    @staticmethod
    def _assign(data: dict, path: str, value: Any) -> None:
        """按点号分隔路径写入嵌套字典（创建缺失的中间字典）。"""
        keys = path.replace("..", ".").split(".")
        current = data
        for k in keys[:-1]:
            if not k:
                continue
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        last = keys[-1]
        if last:
            current[last] = value

    # ── 兼容旧 API ──

    def resolve_placeholders(self, text: str) -> str:
        """解析文本中的 {配置:节.键} 占位符为实际配置值。"""
        import re
        if "{配置:" not in text:
            return text

        def _replace(match):
            inner = match.group(1)
            return str(self.get(inner, match.group(0)))

        return re.sub(r"\{配置:(.+?)\}", _replace, text)


def _deep_merge(defaults: dict, existing: dict) -> dict:
    """深度合并: defaults 的键不覆盖 existing 中相同路径的已有值。"""
    result = dict(existing)
    for key, value in defaults.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(value, result[key])
        elif key not in result:
            result[key] = value
    return result
