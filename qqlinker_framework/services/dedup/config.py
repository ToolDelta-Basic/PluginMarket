# services/dedup/config.py
"""去重配置数据类。"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class DedupConfig:
    """去重引擎的完整配置。

    Attributes:
        local_id_ttl: 本地消息ID缓存TTL (秒)。
        local_content_ttl: 本地内容指纹缓存TTL (秒)。
        local_max_size: 本地缓存最大条目数。
        redis_enabled: 是否启用 Redis。
        redis_url: Redis 连接 URL。
        redis_password: Redis 密码。
        redis_timeout: Redis 超时秒数。
        redis_id_ttl: Redis 消息ID TTL。
        redis_content_ttl: Redis 内容指纹 TTL。
        bloom_enabled: 是否启用布隆过滤器。
        bloom_error_rate: 布隆过滤器允许的错误率。
        bloom_capacity: 布隆过滤器预计容量。
        lock_enabled: 是否启用分布式锁。
        lock_timeout: 锁超时秒数。
        lock_retry_times: 锁获取重试次数。
        lock_retry_delay: 重试间隔秒数。
        fallback_to_local_on_redis_failure: Redis 失败时是否降级到本地。
    """
    local_id_ttl: int = 300
    local_content_ttl: int = 120
    local_max_size: int = 10000

    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_timeout: float = 2.0
    redis_id_ttl: int = 300
    redis_content_ttl: int = 120

    bloom_enabled: bool = False
    bloom_error_rate: float = 0.001
    bloom_capacity: int = 1000000

    lock_enabled: bool = False
    lock_timeout: int = 10
    lock_retry_times: int = 3
    lock_retry_delay: float = 0.1

    fallback_to_local_on_redis_failure: bool = True
