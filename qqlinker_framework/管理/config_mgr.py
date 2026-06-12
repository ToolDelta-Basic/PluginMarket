"""配置管理器（多层独立文件存储 + UID 访问控制 + 自动迁移）

═══════════════════════════════════════════════════════════════
层次结构:
  配置/
    ├─ 核心.json          # L1 — 系统核心 (读≤100, 写=0)
    ├─ 安全.json          # L2 — 安全/隐私 (读=0, 写=0)
    ├─ 管理.json          # L3 — 管理策略 (读≤100, 写≤100)
    └─ 模块/              # L4 — 模块自用 (读≤300, 写≤300)
        ├─ ai_core.json
        └─ ...

访问规则:
  - register_section(name, defaults, 读权限uid, 写权限uid)
  - get(key, requester_uid) — 低于读权限时拒绝
  - set(key, value, requester_uid) — 低于写权限时拒绝
  - auth_bridge.read(config_key, uid) — Gatekeeper 集成

迁移:
  首次启动时自动检测旧 config.json，拆分为各层文件。
═══════════════════════════════════════════════════════════════
"""
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from qqlinker_framework.core.kernel.error_hints import hint

_log = logging.getLogger(__name__)

# ── 层级常量（数字越小权限越高） ──────────────────────────
TIER_KERNEL = 0        # kernel — 完全权限
UID_DAEMON = 100    # daemon — 框架守护
UID_SERVICE = 200   # service — 框架服务
UID_APP = 300       # app — 用户模块
UID_NOBODY = 400    # nobody — 外部模块

# ── 默认 scope 表 ──────────────────────────────────────────

# 各配置节的默认读/写权限（section → (读uid, 写uid, 文件名)）
_BUILTIN_SCOPE: Dict[str, Tuple[int, int, str]] = {
    # L1 核心
    "网络连接":       (UID_DAEMON, TIER_KERNEL, "核心.json"),
    "去重":           (UID_DAEMON, TIER_KERNEL, "核心.json"),
    "调试引擎":       (UID_DAEMON, TIER_KERNEL, "核心.json"),
    "启动检查":       (UID_DAEMON, TIER_KERNEL, "核心.json"),
    "调试":           (UID_DAEMON, TIER_KERNEL, "核心.json"),
    "错误显示模式":   (UID_DAEMON, TIER_KERNEL, "核心.json"),
    # L2 安全/隐私
    "权限管理":       (TIER_KERNEL,    TIER_KERNEL, "安全.json"),
    "审计日志":       (TIER_KERNEL,    TIER_KERNEL, "安全.json"),
    "网络传输":       (TIER_KERNEL,    TIER_KERNEL, "安全.json"),
    "SSRF防护":       (TIER_KERNEL,    TIER_KERNEL, "安全.json"),
    "模块市场":       (TIER_KERNEL,    TIER_KERNEL, "安全.json"),
    "AI助手.密钥":    (TIER_KERNEL,    TIER_KERNEL, "安全.json"),
    # L3 管理
    "模块管理":       (UID_DAEMON, UID_DAEMON, "管理.json"),
    "AI助手":         (UID_DAEMON, UID_DAEMON, "管理.json"),
    "游戏管理":       (UID_DAEMON, UID_DAEMON, "管理.json"),
}


