import time
import hashlib
import threading
import heapq
from typing import Optional

from .config import DedupConfig
from .redis_client import RedisClient
from .bloom_filter import BloomFilter
from .exceptions import RedisUnavailableError


class _TTLCache:
    """基于堆的纯标准库 TTL 缓存（替代 cachetools.TTLCache）。

    设计：
    - 最小堆维护 (到期时间, key)，惰性过期清理
    - 线程安全（RLock）
    - 支持 __contains__ / __getitem__ / __setitem__ / pop / clear
    """

    def __init__(self, maxsize: int = 10000, ttl: int = 300):
        """初始化缓存。"""
        self._cache = {}
        self._heap = []
        self.maxsize = maxsize
        self.ttl = ttl
        self.lock = threading.RLock()

    def __contains__(self, key):
        """检查 key 是否存在且未过期。修复：显式检查时间戳。"""
        with self.lock:
            if key in self._cache:
                _, timestamp = self._cache[key]
                if time.time() - timestamp <= self.ttl:
                    return True
                # 过期，清理
                del self._cache[key]
            return False

    def __getitem__(self, key):
        """获取值，过期则抛出 KeyError。"""
        with self.lock:
            now = time.time()
            if key in self._cache:
                value, timestamp = self._cache[key]
                if now - timestamp <= self.ttl:
                    return value
                del self._cache[key]
            raise KeyError(key)

    def __setitem__(self, key, value):
        """设置值，超过最大容量时淘汰最旧条目，同时清理堆中过期/幽灵条目。"""
        with self.lock:
            now = time.time()
            # 删除旧条目的缓存和堆幽灵（修复内存泄漏）
            if key in self._cache:
                _, _ = self._cache[key]
                del self._cache[key]
                # 从堆中移除对应的旧条目（重建堆清理幽灵）
                self._heap = [(t, k) for t, k in self._heap if k != key]
                heapq.heapify(self._heap)
            self._cache[key] = (value, now)
            heapq.heappush(self._heap, (now, key))
            # 淘汰最旧有效条目
            while len(self._cache) > self.maxsize:
                if not self._heap:
                    break
                t, k = heapq.heappop(self._heap)
                if k in self._cache and self._cache[k][1] == t:
                    del self._cache[k]

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
            now = time.time()
            expired = [k for k, (_, ts) in self._cache.items() if now - ts > self.ttl]
            for k in expired:
                del self._cache[k]
            return len(self._cache)


