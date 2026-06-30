import hashlib
import time
import threading
from typing import Dict

from ..channel_host import Library


class DedupStore:
    """基于时间窗口的消息去重。"""

    def __init__(self, window_seconds: float = 60.0):
        self._window = window_seconds
        self._seen: Dict[str, float] = {}
        self._lock = threading.Lock()

    def is_duplicate(self, group_id: int, user_id: int, message: str) -> bool:
        key = hashlib.md5(f"{group_id}:{user_id}:{message}".encode()).hexdigest()
        now = time.time()
        with self._lock:
            self._cleanup(now)
            if key in self._seen:
                return True
            self._seen[key] = now
            return False

    def check_and_add_id(self, msg_id: str) -> bool:
        """基于消息 ID 的去重检查。

        Returns:
            True 表示是新消息（已添加），False 表示重复。
        """
        now = time.time()
        with self._lock:
            self._cleanup(now)
            if msg_id in self._seen:
                return False
            self._seen[msg_id] = now
            return True

    def check_and_add_command(self, cmd_id: str, short_ttl: int = 5) -> bool:
        """命令消息去重（短 TTL）。

        Args:
            cmd_id: 命令逻辑 ID。
            short_ttl: 短期去重窗口秒数（默认 5s）。

        Returns:
            True 表示是新命令（已添加），False 表示重复。
        """
        now = time.time()
        key = f"cmd:{cmd_id}"
        with self._lock:
            # 使用短 TTL 检查
            if key in self._seen and (now - self._seen[key]) < short_ttl:
                return False
            self._seen[key] = now
            return True

    def check_and_add_content(self, content: str, user_id: int) -> bool:
        """基于内容指纹的去重检查。

        Args:
            content: 消息内容。
            user_id: 用户 ID（参与指纹计算）。

        Returns:
            True 表示是新内容（已添加），False 表示重复。
        """
        fingerprint = hashlib.md5(f"{user_id}:{content}".encode()).hexdigest()
        return self.check_and_add_id(f"content:{fingerprint}")

    def get_stats(self) -> dict:
        """返回去重存储统计信息。"""
        with self._lock:
            now = time.time()
            self._cleanup(now)
            return {
                "entries": len(self._seen),
                "window_seconds": self._window,
            }

    def _cleanup(self, now: float) -> None:
        expired = [k for k, t in self._seen.items() if now - t > self._window]
        for k in expired:
            del self._seen[k]


class DedupLibrary(Library):
    """消息去重库。"""

    name = "dedup"
    version = "1.6.0"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        config = self.services.get("config")
        window = config.get("去重.窗口秒", 60.0)
        store = DedupStore(window)
        self.services.register("dedup", store, mid=300)

    async def unmount(self) -> None:
        pass
