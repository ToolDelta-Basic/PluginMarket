# services/dedup/exceptions.py


class DedupError(Exception):
    """去重模块基础异常。"""


class RedisUnavailableError(DedupError):
    """Redis 不可用异常。"""


class LockAcquireError(DedupError):
    """分布式锁获取失败异常。"""
