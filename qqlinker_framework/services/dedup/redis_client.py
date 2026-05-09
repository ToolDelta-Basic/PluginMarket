# services/dedup/redis_client.py
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
    def __init__(self, config: DedupConfig):
        self.config = config
        self._client: Optional["redis.Redis"] = None
        self._lock = threading.RLock()
        self._last_failure_time = 0
        self._failure_cooldown = 30

    def _connect(self) -> Optional["redis.Redis"]:
        if not self.config.redis_enabled or not REDIS_AVAILABLE:
            return None
        try:
            client = redis.Redis.from_url(
                self.config.redis_url,
                password=self.config.redis_password,
                socket_timeout=self.config.redis_timeout,
                socket_connect_timeout=self.config.redis_timeout,
                decode_responses=True
            )
            client.ping()
            return client
        except Exception as e:
            self._last_failure_time = time.time()
            raise RedisUnavailableError(f"Redis 连接失败: {e}")

    @property
    def client(self) -> Optional["redis.Redis"]:
        if not self.config.redis_enabled or not REDIS_AVAILABLE:
            return None
        with self._lock:
            if self._client is None:
                if time.time() - self._last_failure_time < self._failure_cooldown:
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
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except:
                    pass
            self._client = None

    def execute(self, func_name: str, *args, **kwargs):
        client = self.client
        if client is None:
            return None
        try:
            func = getattr(client, func_name)
            return func(*args, **kwargs)
        except Exception:
            self.reset()
            return None