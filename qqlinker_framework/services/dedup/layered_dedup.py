"""多层去重引擎：本地TTL缓存 + Redis + 布隆过滤器。"""
import time
import hashlib
import threading
from typing import Optional

try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    CACHETOOLS_AVAILABLE = False

from .config import DedupConfig
from .redis_client import RedisClient
from .bloom_filter import BloomFilter


class LayeredDedup:
    """多层去重管理器：本地缓存 + Redis + 布隆过滤器，支持降级。"""

    def __init__(self, config: DedupConfig):
        """初始化去重引擎。"""
        if not CACHETOOLS_AVAILABLE:
            raise ImportError(
                "cachetools 未安装，请执行 'pip install cachetools' 或 'qqdeps install'"
            )
        self.config = config
        self._local_id_cache = TTLCache(
            maxsize=config.local_max_size, ttl=config.local_id_ttl
        )
        self._local_content_cache = TTLCache(
            maxsize=config.local_max_size, ttl=config.local_content_ttl
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

    @staticmethod
    def _make_fingerprint(content: str, user_id: int) -> str:
        """生成内容指纹（SHA-256）。"""
        normalized = content.strip()[:200]
        raw = f"{user_id}:{normalized}".encode()
        return hashlib.sha256(raw).hexdigest()

    def check_and_add_id(self, msg_id: str) -> bool:
        """基于消息 ID 的去重检查。修复竞态：先 Redis 后本地，正确处理降级。"""
        if self.redis:
            result = self.redis.execute(
                "set",
                f"dedup:msgid:{msg_id}",
                "1",
                "nx",
                "ex",
                self.config.redis_id_ttl,
            )
            if result is True:
                with self._local_lock:
                    self._local_id_cache[msg_id] = time.time()
                return True
            if result is None:
                if self.config.fallback_to_local_on_redis_failure:
                    with self._local_lock:
                        if msg_id in self._local_id_cache:
                            self.stats["local_hits"] += 1
                            return False
                        self._local_id_cache[msg_id] = time.time()
                    return True
                return False
            self.stats["redis_hits"] += 1
            return False

        with self._local_lock:
            if msg_id in self._local_id_cache:
                self.stats["local_hits"] += 1
                return False
            self._local_id_cache[msg_id] = time.time()
        return True

    def check_and_add_content(self, content: str, user_id: int) -> bool:
        """基于内容指纹的去重检查。"""
        fingerprint = self._make_fingerprint(content, user_id)
        with self._local_lock:
            if fingerprint in self._local_content_cache:
                self.stats["local_hits"] += 1
                return False

        if self.bloom:
            is_new = self.bloom.check_and_add(fingerprint)
            if is_new:
                with self._local_lock:
                    self._local_content_cache[fingerprint] = time.time()
                return True

        if self.redis:
            result = self.redis.execute(
                "set",
                f"dedup:content:{fingerprint}",
                "1",
                "nx",
                "ex",
                self.config.redis_content_ttl,
            )
            if result is None:
                if self.config.fallback_to_local_on_redis_failure:
                    with self._local_lock:
                        if fingerprint in self._local_content_cache:
                            return False
                        self._local_content_cache[fingerprint] = time.time()
                    return True
                return False
            if result is True:
                with self._local_lock:
                    self._local_content_cache[fingerprint] = time.time()
                return True
            self.stats["redis_hits"] += 1
            return False

        with self._local_lock:
            self._local_content_cache[fingerprint] = time.time()
        return True

    def acquire_lock(
        self, resource: str, ttl: Optional[int] = None
    ) -> bool:
        """获取分布式锁（如果启用）。"""
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
        """释放分布式锁。"""
        if self.config.lock_enabled and self.redis:
            self.redis.execute("del", f"dedup:lock:{resource}")

    def clear_local(self):
        """清空所有本地缓存。"""
        with self._local_lock:
            self._local_id_cache.clear()
            self._local_content_cache.clear()

    def get_stats(self) -> dict:
        """获取去重统计信息。"""
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
        """初始化守卫。"""
        self.dedup = dedup
        self._local_processing = {}
        self._local_lock = threading.RLock()
        self._lock_ttl = 120

    def acquire(self, key: str) -> bool:
        """尝试获取处理权，自动清除过期项。"""
        now = time.time()
        with self._local_lock:
            if key in self._local_processing:
                if now - self._local_processing[key] < self._lock_ttl:
                    return False
                # 过期，删除
                del self._local_processing[key]
            self._local_processing[key] = now
        if self.dedup.config.lock_enabled and not self.dedup.acquire_lock(
            f"proc:{key}"
        ):
            with self._local_lock:
                self._local_processing.pop(key, None)
            return False
        return True

    def release(self, key: str):
        """释放处理权。"""
        with self._local_lock:
            self._local_processing.pop(key, None)
        if self.dedup.config.lock_enabled:
            self.dedup.release_lock(f"proc:{key}")
