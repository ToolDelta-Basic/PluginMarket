"""Redis 客户端封装，支持自动重连与冷却。"""
import threading
import time
from typing import Optional

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

        Returns:
            Redis 客户端或 None。
        """
        if not self.config.redis_enabled or not REDIS_AVAILABLE:
            return None
        with self._lock:
            if self._client is None:
                if (
                    time.time() - self._last_failure_time
                    < self._failure_cooldown
                ):
                    return None
                try:
                    self._client = self._connect()
                except RedisUnavailableError:
                    return None
            else:
                try:
                    self._client.ping()
                except Exception:
                    self._client = None
                    return None
            return self._client

    def reset(self):
        """主动断开并重置 Redis 客户端。"""
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None

    def execute(self, func_name: str, *args, **kwargs):
        """执行 Redis 命令，自动处理异常和重连。

        Args:
            func_name: Redis 客户端方法名。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            命令执行结果，失败返回 None。
        """
        client = self.client
        if client is None:
            return None
        try:
            func = getattr(client, func_name)
            return func(*args, **kwargs)
        except Exception:
            self.reset()
            return None