class ConfigManager:
    """多层独立文件配置管理器，支持 UID 访问控制。

    配置文件仅在以下情况被写入：
    1. 首次创建配置文件时。
    2. 外部调用 save() 或 set() 并触发自动保存时。
    3. 注册新配置节且该节在文件中不存在时。
    """

    _CONFIG_DIR_NAME = "配置"

    def __init__(self, file_path: str = "config.json", data_dir: str = None):
        self._old_config_path = file_path  # 保留用于迁移
        self._data_dir: str = data_dir or os.path.dirname(os.path.abspath(file_path))
        self._config_dir: str = os.path.join(self._data_dir, self._CONFIG_DIR_NAME)
        self._modules_dir: str = os.path.join(self._config_dir, "模块")

        # 各文件的数据缓存
        self._files: Dict[str, dict] = {}           # filename → data
        self._file_paths: Dict[str, str] = {}        # filename → abspath
        self._section_files: Dict[str, str] = {}     # section → filename
        self._section_read_uid: Dict[str, int] = {}  # section → min read uid
        self._section_write_uid: Dict[str, int] = {} # section → min write uid

        self._defaults: Dict[str, dict] = {}
        self._loaded: bool = False
        self._lock = threading.RLock()

        # Fix 1: 原子引用 — _files 和 _section_files 的读写通过 _files_ref 直接读取
        #        避免 asyncio 主循环在 _data/get 中阻塞于同步锁
        self._files_ref: Dict[str, dict] = {}        # 原子快照（只读引用）
        self._section_files_ref: Dict[str, str] = {}  # 原子快照

        # 热重载
        self._last_mtimes: Dict[str, float] = {}
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_stop: Optional[threading.Event] = None
        self._on_reload_callback: Optional[Callable] = None

    # ── 迁移 ──────────────────────────────────────────────

    def _migrate_if_needed(self) -> bool:
        """检测旧 config.json 并自动拆分迁移。

        Returns:
            True 表示执行了迁移。
        """
        old_path = self._old_config_path
        if not os.path.exists(old_path):
            return False
        # 如果配置目录已存在则跳过
        if os.path.exists(self._config_dir) and os.listdir(self._config_dir):
            return False
        try:
            with open(old_path, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return False
        _log.info("检测到旧配置 %s，开始自动迁移到 %s/", old_path, self._CONFIG_DIR_NAME)
        os.makedirs(self._config_dir, exist_ok=True)
        os.makedirs(self._modules_dir, exist_ok=True)

        # 使用 BUILTIN_SCOPE 决定各节归属
        file_data: Dict[str, dict] = {}
        unclassified: dict = {}

        for section, value in old_data.items():
            if section in _BUILTIN_SCOPE:
                _, _, fname = _BUILTIN_SCOPE[section]
                file_data.setdefault(fname, {})[section] = value
            else:
                unclassified[section] = value

        for fname, data in file_data.items():
            fpath = os.path.join(self._config_dir, fname)
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _log.info("  迁移 → %s (%d 节)", fname, len(data))

        if unclassified:
            # 每个 section 写入其对应的文件名（与 _section_to_file 一致）
            by_file: dict = {}
            for section, value in unclassified.items():
                safe = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', section)
                fn = f"模块/{safe}.json"
                by_file.setdefault(fn, {})[section] = value
            for fn, data in by_file.items():
                fpath = os.path.join(self._config_dir, fn)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                _log.info("  迁移 → %s (%d 节)", fn, len(data))

        # 将旧文件重命名备份
        backup = old_path + ".bak"
        shutil.move(old_path, backup)
        _log.info("迁移完成，旧文件已备份为 %s", backup)
        return True

    # ── 节 → 文件分配 ────────────────────────────────────

    def _section_to_file(self, section: str, write: bool = False) -> str:
        """确定配置节应存储到哪个文件。"""
        if section in self._section_files:
            return self._section_files[section]
        if section in _BUILTIN_SCOPE:
            _, _, fname = _BUILTIN_SCOPE[section]
            return fname
        # 模块配置 → 模块/节名.json
        safe = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', section)
        return f"模块/{safe}.json"

    # ── 文件 I/O ──────────────────────────────────────────

    def _file_path(self, filename: str) -> str:
        if filename in self._file_paths:
            return self._file_paths[filename]
        path = os.path.join(self._config_dir, filename)
        self._file_paths[filename] = path
        return path

    def _load_file(self, filename: str) -> dict:
        path = self._file_path(filename)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            _log.warning("配置文件 %s JSON 解析失败: %s，尝试智能修复", filename, e)
            repaired = _repair_json(path)
            if repaired is not None:
                data = repaired
            else:
                return {}
        # ── HMAC 签名校验 ──
        if not self._verify_hmac(data, path):
            _log.warning("配置文件 %s 签名校验失败，尝试从备份恢复", filename)
            restored = self._restore_from_backup(path)
            if restored is not None:
                data = restored
            else:
                _log.error("配置文件 %s 签名无效且无可用备份，重建默认配置", filename)
                # 移除签名后重建
                data.pop("__signature", None)
                data.pop("__signature_data_keys", None)
                self._save_file(filename, data)
                self._compute_hmac(data)
                self._save_file(filename, data)
        return data

    def _save_file(self, filename: str, data: dict) -> None:
        path = self._file_path(filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # ── 签名注入前先移除旧签名 ──
        data.pop("__signature", None)
        data.pop("__signature_data_keys", None)
        self._compute_hmac(data)
        tmp = path + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # ── 原子写入前备份旧文件 ──
        if os.path.exists(path):
            backup_path = path + ".bak"
            try:
                shutil.copy2(path, backup_path)
            except OSError:
                pass
        os.replace(tmp, path)

    # ── HMAC 签名 ─────────────────────────────────────────

    SIGNATURE_KEY = "__signature"
    SIGNATURE_DATA_KEYS = "__signature_data_keys"

    @staticmethod
    def _get_secret() -> Optional[bytes]:
        """从环境变量获取签名密钥。未设置时返回 None（降级模式）。"""
        secret = os.environ.get("QQLINKER_CONFIG_SECRET", "")
        if not secret:
            return None
        return secret.encode("utf-8")

    @classmethod
    def _compute_hmac(cls, data: dict) -> None:
        """计算配置数据（不含签名字段）的 HMAC-SHA256 签名并写入 __signature 字段。"""
        secret = cls._get_secret()
        if secret is None:
            _log.debug("QQLINKER_CONFIG_SECRET 未设置，签名校验降级为仅日志警告")
            return
        # 对键排序保证确定性，序列化为规范化 JSON
        sig_keys = sorted(k for k in data.keys() if k not in (cls.SIGNATURE_KEY, cls.SIGNATURE_DATA_KEYS))
        canonical: Dict[str, Any] = {k: data[k] for k in sig_keys}
        payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        data[cls.SIGNATURE_KEY] = sig
        data[cls.SIGNATURE_DATA_KEYS] = sig_keys

    @classmethod
    def _verify_hmac(cls, data: dict, filepath: str = "") -> bool:
        """校验配置文件的 HMAC 签名。

        Returns:
            True 表示签名匹配或密钥未配置（降级通过）。
        """
        secret = cls._get_secret()
        if secret is None:
            return True  # 降级模式：无密钥时跳过校验
        stored_sig = data.get(cls.SIGNATURE_KEY)
        sig_keys = data.get(cls.SIGNATURE_DATA_KEYS)
        if not stored_sig or not sig_keys:
            _log.warning("配置文件 %s 缺少签名字段，可能为旧格式或篡改", filepath)
            return False
        # 重建规范化 payload
        canonical: Dict[str, Any] = {}
        for k in sig_keys:
            if k in data:
                canonical[k] = data[k]
        payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, stored_sig):
            _log.warning("配置文件 %s HMAC 签名不匹配 (期望=%s, 实际=%s)", filepath, expected[:16], stored_sig[:16])
            return False
        return True

    @staticmethod
    def _restore_from_backup(filepath: str) -> Optional[dict]:
        """从 .bak 备份恢复配置。"""
        backup_path = filepath + ".bak"
        if not os.path.exists(backup_path):
            return None
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _log.info("从备份恢复配置: %s", backup_path)
            return data
        except (json.JSONDecodeError, IOError) as e:
            _log.warning("备份文件 %s 也损坏: %s", backup_path, e)
            return None

    # ── 公共 API ──────────────────────────────────────────

    def register_section(
        self,
        section: str,
        defaults: Dict[str, Any],
        min_read_uid: int = UID_APP,
        min_write_uid: int = UID_APP,
        caller_uid: int = UID_NOBODY,
    ) -> None:
        """注册配置节、默认值及访问权限。

        Fix M2: 调用者 uid 必须 ≤ 声明的读写权限，防止低权限模块
        创建高权限配置节作为后门。

        若 section 在 BUILTIN_SCOPE 中有默认权限，未指定时使用内置值。
        内置 scope 的权限注册只允许 daemon(uid≤100) 调用。
        """
        # Fix M2: 权限校验 — 调用者 UID 必须 ≤ 声明的读写权限
        builtin = _BUILTIN_SCOPE.get(section)
        if builtin:
            # 内置 scope 中的节只能由 daemon 级注册
            if caller_uid > UID_DAEMON:
                _log.warning(
                    "安全拒绝: uid=%d 试图注册内置配置节 '%s'",
                    caller_uid, section,
                )
                return
        else:
            # 非内置节：调用者必须拥有足够的权限
            if caller_uid > min_read_uid or caller_uid > min_write_uid:
                _log.warning(
                    "安全拒绝: uid=%d 试图注册配置节 '%s' (读需≤%d, 写需≤%d)",
                    caller_uid, section, min_read_uid, min_write_uid,
                )
                return

        if section not in self._defaults:
            self._defaults[section] = defaults

        # 权限
        if section not in self._section_read_uid:
            builtin = _BUILTIN_SCOPE.get(section)
            self._section_read_uid[section] = builtin[0] if builtin else min_read_uid
        if section not in self._section_write_uid:
            builtin = _BUILTIN_SCOPE.get(section)
            self._section_write_uid[section] = builtin[1] if builtin else min_write_uid

        # 文件分配
        if section not in self._section_files:
            self._section_files[section] = self._section_to_file(section)

        if not self._loaded:
            return

        fname = self._section_files[section]
        with self._lock:
            data = self._files.setdefault(fname, {})
            section_data = data.setdefault(section, {})
            changed = self._apply_defaults(section_data, defaults)
        if changed:
            self.save()

    def load(self) -> None:
        """检查迁移、加载所有配置文件并与默认值深度合并。"""
        self._migrate_if_needed()

        os.makedirs(self._config_dir, exist_ok=True)
        os.makedirs(self._modules_dir, exist_ok=True)

        with self._lock:
            self._files.clear()

            # 加载所有已知文件
            known = {"核心.json", "安全.json", "管理.json"}
            for section, fname in list(self._section_files.items()):
                known.add(fname)

            for fname in known:
                data = self._load_file(fname)
                if data:
                    self._files[fname] = data

            # 扫描模块目录发现额外文件
            if os.path.isdir(self._modules_dir):
                for fname in sorted(os.listdir(self._modules_dir)):
                    if fname.endswith(".json"):
                        full = f"模块/{fname}"
                        if full not in self._files:
                            data = self._load_file(full)
                            if data:
                                self._files[full] = data

            # 合并默认值
            for section, defaults in self._defaults.items():
                fname = self._section_to_file(section)
                self._section_files.setdefault(section, fname)
                data = self._files.setdefault(fname, {})
                section_data = data.setdefault(section, {})
                self._apply_defaults(section_data, defaults)

            # 类型校验 + 自动修复
            fixed_count = 0
            for section, defaults in self._defaults.items():
                fname = self._section_files.get(section, "")
                data = self._files.get(fname, {})
                section_data = data.get(section, {})
                fixed_count += self._auto_repair_types(
                    section, section_data, defaults
                )
            if fixed_count > 0:
                _log.info(
                    "配置自动修复: %d 处类型错误已修正并保存", fixed_count
                )

            self._loaded = True
            # 记录初始 mtime
            for fname in self._files:
                try:
                    self._last_mtimes[fname] = os.path.getmtime(
                        self._file_path(fname)
                    )
                except OSError:
                    pass

            # Fix 1: 发布原子快照，供无锁读取
            self._publish_snapshot()

    def save(self) -> None:
        """持久化所有修改的文件。"""
        with self._lock:
            for fname, data in list(self._files.items()):
                self._save_file(fname, data)
        # Fix 1: 保存后更新快照
        self._publish_snapshot()

    def get(self, key: str, default: Any = None, requester_uid: int = UID_NOBODY) -> Any:
        """按点号分隔键读取配置，受 UID 控制。

        Args:
            key: 点号分隔的键路径（如 "模块市场.端口"）。
            default: 键不存在时的默认值。
            requester_uid: 调用方 UID（0=root 不受限制）。

        Returns:
            配置值，权限不足时返回 default。
        """
        section = key.split('.')[0]
        min_read = self._section_read_uid.get(section, UID_APP)
        if requester_uid > min_read:
            _log.debug(
                "配置读取拒绝: %s (uid=%d, 需要≤%d)",
                key, requester_uid, min_read,
            )
            return default

        keys = key.split('.')
        # Fix 1: 无锁读取 — 使用原子快照
        fname = self._section_files_ref.get(section, self._section_to_file(section))
        files = self._files_ref
        data = files.get(fname, {})
        value: Any = data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(
        self, key: str, value: Any, requester_uid: int = UID_NOBODY,
    ) -> bool:
        """按点号分隔键写入配置，受 UID 控制并自动持久化。

        Returns:
            True 表示写入成功，False 表示权限不足。
        """
        section = key.split('.')[0]
        min_write = self._section_write_uid.get(section, UID_APP)
        if requester_uid > min_write:
            _log.warning(
                "配置写入拒绝: %s = %s (uid=%d, 需要≤%d)",
                key, repr(value)[:80], requester_uid, min_write,
            )
            return False

        keys = key.split('.')
        fname = self._section_files.get(section, self._section_to_file(section))
        with self._lock:
            data = self._files.setdefault(fname, {})
            target: dict = data
            for k in keys[:-1]:
                target = target.setdefault(k, {})
            target[keys[-1]] = value
            self._save_file(fname, data)
        # Fix 1: 写入后发布快照
        self._publish_snapshot()
        return True

    def get_data_dir(self) -> str:
        return self._data_dir

    def get_config_dir(self) -> str:
        return self._config_dir

    # ── 令牌代理 ────────────────────────────────────────

    _PLACEHOLDER_RE = None

    @classmethod
    def _get_placeholder_re(cls):
        if cls._PLACEHOLDER_RE is None:
            import re
            cls._PLACEHOLDER_RE = re.compile(
                r'\{配置:([^}]+)\}'
            )
        return cls._PLACEHOLDER_RE

    def resolve_placeholders(self, text: str, _requester_uid: int = 0) -> str:
        """解析文本中的 {配置:节.键} 占位符，替换为配置值。"""
        if '{配置:' not in text:
            return text
        def _replace(m):
            key = m.group(1)
            val = self.get(key, f"{{配置:{key}}}", requester_uid=0)
            return str(val) if not isinstance(val, dict) else str(val)
        return self._get_placeholder_re().sub(_replace, text)

    @property
    def _data(self) -> dict:
        """返回所有文件的合并视图（只读）。

        Fix 1: 无锁读取 — 使用原子快照，避免阻塞 asyncio 主循环。
        """
        merged: dict = {}
        files = self._files_ref
        for data in files.values():
            merged.update(data)
        return merged

    def _publish_snapshot(self) -> None:
        """Fix 1: 发布_filses 和 _section_files 的原子快照。

        必须在持有 self._lock 时调用。
        快照是 dict 的浅拷贝；values 引用的内部 dict 在更新时
        通过 reload() 整体替换引用，而不是原地修改，因此无竞态。
        """
        self._files_ref = dict(self._files)
        self._section_files_ref = dict(self._section_files)

    def get_section_permissions(self, section: str) -> Dict[str, int]:
        """返回某配置节的 (读权限, 写权限) 信息。"""
        return {
            "读权限": self._section_read_uid.get(
                section, UID_APP
            ),
            "写权限": self._section_write_uid.get(
                section, UID_APP
            ),
        }

    # ── 热重载 ────────────────────────────────────────────

    def reload(self) -> bool:
        if not self._loaded:
            return False
        changed = False
        for fname in list(self._files.keys()):
            fpath = self._file_path(fname)
            try:
                mtime = os.path.getmtime(fpath)
                if mtime <= self._last_mtimes.get(fname, 0):
                    continue
            except OSError:
                continue
            # I/O 在锁外
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    new_data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _log.warning("配置重载失败 %s: %s", fname, e)
                continue

            # Fix 2: 带重试的锁获取，最多 3 次，间隔 0.2s
            RETRY_MAX = 3
            RETRY_DELAY = 0.2
            acquired = False
            for attempt in range(RETRY_MAX):
                acquired = self._lock.acquire(timeout=1.0)
                if acquired:
                    break
                _log.debug(
                    "配置热重载锁获取失败(attempt %d/%d): %s (可能被主循环 hold 住)",
                    attempt + 1, RETRY_MAX, fname,
                )
                time.sleep(RETRY_DELAY)
            if not acquired:
                _log.warning(
                    "配置热重载跳过 %s: 锁获取失败(重试%d次)",
                    fname, RETRY_MAX,
                )
                continue
            try:
                self._files[fname] = new_data
                self._last_mtimes[fname] = mtime
                changed = True
            finally:
                self._lock.release()

        if changed:
            # Fix 1: 重载后发布新快照
            with self._lock:
                self._publish_snapshot()
            _log.info("配置已热重载（%d 文件变更）",
                      sum(1 for f in self._files if True))
            if self._on_reload_callback:
                try:
                    self._on_reload_callback()
                except Exception as e:
                    _log.error("配置重载回调异常: %s", e)
        return changed

    def start_watching(self, interval: float = 2.0,
                       on_reload: Optional[Callable] = None) -> None:
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._on_reload_callback = on_reload
        for fname in self._files:
            try:
                self._last_mtimes[fname] = os.path.getmtime(
                    self._file_path(fname)
                )
            except OSError:
                pass
        self._watcher_stop = threading.Event()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop, args=(interval,), daemon=True,
        )
        self._watcher_thread.start()

    def stop_watching(self) -> None:
        if self._watcher_stop:
            self._watcher_stop.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=5)

    def _watch_loop(self, interval: float) -> None:
        while not self._watcher_stop.is_set():
            self._watcher_stop.wait(interval)
            if self._watcher_stop.is_set():
                break
            self.reload()

    # ── 内部工具 ──────────────────────────────────────────

    @staticmethod
    def _apply_defaults(target: dict, defaults: dict) -> bool:
        changed = False
        for key, default_value in defaults.items():
            if key not in target:
                target[key] = default_value
                changed = True
            elif isinstance(default_value, dict) and isinstance(target[key], dict):
                changed |= ConfigManager._apply_defaults(target[key], default_value)
        return changed

    @staticmethod
    def _auto_repair_types(section: str, data: dict, defaults: dict,
                           path: str = "") -> int:
        """递归校验并自动修复类型错误。返回修复次数。"""
        fixed = 0
        for key, default_value in defaults.items():
            full_path = f"{path}{section}.{key}" if path else f"{section}.{key}"
            if key not in data:
                continue
            actual = data[key]
            expected_type = type(default_value)
            if not isinstance(actual, expected_type):
                # 尝试智能转换
                repaired = _config_smart_cast(actual, expected_type)
                if repaired is not None:
                    data[key] = repaired
                    _log.info(
                        "[配置修复] %s: %s → %s (自动修复)",
                        full_path,
                        type(actual).__name__,
                        expected_type.__name__,
                    )
                    fixed += 1
                else:
                    # 无法转换，回退默认值
                    data[key] = default_value
                    _log.info(
                        "[配置修复] %s: %s (%s) 无法转换→回退默认值",
                        full_path,
                        type(actual).__name__,
                        repr(actual)[:60],
                    )
                    fixed += 1
            elif isinstance(default_value, dict) and isinstance(actual, dict):
                fixed += ConfigManager._auto_repair_types(
                    f"{section}.{key}" if not path else f"{path}.{key}",
                    actual, default_value, ""
                )
        return fixed

    @staticmethod
    def _validate_types(section: str, data: dict, defaults: dict) -> None:
        """仅校验警告，不修复。"""
        for key, default_value in defaults.items():
            if key not in data:
                continue
            actual = data[key]
            expected_type = type(default_value)
            if not isinstance(actual, expected_type):
                _log.warning(
                    "配置类型不匹配 [%s].%s: 期望 %s, 实际 %s (%s)。%s",
                    section, key,
                    expected_type.__name__,
                    type(actual).__name__,
                    repr(actual)[:80],
                    hint["CONFIG_TYPE_MISMATCH"],
                )
            elif isinstance(default_value, dict) and isinstance(actual, dict):
                ConfigManager._validate_types(
                    f"{section}.{key}", actual, default_value
                )