class LayeredDedup:
    """多层去重管理器：本地缓存 + Redis + 布隆过滤器，支持降级。

    线程安全说明：
    - _TTLCache 内部已持有 threading.RLock，对其操作天然线程安全
    - 不再在 LayeredDedup 层额外加锁，避免 asyncio 事件循环中 threading 锁阻塞
      以及双重锁嵌套问题
    - self.stats 的更新使用简单的原子操作（int += 1 在 CPython 中是原子的）
    """

    def __init__(self, config: DedupConfig):
        """初始化去重引擎。"""
        self.config = config
        self._local_id_cache = _TTLCache(
            maxsize=config.local_max_size, ttl=config.local_id_ttl
        )
        self._local_content_cache = _TTLCache(
            maxsize=config.local_max_size, ttl=config.local_content_ttl
        )
        self._command_cache = _TTLCache(
            maxsize=config.local_max_size, ttl=1
        )

        # 不再使用 threading.RLock() — _TTLCache 内部已线程安全，
        # 避免在 asyncio 事件循环中持锁导致整个循环冻结
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
            try:
                result = self.redis.execute(
                    "set",
                    f"dedup:msgid:{msg_id}",
                    "1",
                    ex=self.config.redis_id_ttl,
                    nx=True,
                )
            except RedisUnavailableError:
                # Redis 命令执行异常，降级到本地缓存
                result = None
            if result is True:
                self._local_id_cache[msg_id] = time.time()
                return True
            if result is None:
                # 区分：Redis 不可用 (client is None) vs 键已存在 (SET NX 拒绝)
                if self.redis.client is None:
                    # Redis 连接失败，降级到本地
                    if self.config.fallback_to_local_on_redis_failure:
                        if msg_id in self._local_id_cache:
                            self.stats["local_hits"] += 1
                            return False
                        self._local_id_cache[msg_id] = time.time()
                        return True
                    return False
                # 键已存在（SET NX 拒绝），视为重复
                self.stats["redis_hits"] += 1
                return False
            self.stats["redis_hits"] += 1
            return False

        if msg_id in self._local_id_cache:
            self.stats["local_hits"] += 1
            return False
        self._local_id_cache[msg_id] = time.time()
        return True

    def check_and_add_content(self, content: str, user_id: int) -> bool:
        """基于内容指纹的去重检查。"""
        fingerprint = self._make_fingerprint(content, user_id)
        if fingerprint in self._local_content_cache:
            self.stats["local_hits"] += 1
            return False

        if self.bloom:
            is_new = self.bloom.check_and_add(fingerprint)
            if is_new:
                self._local_content_cache[fingerprint] = time.time()
                return True

        if self.redis:
            try:
                result = self.redis.execute(
                    "set",
                    f"dedup:content:{fingerprint}",
                    "1",
                    ex=self.config.redis_content_ttl,
                    nx=True,
                )
            except RedisUnavailableError:
                # Redis 命令执行异常，降级到本地缓存
                result = None
            if result is None:
                # 区分：Redis 不可用 vs 键已存在 (SET NX 拒绝)
                if self.redis.client is None:
                    # Redis 连接失败，降级到本地
                    if self.config.fallback_to_local_on_redis_failure:
                        if fingerprint in self._local_content_cache:
                            return False
                        self._local_content_cache[fingerprint] = time.time()
                        return True
                    return False
                # 键已存在，视为重复
                self.stats["redis_hits"] += 1
                return False
            if result is True:
                self._local_content_cache[fingerprint] = time.time()
                return True
            self.stats["redis_hits"] += 1
            return False

        self._local_content_cache[fingerprint] = time.time()
        return True

    def check_and_add_command(self, msg_id: str, short_ttl: int = 1) -> bool:
        """命令专用去重：短 TTL (5s)，只拦截真正的重复推送（OneBot 多 bot 同时处理）。

        与普通消息去重分离，使用独立的 _command_cache（_TTLCache，TTL=1s）。
        翻页导航字符 (+/-/q) 通过 event_bridge 直接跳过，不调用此方法。

        Args:
            msg_id: 逻辑消息 ID（格式: cmd_{group_id}_{user_id}_{text[:30]}）
            short_ttl: TTL 秒数（默认 1 秒）

        Returns:
            True 如果消息未见过（放行），False 如果重复（拦截）
        """
        # 更新 TTL（支持动态调整，虽然通常使用默认值）
        if self._command_cache.ttl != short_ttl:
            self._command_cache.ttl = short_ttl

        if msg_id in self._command_cache:
            return False
        self._command_cache[msg_id] = time.time()
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
                "set", lock_key, lock_value, ex=ttl, nx=True
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
        self._local_id_cache.clear()
        self._local_content_cache.clear()

    def get_stats(self) -> dict:
        """获取去重统计信息。"""
        stats = self.stats.copy()
        stats["local_id_cache_size"] = len(self._local_id_cache)
        stats["local_content_cache_size"] = len(
            self._local_content_cache
        )
        return stats


class ProcessingGuardV2:
    """并发处理守卫，防止同一任务被重复处理。

    线程安全说明：
    - _local_processing 使用 threading.RLock 保护，但锁仅用于字典操作，
      不包含 redis 网络 I/O 的等待循环，避免 asyncio 事件循环阻塞
    """

    def __init__(self, dedup: LayeredDedup):
        """初始化守卫。"""
        self.dedup = dedup
        self._local_processing = {}
        self._local_lock = threading.RLock()
        self._lock_ttl = 120

    def acquire(self, key: str) -> bool:
        """尝试获取处理权，自动清除过期项。

        锁内仅做字典的 O(1) 操作，redis 分布式锁获取在锁外进行，
        避免 asyncio 事件循环中长时间持锁。
        """
        now = time.time()
        # 局部快照：只在锁内获取必要信息
        with self._local_lock:
            if key in self._local_processing:
                entry_time = self._local_processing[key]
                if now - entry_time < self._lock_ttl:
                    return False
                # 过期，删除
                del self._local_processing[key]
            # 标记为处理中
            self._local_processing[key] = now
            acquired_local = True

        # 锁外执行分布式锁获取（可能涉及网络 I/O）
        if self.dedup.config.lock_enabled and not self.dedup.acquire_lock(
            f"proc:{key}"
        ):
            with self._local_lock:
                self._local_processing.pop(key, None)
            return False
        return acquired_local

    def release(self, key: str):
        """释放处理权。锁内仅做字典删除，redis 释放锁在锁外进行。"""
        with self._local_lock:
            self._local_processing.pop(key, None)
        if self.dedup.config.lock_enabled:
            self.dedup.release_lock(f"proc:{key}")
