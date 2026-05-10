# services/dedup/exceptions.py
"""去重模块自定义异常。"""

class DedupError(Exception):
    """去重模块基础异常。"""
    pass

class RedisUnavailableError(DedupError):
    """Redis 不可用异常。"""
    pass

class LockAcquireError(DedupError):
    """分布式锁获取失败异常。"""
    pass
    