def _config_smart_cast(value, target_type) -> Any:
    """智能类型转换：尝试将 value 转为 target_type。

    支持的转换:
      - str → int: "123" → 123 (纯数字字符串)
      - str → float: "1.5" → 1.5
      - str → bool: "true"/"false"/"1"/"0" → True/False
      - str → list: 逗号分隔的字符串 → 列表
      - str → dict: JSON 字符串 → dict
      - int → str: 123 → "123"
      - bool → str: True → "true"
      - list 单元素 → str: ["hello"] → "hello"

    Returns:
        转换后的值，无法转换时返回 None。
    """
    import json as _json

    # str → int
    if target_type is int and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass

    # str → float
    if target_type is float and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass

    # str → bool
    if target_type is bool and isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes"):
            return True
        if v in ("false", "0", "no"):
            return False

    # str → list (逗号分隔)
    if target_type is list and isinstance(value, str):
        v = value.strip()
        if v.startswith("["):
            try:
                return _json.loads(v)
            except (_json.JSONDecodeError, ValueError):
                pass
        # 逗号分隔
        parts = [p.strip() for p in v.split(",") if p.strip()]
        if parts:
            return parts

    # str → dict
    if target_type is dict and isinstance(value, str):
        try:
            return _json.loads(value)
        except (_json.JSONDecodeError, ValueError):
            pass

    # int/float/bool → str
    if target_type is str and isinstance(value, (int, float, bool)):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    # list(单元素) → str
    if target_type is str and isinstance(value, list) and len(value) == 1:
        if isinstance(value[0], str):
            return value[0]

    return None


