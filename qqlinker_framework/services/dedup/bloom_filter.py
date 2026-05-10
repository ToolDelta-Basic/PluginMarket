"""基于 RedisBloom 的布隆过滤器封装。"""
import logging
import time
from .redis_client import RedisClient
from .config import DedupConfig

logger = logging.getLogger(__name__)


class BloomFilter:
    """布隆过滤器，按天分 key，利用 RedisBloom 模块。"""

    def __init__(
        self,
        config: DedupConfig,
        redis_client: RedisClient,
        prefix: str = "dedup:bf",
    ):
        """初始化布隆过滤器。

        Args:
            config: 去重配置。
            redis_client: Redis 客户端实例。
            prefix: Redis key 前缀。
        """
        self.config = config
        self.redis = redis_client
        self.prefix = prefix

    def _get_key(self) -> str:
        """生成按日滚动的 Redis key。

        Returns:
            形如 "dedup:bf:20250101" 的 key。
        """
        return f"{self.prefix}:{time.strftime('%Y%m%d')}"

    def check_and_add(self, item: str) -> bool:
        """检查元素是否存在，若不存在则添加。

        Args:
            item: 待检查的字符串。

        Returns:
            True 表示新元素（未命中），False 表示可能已存在。
        """
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
            