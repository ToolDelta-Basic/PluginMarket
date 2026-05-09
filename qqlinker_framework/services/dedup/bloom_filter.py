# services/dedup/bloom_filter.py
import logging
import time
from .redis_client import RedisClient
from .config import DedupConfig

logger = logging.getLogger(__name__)

class BloomFilter:
    def __init__(self, config: DedupConfig, redis_client: RedisClient, prefix: str = "dedup:bf"):
        self.config = config
        self.redis = redis_client
        self.prefix = prefix

    def _get_key(self) -> str:
        return f"{self.prefix}:{time.strftime('%Y%m%d')}"

    def check_and_add(self, item: str) -> bool:
        if not self.config.bloom_enabled or not self.redis.client:
            return True
        key = self._get_key()
        script = """
        local exists = redis.call('bf.exists', KEYS[1], ARGV[1])
        if exists == 0 then
            redis.call('bf.add', KEYS[1], ARGV[1])
            return 1
        else
            return 0
        end
        """
        try:
            result = self.redis.client.eval(script, 1, key, item)
            return result == 1
        except Exception as e:
            logger.error("布隆过滤器检查失败，降级为放行: %s", e)
            return True