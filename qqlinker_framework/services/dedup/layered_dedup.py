"""多层去重引擎：本地TTL缓存 + Redis + 布隆过滤器。"""
import time
import hashlib
import threading
import heapq
from typing import Optional

try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    CACHETOOLS_AVAILABLE = False

from .config import DedupConfig
from .redis_client import RedisClient
from .bloom_filter import BloomFilter


class _SimpleTTLCache:
    """基于堆的 TTL 缓存实现，提供 O(log n) 的过期淘汰。"""

    def __init__(self, maxsize: int = 10000, ttl: int = 300):
        """初始化缓存。

        Args:
            maxsize: 最大条目数。
            ttl: 存活时间（秒）。
        """
        self._cache = {}                      # key -> (value, timestamp)
        self._heap = []                       # 最小堆 (timestamp, key)
        self.maxsize = maxsize
        self.ttl = ttl
        self.lock = threading.RLock()

    def __contains__(self, key):
        """检查 key 是否存在且未过期。"""
        with self.lock:
            self._cleanup(time.time())
            return key in self._cache

    def __getitem__(self, key):
        """获取值，过期则抛出 KeyError。"""
        with self.lock:
            now = time.time()
            self._cleanup(now)
            value, timestamp = self._cache[key]
            if now - timestamp <= self.ttl:
                return value
            else:
                del self._cache[key]
                raise KeyError(key)

    def __setitem__(self, key, value):
        """设置值，超过最大容量时淘汰最旧条目。"""
        with self.lock:
            now = time.time()
            self._cleanup(now)
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = (value, now)
            heapq.heappush(self._heap, (now, key))
            while len(self._cache) > self.maxsize:
                while self._heap:
                    t, k = heapq.heappop(self._heap)
                    if k in self._cache and self._cache[k][1] == t:
                        del self._cache[k]
                        break

    def pop(self, key, default=None):
        """弹出值。"""
        with self.lock:
            if key in self._cache:
                return self._cache.pop(key)[0]
            return default

    def clear(self):
        """清空缓存。"""
        with self.lock:
            self._cache.clear()
            self._heap.clear()

    def __len__(self):
        """返回当前有效条目数。"""
        with self.lock:
            self._cleanup(time.time())
            return len(self._cache)

    def _cleanup(self, now):
        """清理过期条目。"""
        while self._heap and now - self._heap[0][0] > self.ttl:
            t, k = heapq.heappop(self._heap)
            if k in self._cache and self._cache[k][1] == t:
                del self._cache[k]


