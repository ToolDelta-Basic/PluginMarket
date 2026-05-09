# services/dedup/layered_dedup.py
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

# ---------- 优化的 TTL 缓存（基于堆的 O(log n) 淘汰）----------
class _SimpleTTLCache:
    def __init__(self, maxsize: int = 10000, ttl: int = 300):
        self._cache = {}                      # key -> (value, timestamp)
        self._heap = []                       # 最小堆 (timestamp, key)
        self.maxsize = maxsize
        self.ttl = ttl
        self.lock = threading.RLock()

    def __contains__(self, key):
        with self.lock:
            self._cleanup(time.time())
            return key in self._cache

    def __getitem__(self, key):
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
        with self.lock:
            now = time.time()
            self._cleanup(now)
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = (value, now)
            heapq.heappush(self._heap, (now, key))
            while len(self._cache) > self.maxsize:
                # 弹出堆中最旧的条目，并确保对应键确实仍在缓存中
                while self._heap:
                    t, k = heapq.heappop(self._heap)
                    if k in self._cache and self._cache[k][1] == t:
                        del self._cache[k]
                        break

    def pop(self, key, default=None):
        with self.lock:
            if key in self._cache:
                return self._cache.pop(key)[0]
            return default

    def clear(self):
        with self.lock:
            self._cache.clear()
            self._heap.clear()

    def __len__(self):
        with self.lock:
            self._cleanup(time.time())
            return len(self._cache)

    def _cleanup(self, now):
        while self._heap and now - self._heap[0][0] > self.ttl:
            t, k = heapq.heappop(self._heap)
            if k in self._cache and self._cache[k][1] == t:
                del self._cache[k]

# ---------- 多层去重管理器 ----------
class LayeredDedup:
    def __init__(self, config: DedupConfig):
        self.config = config
        if CACHETOOLS_AVAILABLE:
            self._local_id_cache = TTLCache(maxsize=config.local_max_size, ttl=config.local_id_ttl)
            self._local_content_cache = TTLCache(maxsize=config.local_max_size, ttl=config.local_content_ttl)
        else:
            self._local_id_cache = _SimpleTTLCache(maxsize=config.local_max_size, ttl=config.local_id_ttl)
            self._local_content_cache = _SimpleTTLCache(maxsize=config.local_max_size, ttl=config.local_content_ttl)

        self._local_lock = threading.RLock()
        self.redis = RedisClient(config) if config.redis_enabled else None
        self.bloom = BloomFilter(config, self.redis) if self.redis and config.bloom_enabled else None

        self.stats = {"local_hits": 0, "redis_hits": 0}

    def _make_fingerprint(self, content: str, user_id: int) -> str:
        normalized = content.strip()[:200]
        return hashlib.md5(f"{user_id}:{normalized}".encode()).hexdigest()

    def check_and_add_id(self, msg_id: str) -> bool:
        # 1. 本地缓存
        with self._local_lock:
            if msg_id in self._local_id_cache:
                self.stats["local_hits"] += 1
                return False
            self._local_id_cache[msg_id] = time.time()

        # 2. Redis 检查（如果可用）
        if self.redis:
            try:
                result = self.redis.execute("set", f"dedup:msgid:{msg_id}", "1", "nx", "ex", self.config.redis_id_ttl)
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
        fingerprint = self._make_fingerprint(content, user_id)
        # 1. 本地
        with self._local_lock:
            if fingerprint in self._local_content_cache:
                self.stats["local_hits"] += 1
                return False

        # 2. 布隆过滤器（可选）
        if self.bloom:
            if not self.bloom.check_and_add(fingerprint):
                with self._local_lock:
                    self._local_content_cache[fingerprint] = time.time()
                return True

        # 3. Redis
        if self.redis:
            try:
                result = self.redis.execute("set", f"dedup:content:{fingerprint}", "1", "nx", "ex", self.config.redis_content_ttl)
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

    def acquire_lock(self, resource: str, ttl: Optional[int] = None) -> bool:
        if not self.config.lock_enabled or not self.redis:
            return True
        ttl = ttl or self.config.lock_timeout
        lock_key = f"dedup:lock:{resource}"
        lock_value = f"{time.time()}:{threading.get_ident()}"
        for _ in range(self.config.lock_retry_times):
            result = self.redis.execute("set", lock_key, lock_value, "nx", "ex", ttl)
            if result:
                return True
            time.sleep(self.config.lock_retry_delay)
        return False

    def release_lock(self, resource: str):
        if self.config.lock_enabled and self.redis:
            self.redis.execute("del", f"dedup:lock:{resource}")

    def clear_local(self):
        with self._local_lock:
            self._local_id_cache.clear()
            self._local_content_cache.clear()

    def get_stats(self) -> dict:
        stats = self.stats.copy()
        with self._local_lock:
            stats["local_id_cache_size"] = len(self._local_id_cache)
            stats["local_content_cache_size"] = len(self._local_content_cache)
        return stats


# ---------- 并发处理守卫 ----------
class ProcessingGuardV2:
    def __init__(self, dedup: LayeredDedup):
        self.dedup = dedup
        self._local_processing = {}
        self._local_lock = threading.RLock()
        self._lock_ttl = 120

    def acquire(self, key: str) -> bool:
        now = time.time()
        with self._local_lock:
            if key in self._local_processing and now - self._local_processing[key] < self._lock_ttl:
                return False
            self._local_processing[key] = now
        if self.dedup.config.lock_enabled:
            if not self.dedup.acquire_lock(f"proc:{key}"):
                with self._local_lock:
                    self._local_processing.pop(key, None)
                return False
        return True

    def release(self, key: str):
        with self._local_lock:
            self._local_processing.pop(key, None)
        if self.dedup.config.lock_enabled:
            self.dedup.release_lock(f"proc:{key}")