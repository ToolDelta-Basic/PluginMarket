"""崩溃恢复引擎 — 健康心跳 + 崩溃检测 + 检查点 + 递归防护 + 防滥用

═══════════════════════════════════════════════════════════════════════════
 架构
═══════════════════════════════════════════════════════════════════════════
 · .heartbeat 健康文件          — 每 N 秒 touch，外部 watchdog/cron 监控
 · .crashed 崩溃标记            — 正常退出删除，崩溃时残留，启动时检测
 · .restart_guard 递归防护      — 防止配置错误导致的无限重启循环
 · checkpoint() 模块约定        — 模块声明式持久化关键状态
 · restore_checkpoint() 恢复    — 启动恢复模式时重新注入
 · 定期检查点 (30s)             — 框架调度器自动轮询模块 checkpoint
═══════════════════════════════════════════════════════════════════════════

 递归重启防护
═══════════════════════════════════════════════════════════════════════════
 如果框架在 N 秒内崩溃了 M 次，视为故障循环，拒绝继续重启。

 参数:
   RESTART_WINDOW_SECONDS = 300    # 5 分钟窗口
   RESTART_MAX_IN_WINDOW  = 3      # 窗口内最多 3 次

 存储: data/.restart_guard.json
   {
     "history": [ts1, ts2, ts3, ...],  # 最近崩溃时间戳
     "last_clean_exit": ts              # 上一次完全正常退出的时间
   }

 当触发防护时，写入 data/.restart_blocked 标记文件，
 外部 watchdog 应检查此文件并停止重试。
═══════════════════════════════════════════════════════════════════════════
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Callable, Optional
from ..kernel.services import TIER_NOBODY

_log = logging.getLogger(__name__)

# ── 常量 ──
RESTART_WINDOW_SECONDS = 300   # 5 分钟窗口
RESTART_MAX_IN_WINDOW = 3      # 窗口内最多 3 次重启
MAX_CHECKPOINT_SIZE = 256 * 1024  # 检查点最大 256KB
# nobody 级模块 uid 阈值
_MODULE_NAME_RE = re.compile(r'[^a-zA-Z0-9_-]')  # 模块名净化
_CHECKPOINT_HEADER = b"QQLINKER_CHECKPOINT_V1"  # HMAC 签名前缀


class RecoveryEngine:
    """崩溃恢复引擎：心跳、检测、检查点调度、递归防护。"""

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._heartbeat_path = os.path.join(data_dir, "数据", ".心跳")
        self._crashed_path = os.path.join(data_dir, "数据", ".崩溃标记")
        self._restart_guard_path = os.path.join(
            data_dir, "数据", ".restart_guard.json"
        )
        self._restart_blocked_path = os.path.join(
            data_dir, "数据", ".restart_blocked"
        )
        self._checkpoint_dir = os.path.join(data_dir, "数据", "检查点")
        os.makedirs(os.path.dirname(self._heartbeat_path), exist_ok=True)
        os.makedirs(self._checkpoint_dir, exist_ok=True)

        # 运行时状态
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._checkpoint_task: Optional[asyncio.Task] = None
        self._heartbeat_interval: float = 5.0
        self._checkpoint_interval: float = 30.0
        self._stop_event = asyncio.Event()

        # 模块注册 — 仅持有强引用避免阻碍 GC
        self._checkpoint_modules: list = []

        # HMAC 签名密钥 — 持久化到磁盘，跨重启保持一致
        self._hmac_key = self._load_or_create_hmac_key()

        # 崩溃标记 — 启动时写入，正常退出时由 clean_shutdown() 删除
        self._mark_crashed()

    # ═══════════════════════════════════════════════════════════
    # 工具
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def sanitize_module_name(name: str) -> str:
        """净化模块名，防止路径穿越。"""
        sanitized = _MODULE_NAME_RE.sub('_', name)
        if sanitized != name:
            _log.warning("模块名已净化: '%s' → '%s'", name, sanitized)
        return sanitized or "unknown"

    def _load_or_create_hmac_key(self) -> bytes:
        """加载或生成 HMAC 签名密钥，持久化到磁盘跨重启保持一致。

        密钥存储在 data/.checkpoint_key 中，仅在首次运行时生成。
        """
        key_path = os.path.join(self._data_dir, "数据", ".检查点密钥")
        try:
            if os.path.exists(key_path):
                with open(key_path, "rb") as f:
                    key = f.read()
                if len(key) == 32:
                    return key
                _log.warning("检查点密钥长度异常，重新生成")
        except OSError as e:
            _log.debug("读取检查点密钥失败: %s，将重新生成", e)
        # 生成新密钥
        key = secrets.token_bytes(32)
        try:
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, "wb") as f:
                f.write(key)
            _log.info("已生成检查点签名密钥")
        except OSError as e:
            _log.warning("无法持久化检查点密钥: %s，本次启动期间检查点签名有效", e)
        return key

    # ═══════════════════════════════════════════════════════════
    # 心跳
    # ═══════════════════════════════════════════════════════════

    def _touch_heartbeat(self) -> None:
        """同步 touch 心跳文件（mtime 更新，无 IO 压力）。"""
        try:
            if os.path.exists(self._heartbeat_path):
                os.utime(self._heartbeat_path, None)
            else:
                with open(self._heartbeat_path, 'w') as f:
                    f.write(str(int(time.time())))
        except OSError:
            pass  # 磁盘满了也尽量不崩溃

    async def _heartbeat_loop(self) -> None:
        """异步心跳循环。"""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._heartbeat_interval,
                )
                break
            except asyncio.TimeoutError:
                self._touch_heartbeat()

    def start_heartbeat(self, interval: float = 5.0):
        """启动心跳（在 asyncio 事件循环中）。"""
        self._heartbeat_interval = interval
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        _log.info("心跳已启动 (%.1fs)", interval)

    # ═══════════════════════════════════════════════════════════
    # 崩溃标记
    # ═══════════════════════════════════════════════════════════

    def _mark_crashed(self) -> None:
        """写入崩溃标记（框架启动时调用，表示「可能未完成」）。"""
        try:
            with open(self._crashed_path, 'w') as f:
                f.write(str(int(time.time())))
        except OSError as e:
            _log.warning("无法写入崩溃标记 %s: %s", self._crashed_path, e)

    def clean_shutdown(self) -> None:
        """正常退出：删除崩溃标记和心跳文件。"""
        for path in (self._crashed_path, self._heartbeat_path):
            try:
                os.remove(path)
            except (FileNotFoundError, OSError):
                pass
        _log.debug("崩溃标记和心跳文件已清理")

    def was_crashed(self) -> bool:
        """返回 True 表示上次是非正常退出。"""
        return os.path.exists(self._crashed_path)

    # ═══════════════════════════════════════════════════════════
    # 递归重启防护
    # ═══════════════════════════════════════════════════════════

    def check_restart_guard(self) -> bool:
        """检查是否允许重启。返回 False 表示已被防护拦截。

        逻辑:
          1. 无防护文件 → 允许
          2. 最近 N 秒内崩溃次数 >= M → 拒绝，写 .restart_blocked
          3. 否则允许，记录本次启动时间戳
        """
        now = time.time()

        if os.path.exists(self._restart_blocked_path):
            _log.critical(
                "递归重启防护已激活 (文件: %s)。"
                "请手动检查配置错误后删除此文件。",
                self._restart_blocked_path,
            )
            return False

        history: list[float] = []
        if os.path.exists(self._restart_guard_path):
            try:
                with open(self._restart_guard_path, 'r') as f:
                    data = json.load(f)
                history = data.get("history", [])
                if not isinstance(history, list):
                    history = []
            except (json.JSONDecodeError, IOError):
                history = []

        # 只保留窗口内的记录
        recent = [t for t in history if now - t < RESTART_WINDOW_SECONDS]

        if len(recent) >= RESTART_MAX_IN_WINDOW:
            _log.critical(
                "‼️ 递归重启防护触发: %d 秒内崩溃了 %d 次 (阈值: %d)。"
                "框架拒绝继续重启。",
                RESTART_WINDOW_SECONDS,
                len(recent),
                RESTART_MAX_IN_WINDOW,
            )
            try:
                with open(self._restart_blocked_path, 'w') as f:
                    json.dump({
                        "reason": "too_many_crashes",
                        "window_seconds": RESTART_WINDOW_SECONDS,
                        "max_restarts": RESTART_MAX_IN_WINDOW,
                        "crash_times": recent,
                        "blocked_at": now,
                    }, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
            return False

        # 记录本次启动
        recent.append(now)
        try:
            with open(self._restart_guard_path, 'w') as f:
                json.dump({
                    "history": recent,
                    "last_launch": now,
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

        _log.info(
            "重启防护: 窗口内第 %d 次启动 (阈值: %d)",
            len(recent), RESTART_MAX_IN_WINDOW,
        )
        return True

    def clear_restart_block(self) -> bool:
        """手动清除防护阻断（控制台命令用）。"""
        try:
            os.remove(self._restart_blocked_path)
        except FileNotFoundError:
            return False
        except OSError:
            return False
        _log.info("递归重启防护已手动清除")
        return True

    def mark_clean_exit(self) -> None:
        """记录一次正常退出时间戳，用于判断「上次是否正常」"""
        try:
            if os.path.exists(self._restart_guard_path):
                with open(self._restart_guard_path, 'r') as f:
                    data = json.load(f)
                data["last_clean_exit"] = time.time()
                with open(self._restart_guard_path, 'w') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ═══════════════════════════════════════════════════════════
    # 检查点引擎
    # ═══════════════════════════════════════════════════════════

    def register_module(self, module) -> None:
        """注册需要定期检查点的模块。

        强制执行:
          1. 模块必须覆写 checkpoint()（区别于基类默认返回 None）
          2. nobody 级 (uid>=TIER_NOBODY) 模块禁止使用检查点
        """
        if not hasattr(module, 'checkpoint') or not callable(module.checkpoint):
            _log.warning(
                "模块 '%s' 未实现 checkpoint() 方法，跳过注册",
                getattr(module, 'name', type(module).__name__),
            )
            return
        # 排除基类的默认实现（通过 MRO 检测）
        base_checkpoint = type(module).__mro__[1].__dict__.get('checkpoint')
        if base_checkpoint is not None and type(module).checkpoint is base_checkpoint:
            _log.debug(
                "模块 '%s' 未覆写 checkpoint()（使用基类默认），跳过",
                module.name,
            )
            return
        # UID 隔离: nobody 级模块禁止 checkpoint
        if getattr(module, 'uid', 0) >= TIER_NOBODY:
            _log.warning(
                "模块 '%s' (uid=%d, nobody 级) 禁止使用检查点功能，跳过注册",
                module.name, module.uid,
            )
            return
        self._checkpoint_modules.append(module)
        _log.debug("模块 '%s' 已注册 checkpoint", module.name)

    async def _checkpoint_loop(self) -> None:
        """定期 checkpoint 循环。"""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._checkpoint_interval,
                )
                break
            except asyncio.TimeoutError:
                await self._save_all_checkpoints()

    def start_checkpoint_loop(self, interval: float = 30.0) -> None:
        """启动定期检查点。"""
        self._checkpoint_interval = interval
        if self._checkpoint_task and not self._checkpoint_task.done():
            return
        self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())
        _log.info("检查点引擎已启动 (%.1fs)", interval)

    async def _save_all_checkpoints(self) -> None:
        """遍历所有已注册模块，调用 checkpoint() 并保存到磁盘。"""
        for mod in self._checkpoint_modules:
            try:
                data = mod.checkpoint()
                if data is None:
                    continue
                if not isinstance(data, dict):
                    _log.warning(
                        "模块 '%s' checkpoint() 返回非 dict: %s",
                        mod.name, type(data).__name__,
                    )
                    continue
                await self._save_module_checkpoint(mod.name, data)
            except Exception as e:
                _log.error(
                    "模块 '%s' checkpoint 失败: %s", mod.name, e
                )

    async def _save_module_checkpoint(
        self, module_name: str, data: dict
    ) -> None:
        """原子写入模块检查点文件（含 HMAC 签名 + 大小限制）。"""
        import tempfile

        safe_name = self.sanitize_module_name(module_name)
        if safe_name != module_name:
            _log.warning("检查点模块名已净化: '%s' → '%s'", module_name, safe_name)

        # 大小限制
        raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(raw) > MAX_CHECKPOINT_SIZE:
            _log.error(
                "模块 '%s' 检查点过大 (%d bytes, 上限 %d bytes)，拒绝保存",
                module_name, len(raw), MAX_CHECKPOINT_SIZE,
            )
            return

        # HMAC 签名
        sig = hmac.digest(self._hmac_key, _CHECKPOINT_HEADER + raw, hashlib.sha256)
        payload = {"data": data, "sig": sig.hex()}

        path = os.path.join(self._checkpoint_dir, f"{safe_name}.json")
        try:
            tmpfd, tmppath = tempfile.mkstemp(
                dir=self._checkpoint_dir,
                prefix=f"{safe_name}.",
                suffix=".tmp",
            )
            with os.fdopen(tmpfd, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmppath, path)
        except (OSError, TypeError) as e:
            _log.error("写入检查点 '%s' 失败: %s", module_name, e)

    async def restore_all_checkpoints(self) -> dict[str, dict]:
        """恢复模式下：加载所有检查点，验签后返回 {module_name: data}。

        Returns:
            模块名到检查点数据的映射。调用方应遍历并调用模块的 restore_checkpoint()。
        """
        result = {}
        if not os.path.isdir(self._checkpoint_dir):
            return result

        for entry in sorted(os.listdir(self._checkpoint_dir)):
            if not entry.endswith('.json'):
                continue
            path = os.path.join(self._checkpoint_dir, entry)
            if not os.path.isfile(path):
                continue
            module_name = entry[:-5]
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
                if not isinstance(payload, dict):
                    _log.warning("检查点 '%s' 格式异常，跳过", module_name)
                    continue

                # HMAC 验签
                data = payload.get("data")
                sig_hex = payload.get("sig")
                if not isinstance(data, dict) or not isinstance(sig_hex, str):
                    _log.warning("检查点 '%s' 缺少签名或数据，跳过", module_name)
                    continue
                raw = json.dumps(
                    data, ensure_ascii=False, separators=(',', ':')
                ).encode('utf-8')
                expected_sig = hmac.digest(
                    self._hmac_key, _CHECKPOINT_HEADER + raw, hashlib.sha256
                )
                try:
                    actual_sig = bytes.fromhex(sig_hex)
                except ValueError:
                    _log.warning("检查点 '%s' 签名格式无效，跳过", module_name)
                    continue
                if not hmac.compare_digest(expected_sig, actual_sig):
                    _log.error(
                        "检查点 '%s' HMAC 签名不匹配！可能被篡改，跳过",
                        module_name,
                    )
                    continue

                result[module_name] = data
                _log.info(
                    "检查点已加载: %s (%d 键)",
                    module_name, len(data),
                )
            except (json.JSONDecodeError, IOError) as e:
                _log.error("检查点 '%s' 加载失败: %s", module_name, e)

        return result

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    async def stop(self) -> None:
        """停止心跳和检查点循环。"""
        self._stop_event.set()
        for task in (self._heartbeat_task, self._checkpoint_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        # 最后一次 checkpoint（尽力而为）
        await self._save_all_checkpoints()
        _log.info("恢复引擎已停止")

    def get_heartbeat_path(self) -> str:
        """返回心跳文件路径（供外部 watchdog 使用）。"""
        return self._heartbeat_path

    def get_blocked_path(self) -> str:
        """返回阻断标记路径。"""
        return self._restart_blocked_path
