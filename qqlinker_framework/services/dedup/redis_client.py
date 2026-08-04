import threading
import time
from typing import Optional
import logging
_log = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .config import DedupConfig
from .exceptions import RedisUnavailableError


class RedisClient:
    """Redis 客户端封装，提供自动重连和故障冷却机制。"""

    def __init__(self, config: DedupConfig):
        """初始化 Redis 客户端。

        Args:
            config: 去重配置对象。
        """
        self.config = config
        self._client: Optional["redis.Redis"] = None
        self._lock = threading.RLock()
        self._last_failure_time = 0
        self._failure_cooldown = 30

    def _connect(self) -> Optional["redis.Redis"]:
        """建立 Redis 连接并测试 ping。

        Returns:
            Redis 客户端实例。

        Raises:
            RedisUnavailableError: 连接失败。
        """
        if not self.config.redis_enabled or not REDIS_AVAILABLE:
            return None
        try:
            client = redis.Redis.from_url(
                self.config.redis_url,
                password=self.config.redis_password,
                socket_timeout=self.config.redis_timeout,
                socket_connect_timeout=self.config.redis_timeout,
                decode_responses=True,
            )
            client.ping()
            return client
        except Exception as e:
            self._last_failure_time = time.time()
            raise RedisUnavailableError(f"Redis 连接失败: {e}")

    @property
    def client(self) -> Optional["redis.Redis"]:
        """获取当前 Redis 客户端，如已失效则尝试重连。

        修复：ping() 移到锁外执行，避免 RLock 内网络 I/O 阻塞调用者。
        使用双重检查模式：先快速读，需要时才加锁重建。

        Returns:
            Redis 客户端或 None。
        """
        if not self.config.redis_enabled or not REDIS_AVAILABLE:
            return None

        # 快速路径：客户端存在，锁外 ping 验证（带超时保护）
        client_snapshot = self._client
        if client_snapshot is not None:
            try:
                client_snapshot.ping()
                return client_snapshot
            except Exception as e:
                _log.warning("redis_client.client: %s", e)

        # 慢路径：需要重建连接，加锁保护
        with self._lock:
            # 双重检查：可能已被其他线程重建
            if self._client is not None:
                try:
                    self._client.ping()
                    return self._client
                except Exception:
                    self._client = None

            # 冷却期检查
            if (
                time.time() - self._last_failure_time
                < self._failure_cooldown
            ):
                return None

            # 重建连接（锁内调用 _connect，但 _connect 自带超时）
            try:
                self._client = self._connect()
            except RedisUnavailableError:
                return None
            return self._client

    def reset(self):
        """主动断开并重置 Redis 客户端。"""
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception as e:
                    _log.warning("redis_client.reset: %s", e)
            self._client = None

    def execute(self, func_name: str, *args, **kwargs):
        """执行 Redis 命令，自动处理异常和重连。

        Args:
            func_name: Redis 客户端方法名。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            命令执行结果，连接不可用时返回 None。

        Raises:
            RedisUnavailableError: 命令执行异常（连接中断等）。
        """
        client = self.client
        if client is None:
            return None
        try:
            func = getattr(client, func_name)
            return func(*args, **kwargs)
        except Exception as e:
            self.reset()
            raise RedisUnavailableError(
                f"Redis 命令 '{func_name}' 执行失败: {e}"
            ) from e
