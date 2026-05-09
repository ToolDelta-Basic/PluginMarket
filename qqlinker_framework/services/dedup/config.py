# services/dedup/config.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class DedupConfig:
    # 本地缓存
    local_id_ttl: int = 300
    local_content_ttl: int = 120
    local_max_size: int = 10000

    # Redis
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    redis_timeout: float = 2.0
    redis_id_ttl: int = 300
    redis_content_ttl: int = 120

    # 布隆过滤器 (RedisBloom)
    bloom_enabled: bool = False
    bloom_error_rate: float = 0.001
    bloom_capacity: int = 1000000

    # 分布式锁
    lock_enabled: bool = False
    lock_timeout: int = 10
    lock_retry_times: int = 3
    lock_retry_delay: float = 0.1

    # 降级策略
    fallback_to_local_on_redis_failure: bool = True