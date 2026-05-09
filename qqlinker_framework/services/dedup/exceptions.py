# services/dedup/exceptions.py
class DedupError(Exception):
    pass

class RedisUnavailableError(DedupError):
    pass

class LockAcquireError(DedupError):
    pass