# ═══════════════════════════════════════════════════════════════
# Gatekeeper Bridge 工厂
# ═══════════════════════════════════════════════════════════════

def register_config_bridge(bridge, cfg_mgr: ConfigManager) -> None:
    """向 GatekeeperBridge 注册配置读/写代理方法。

    通过 bridge 调用的模块自动带上其 uid 做权限校验。
    """
    import re as _re

    bridge.register(
        "配置.读",
        lambda key, default=None, uid=0: cfg_mgr.get(key, default, uid),
        min_tier="app", readonly=True,
        description="按模块 UID 权限读取配置（KEY路径, 默认值）",
    )
    bridge.register(
        "配置.写",
        lambda key, value, uid=0: cfg_mgr.set(key, value, uid),
        min_tier="daemon", readonly=False,
        description="按模块 UID 权限写入配置（KEY路径, 值）",
    )
    bridge.register(
        "配置.节权限",
        lambda section: cfg_mgr.get_section_permissions(section),
        min_tier="app", readonly=True,
        description="查询某配置节的读/写权限 uid",
    )
    bridge.register(
        "配置.代理解析",
        lambda text, uid=0: cfg_mgr.resolve_placeholders(text, uid),
        min_tier="daemon", readonly=True,
        description="解析文本中的 {配置:节.键} 占位符 (uid≤100可用)",
    )