class LayeredDedup:
    """多层去重管理器：本地缓存 + Redis + 布隆过滤器，支持降级。"""

    def __init__(self, config: DedupConfig):
        """初始化去重引擎。

        Args:
            config: 去重配置。
        """
        self.config = config
        if CACHETOOLS_AVAILABLE:
            self._local_id_cache = TTLCache(
                maxsize=config.local_max_size, ttl=config.local_id_ttl
            )
            self._local_content_cache = TTLCache(
                maxsize=config.local_max_size,
                ttl=config.local_content_ttl,
            )
        else:
            self._local_id_cache = _SimpleTTLCache(
                maxsize=config.local_max_size, ttl=config.local_id_ttl
            )
            self._local_content_cache = _SimpleTTLCache(
                maxsize=config.local_max_size,
                ttl=config.local_content_ttl,
            )

        self._local_lock = threading.RLock()
        self.redis = (
            RedisClient(config) if config.redis_enabled else None
        )
        self.bloom = (
            BloomFilter(config, self.redis)
            if self.redis and config.bloom_enabled
            else None
        )

        self.stats = {"local_hits": 0, "redis_hits": 0}

    def _make_fingerprint(self, content: str, user_id: int) -> str:
        """生成内容指纹（MD5(user_id:content)）。

        Args:
            content: 文本内容。
            user_id: 用户标识。

        Returns:
            指纹字符串。
        """
        normalized = content.strip()[:200]
        return hashlib.md5(f"{user_id}:{normalized}".encode()).hexdigest()

    def check_and_add_id(self, msg_id: str) -> bool:
        """基于消息 ID 的去重检查。

        Args:
            msg_id: 消息唯一标识。

        Returns:
            True 表示新消息，False 表示重复。
        """
        with self._local_lock:
            if msg_id in self._local_id_cache:
                self.stats["local_hits"] += 1
                return False
            self._local_id_cache[msg_id] = time.time()

        if self.redis:
            try:
                result = self.redis.execute(
                    "set",
                    f"dedup:msgid:{msg_id}",
                    "1",
                    "nx",
                    "ex",
                    self.config.redis_id_ttl,
                )
                if result is True:
                    return True
                else:
                    with self._local_lock:
                        self._local_id_cache.pop(msg_id, None)
                    self.stats["redis_hits"] += 1
                    return False
            except Exception:
                if self.config.fallback_to_local_on_redis_failure:
                    return True
                else:
                    with self._local_lock:
                        self._local_id_cache.pop(msg_id, None)
                    return False
        return True

    def check_and_add_content(self, content: str, user_id: int) -> bool:
        """基于内容指纹的去重检查。

        Args:
            content: 文本内容。
            user_id: 用户标识。

        Returns:
            True 表示新内容，False 表示重复。
        """
        fingerprint = self._make_fingerprint(content, user_id)
        with self._local_lock:
            if fingerprint in self._local_content_cache:
                self.stats["local_hits"] += 1
                return False

        if self.bloom:
            if not self.bloom.check_and_add(fingerprint):
                with self._local_lock:
                    self._local_content_cache[fingerprint] = time.time()
                return True

        if self.redis:
            try:
                result = self.redis.execute(
                    "set",
                    f"dedup:content:{fingerprint}",
                    "1",
                    "nx",
                    "ex",
                    self.config.redis_content_ttl,
                )
                if result is True:
                    with self._local_lock:
                        self._local_content_cache[fingerprint] = time.time()
                    return True
                else:
                    self.stats["redis_hits"] += 1
                    return False
            except Exception:
                if self.config.fallback_to_local_on_redis_failure:
                    with self._local_lock:
                        if fingerprint in self._local_content_cache:
                            return False
                        self._local_content_cache[fingerprint] = time.time()
                    return True
                else:
                    return False
        else:
            with self._local_lock:
                self._local_content_cache[fingerprint] = time.time()
            return True

    def acquire_lock(
        self, resource: str, ttl: Optional[int] = None
    ) -> bool:
        """获取分布式锁（如果启用）。

        Args:
            resource: 资源标识。
            ttl: 锁超时。

        Returns:
            是否获取成功。
        """
        if not self.config.lock_enabled or not self.redis:
            return True
        ttl = ttl or self.config.lock_timeout
        lock_key = f"dedup:lock:{resource}"
        lock_value = f"{time.time()}:{threading.get_ident()}"
        for _ in range(self.config.lock_retry_times):
            result = self.redis.execute(
                "set", lock_key, lock_value, "nx", "ex", ttl
            )
            if result:
                return True
            time.sleep(self.config.lock_retry_delay)
        return False

    def release_lock(self, resource: str):
        """释放分布式锁。

        Args:
            resource: 资源标识。
        """
        if self.config.lock_enabled and self.redis:
            self.redis.execute("del", f"dedup:lock:{resource}")

    def clear_local(self):
        """清空所有本地缓存。"""
        with self._local_lock:
            self._local_id_cache.clear()
            self._local_content_cache.clear()

    def get_stats(self) -> dict:
        """获取去重统计信息。

        Returns:
            包含命中数和缓存大小的字典。
        """
        stats = self.stats.copy()
        with self._local_lock:
            stats["local_id_cache_size"] = len(self._local_id_cache)
            stats["local_content_cache_size"] = len(
                self._local_content_cache
            )
        return stats


class ProcessingGuardV2:
    """并发处理守卫，防止同一任务被重复处理。"""

    def __init__(self, dedup: LayeredDedup):
        """初始化守卫。

        Args:
            dedup: 去重管理器实例。
        """
        self.dedup = dedup
        self._local_processing = {}
        self._local_lock = threading.RLock()
        self._lock_ttl = 120

    def acquire(self, key: str) -> bool:
        """尝试获取处理权。

        Args:
            key: 任务唯一标识。

        Returns:
            True 表示成功获取，False 表示已被处理。
        """
        now = time.time()
        with self._local_lock:
            if (
                key in self._local_processing
                and now - self._local_processing[key] < self._lock_ttl
            ):
                return False
            self._local_processing[key] = now
        if self.dedup.config.lock_enabled:
            if not self.dedup.acquire_lock(f"proc:{key}"):
                with self._local_lock:
                    self._local_processing.pop(key, None)
                return False
        return True

    def release(self, key: str):
        """释放处理权。

        Args:
            key: 任务标识。
        """
        with self._local_lock:
            self._local_processing.pop(key, None)
        if self.dedup.config.lock_enabled:
            self.dedup.release_lock(f"proc:{key}")
            