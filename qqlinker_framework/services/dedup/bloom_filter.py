import logging
_log = logging.getLogger(__name__)
import time
from .redis_client import RedisClient
from .config import DedupConfig

logger = logging.getLogger(__name__)

# ── 安全限制 ──
# 布隆过滤器设计参数（当无法从 Redis 查询实际参数时使用）
_DEFAULT_CAPACITY = 100_000_000  # 默认容量 1 亿
_DEFAULT_ERROR_RATE = 0.001      # 默认假阳性率 0.1%
_MAX_ELEMENTS_PER_KEY = 500_000_000  # 每个 key 最大元素数（5 亿）
# 假阳性率警告阈值
_FP_WARN_THRESHOLD = 0.01  # 1%
_FP_CRITICAL_THRESHOLD = 0.05  # 5%


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
        self._estimated_count: int = 0
        self._last_fp_check: float = 0.0

    def _get_key(self) -> str:
        """生成按日滚动的 Redis key。

        Returns:
            形如 "dedup:bf:20250101" 的 key。
        """
        return f"{self.prefix}:{time.strftime('%Y%m%d')}"

    def _check_false_positive_rate(self) -> None:
        """检查并记录布隆过滤器假阳性率。

        如果 RedisBloom 可用，查询实际参数；否则使用估计值。
        当假阳性率超过警告阈值时记录日志。
        """
        now = time.time()
        # 每分钟最多检查一次
        if now - self._last_fp_check < 60:
            return
        self._last_fp_check = now

        try:
            key = self._get_key()
            # 尝试从 Redis 获取布隆过滤器信息
            info = self.redis.client.execute_command("BF.INFO", key)
            if info and isinstance(info, list):
                info_dict = {}
                for i in range(0, len(info), 2):
                    if i + 1 < len(info):
                        info_dict[info[i].decode() if isinstance(info[i], bytes) else info[i]] = info[i + 1]

                capacity = info_dict.get("Capacity", _DEFAULT_CAPACITY)
                size = info_dict.get("Number of items inserted", 0)
                # _num_filters 保留供将来使用（变种过滤器数统计）
                _ = info_dict.get("Number of filters", 1)

                # 估计假阳性率：p ≈ (1 - e^(-k*n/m))^k
                # 简化：使用负载因子估计
                if capacity > 0:
                    load_factor = size / capacity
                    # 对标准布隆过滤器，假阳性率随负载指数增长
                    if load_factor > 0.5:
                        logger.warning(
                            "布隆过滤器负载过高: %d/%d (%.1f%%), "
                            "假阳性率可能显著增加",
                            size, capacity, load_factor * 100,
                        )
                    if load_factor > 0.9:
                        logger.critical(
                            "布隆过滤器接近满载: %d/%d (%.1f%%), 建议增加容量",
                            size, capacity, load_factor * 100,
                        )
        except Exception as e:
            # RedisBloom 可能不可用或命令不支持，静默降级
            _log.debug("bloom_filter.bloom_filter: %s", e)

    def _check_element_limit(self) -> None:
        """检查布隆过滤器元素数是否超过最大限制。

        超限时记录严重警告，防止过滤器退化。
        """
        self._estimated_count += 1
        if self._estimated_count > _MAX_ELEMENTS_PER_KEY:
            logger.critical(
                "布隆过滤器元素数超过上限 (%d)，过滤器已退化，"
                "所有查询可能返回 '已存在'",
                _MAX_ELEMENTS_PER_KEY,
            )
            # 重置计数器以继续工作但记录警告
            self._estimated_count = 0

    def check_and_add(self, item: str) -> bool:
        """检查元素是否存在，若不存在则添加。

        Args:
            item: 待检查的字符串。

        Returns:
            True 表示新元素（未命中），False 表示可能已存在。
        """
        if not self.config.bloom_enabled or not self.redis.client:
            return True

        # ── 最大元素数检查 ──
        self._check_element_limit()

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
            # ── 定期假阳性率检查 ──
            self._check_false_positive_rate()
            return result == 1
        except Exception as e:
            logger.error("布隆过滤器检查失败，降级为放行: %s", e)
            return True