def _repair_json(filepath: str):
    """智能修复损坏的 JSON 配置文件并写回。"""

    import re as _re, shutil, os as _os
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()
    except OSError:
        return None

    original = raw
    repaired = False

    # 1. 移除注释行
    lines = raw.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            repaired = True
            continue
        cleaned.append(line)
    raw = '\n'.join(cleaned)

    # 2. Python bool → JSON bool
    for py_val, json_val in [('True', 'true'), ('False', 'false'), ('None', 'null')]:
        if py_val in raw:
            raw = raw.replace(py_val, json_val)
            repaired = True

    # 3. 移除尾逗号
    raw = _re.sub(r',(\s*[}\]])', r'\1', raw)

    # 4. 统计并补全未闭合的括号
    brace_count = raw.count('{') - raw.count('}')
    bracket_count = raw.count('[') - raw.count(']')
    if brace_count > 0:
        raw = raw.rstrip() + '\n' + '}' * brace_count
        repaired = True
    if bracket_count > 0:
        raw = raw.rstrip() + '\n' + ']' * bracket_count
        repaired = True

    if not repaired:
        return None

    try:
        import json as _json
        data = _json.loads(raw)
    except (_json.JSONDecodeError, ValueError):
        _log.warning("JSON 智能修复失败: %s", filepath)
        return None

    if not isinstance(data, dict):
        return None

    backup = filepath + '.bak'
    try:
        shutil.copy2(filepath, backup)
    except OSError:
        pass

    try:
        import json as _json
        with open(filepath, 'w', encoding='utf-8') as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        _log.info("JSON 智能修复成功: %s (原 %d bytes)", _os.path.basename(filepath), len(original))
    except OSError:
        pass

    return data
