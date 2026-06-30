import asyncio
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)

# 默认配置映射
DEFAULT_MAPPING = {
    "核心.json": ["网络连接", "框架", "模块管理", "去重"],
    "安全.json": ["安全", "LLM安全", "网络连接.令牌"],
    "管理.json": ["管理员", "群管理", "多机器人"],
}

MAPPING_FILENAME = "配置映射.json"
MERGED_VIEW_FILENAME = "全部配置(只读视图).json"


class ConfigStore:
    """分层配置存储。

    架构：
    - 分层文件为权威源（核心.json / 安全.json / 管理.json / 模块/*.json）
    - 合并视图为只读（自动生成，外部修改时延迟同步回分层）
    - config.json 仅首次启动迁移用
    """

    def __init__(self, data_dir: str):
        self._root_dir = data_dir
        # 自动检测配置目录：优先 data_dir/配置/，否则 data_dir/ 本身
        config_subdir = os.path.join(data_dir, "配置")
        if os.path.isdir(config_subdir):
            self._data_dir = config_subdir
        elif any(f.endswith('.json') and f in ('核心.json', '安全.json', '管理.json')
                 for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))):
            # 配置文件直接在根目录
            self._data_dir = data_dir
        else:
            # 默认创建 配置/ 子目录
            self._data_dir = config_subdir

        self._data: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._mapping: Dict[str, List[str]] = {}
        self._self_write = False
        self._merged_mtime: float = 0

        os.makedirs(self._data_dir, exist_ok=True)
        os.makedirs(os.path.join(self._data_dir, "模块"), exist_ok=True)

        # 加载映射
        self._load_mapping()
        # 迁移旧 config.json
        self._migrate_legacy()
        # 从分层文件加载
        self._load_layered()
        # 生成合并视图
        self._write_merged_view()

        # 调试日志
        _log.info("配置加载完成: data_dir=%s, 文件=%s, 网络连接.地址=%s",
                  self._data_dir,
                  [f for f in os.listdir(self._data_dir) if f.endswith('.json')],
                  self.get('网络连接.地址', '(未找到)'))

    # ═══════════════════════════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════════════════════════

    def get(self, path: str, default: Any = None, **kwargs) -> Any:
        """读取配置值（支持点号路径）。"""
        with self._lock:
            return self._resolve(path, default)

    def set(self, path: str, value: Any, **kwargs) -> None:
        """写入配置值（自动写入对应分层文件）。"""
        with self._lock:
            parts = path.split(".")
            d = self._data
            for p in parts[:-1]:
                if p not in d or not isinstance(d[p], dict):
                    d[p] = {}
                d = d[p]
            d[parts[-1]] = value
            # 确定归属文件并保存
            top_key = parts[0]
            self._save_key_to_layer(top_key)
            self._write_merged_view()

    def register_section(self, section: str, defaults: dict, **kwargs) -> None:
        """注册配置节及其默认值。"""
        with self._lock:
            if section not in self._data:
                self._data[section] = dict(defaults)
                self._save_key_to_layer(section)
                self._write_merged_view()
            else:
                # 补充缺失的默认键
                existing = self._data[section]
                if isinstance(existing, dict):
                    changed = False
                    for k, v in defaults.items():
                        if k not in existing:
                            existing[k] = v
                            changed = True
                    if changed:
                        self._save_key_to_layer(section)

    def save(self) -> None:
        """保存所有分层文件。"""
        with self._lock:
            self._save_all_layers()
            self._write_merged_view()

    def get_all(self) -> dict:
        """获取完整配置副本。"""
        with self._lock:
            return dict(self._data)

    @property
    def data_dir(self) -> str:
        """数据根目录（属性访问，兼容旧代码）。"""
        return self._root_dir

    def get_data_dir(self) -> str:
        """返回数据根目录（非配置子目录）。"""
        return self._root_dir

    def get_config_dir(self) -> str:
        """返回配置子目录。"""
        return self._data_dir

    def check_merged_view_changes(self) -> None:
        """检查合并视图是否被外部修改，如果是则同步回分层。"""
        merged_path = os.path.join(self._data_dir, MERGED_VIEW_FILENAME)
        if not os.path.isfile(merged_path):
            return
        try:
            current_mtime = os.path.getmtime(merged_path)
        except OSError:
            return
        if current_mtime > self._merged_mtime and not self._self_write:
            # 外部修改了合并视图 → 延迟同步
            _log.info("检测到合并视图被外部修改，同步回分层文件...")
            try:
                with open(merged_path, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                if isinstance(new_data, dict):
                    with self._lock:
                        self._data = new_data
                        self._save_all_layers()
                        self._merged_mtime = current_mtime
            except (json.JSONDecodeError, OSError) as e:
                _log.warning("合并视图解析失败: %s", e)

    # ═══════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════

    def _load_mapping(self) -> None:
        """加载配置映射文件。"""
        path = os.path.join(self._data_dir, MAPPING_FILENAME)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._mapping = json.load(f)
                return
            except (json.JSONDecodeError, OSError) as e:
                _log.warning("config_store._load_mapping: %s", e)
        # 使用默认映射并写出
        self._mapping = dict(DEFAULT_MAPPING)
        self._save_mapping()

    def _save_mapping(self) -> None:
        """保存配置映射文件。"""
        path = os.path.join(self._data_dir, MAPPING_FILENAME)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, ensure_ascii=False, indent=2)
        except OSError as e:
            _log.warning("config_store._save_mapping: %s", e)

    def _migrate_legacy(self) -> None:
        """迁移旧 config.json（一次性）。"""
        legacy_path = os.path.join(self._root_dir, "config.json")
        if not os.path.isfile(legacy_path):
            return
        migrated_marker = os.path.join(self._root_dir, ".config_migrated")
        if os.path.isfile(migrated_marker):
            return
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
            if isinstance(legacy_data, dict) and legacy_data:
                self._data = legacy_data
                self._save_all_layers()
                # 标记已迁移
                with open(migrated_marker, "w") as f:
                    f.write("migrated")
                _log.info("旧 config.json 已迁移到分层配置")
        except (json.JSONDecodeError, OSError) as e:
            _log.warning("旧 config.json 迁移失败: %s", e)

    def _load_layered(self) -> None:
        """从分层文件加载配置。"""
        # 加载映射中定义的文件
        for filename in self._mapping.keys():
            path = os.path.join(self._data_dir, filename)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        layer = json.load(f)
                    if isinstance(layer, dict):
                        self._deep_merge(self._data, layer)
                except (json.JSONDecodeError, OSError) as e:
                    _log.warning("分层配置 %s 加载失败: %s", filename, e)

        # 加载模块配置目录
        modules_dir = os.path.join(self._data_dir, "模块")
        if os.path.isdir(modules_dir):
            for filename in sorted(os.listdir(modules_dir)):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(modules_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        layer = json.load(f)
                    if isinstance(layer, dict):
                        self._deep_merge(self._data, layer)
                except (json.JSONDecodeError, OSError) as e:
                    _log.warning("config_store._load_layered: %s", e)

    def _save_key_to_layer(self, top_key: str) -> None:
        """将指定顶层键保存到对应的分层文件。"""
        target_file = self._find_layer_for_key(top_key)
        target_path = os.path.join(self._data_dir, target_file)

        # 收集该文件拥有的所有顶层键
        owned_keys = self._get_keys_for_file(target_file)

        # 构建该文件的数据
        file_data = {}
        for key in owned_keys:
            if key in self._data:
                file_data[key] = self._data[key]
        # 确保当前 key 也写入
        if top_key in self._data and top_key not in file_data:
            file_data[top_key] = self._data[top_key]

        self._atomic_write(target_path, file_data)

    def _save_all_layers(self) -> None:
        """保存所有分层文件。"""
        # 按映射分组
        written_keys: set = set()

        for filename, keys in self._mapping.items():
            file_data = {}
            for key in keys:
                # key 可能是 "网络连接.令牌" 这种子路径，取顶层
                top = key.split(".")[0]
                if top in self._data:
                    file_data[top] = self._data[top]
                    written_keys.add(top)
            if file_data:
                path = os.path.join(self._data_dir, filename)
                self._atomic_write(path, file_data)

        # 未归属的键写入模块配置
        modules_dir = os.path.join(self._data_dir, "模块")
        os.makedirs(modules_dir, exist_ok=True)
        for key, value in self._data.items():
            if key not in written_keys and not key.startswith("_"):
                path = os.path.join(modules_dir, f"{key}.json")
                self._atomic_write(path, {key: value})

    def _find_layer_for_key(self, top_key: str) -> str:
        """查找顶层键归属的分层文件。"""
        for filename, keys in self._mapping.items():
            for k in keys:
                if k == top_key or k.startswith(top_key + "."):
                    return filename
                if top_key.startswith(k.split(".")[0]):
                    return filename
        # 未映射 → 模块配置
        return f"模块/{top_key}.json"

    def _get_keys_for_file(self, filename: str) -> List[str]:
        """获取某文件拥有的所有顶层键。"""
        if filename in self._mapping:
            # 取所有映射键的顶层部分
            tops = set()
            for k in self._mapping[filename]:
                tops.add(k.split(".")[0])
            return list(tops)
        return []

    def _write_merged_view(self) -> None:
        """生成合并视图文件（只读供查看）。"""
        path = os.path.join(self._data_dir, MERGED_VIEW_FILENAME)
        self._self_write = True
        try:
            self._atomic_write(path, self._data)
            self._merged_mtime = os.path.getmtime(path)
        finally:
            self._self_write = False

    def _resolve(self, path: str, default: Any) -> Any:
        parts = path.split(".")
        d = self._data
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                return default
        return d

    @staticmethod
    def _deep_merge(base: dict, overlay: dict) -> None:
        """深度合并 overlay 到 base。"""
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigStore._deep_merge(base[key], value)
            else:
                base[key] = value

    @staticmethod
    def _atomic_write(path: str, data: dict) -> None:
        """原子写入 JSON 文件。"""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as e:
            _log.error("配置保存失败 [%s]: %s", path, e)


class ConfigStoreLibrary(Library):
    """配置存储库。"""

    name = "config_store"
    version = "1.6.0"
    dependencies: list = []

    async def mount(self) -> None:
        data_path = self.services.get("_data_path")
        store = ConfigStore(data_path)
        self.services.register("config", store, mid=300)
        self._store = store

        # 启动合并视图变更检测（每 5 秒）
        self._check_task = asyncio.ensure_future(self._watch_merged_view())

    async def unmount(self) -> None:
        if hasattr(self, "_check_task"):
            self._check_task.cancel()

    async def _watch_merged_view(self) -> None:
        """定期检查合并视图是否被外部修改。"""
        while True:
            await asyncio.sleep(5)
            try:
                self._store.check_merged_view_changes()
            except Exception as e:
                _log.warning("config_store._watch_merged_view: %s", e)
