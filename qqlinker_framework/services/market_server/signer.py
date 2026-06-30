import hashlib
import hmac
import time
from typing import Dict, Optional

# ── 签名时效性 ──
_SIGNATURE_MAX_AGE = 300  # 签名最大有效期（秒）= 5 分钟

# ── Nonce 防重放缓存（简单内存缓存）──
# key: nonce, value: 过期时间戳
_nonce_cache: Dict[str, float] = {}
_NONCE_CACHE_MAX_SIZE = 10000


def sign_module(name: str, version: str, secret: str,
                timestamp: Optional[float] = None) -> str:
    """为模块生成 HMAC-SHA256 签名（含时间戳防重放）。

    Args:
        name: 模块名。
        version: 版本号字符串。
        secret: 签名密钥。
        timestamp: Unix 时间戳（默认当前时间）。

    Returns:
        HMAC-SHA256 十六进制签名。
    """
    ts = int(timestamp or time.time())
    msg = f"{name}:{version}:{ts}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]
    return f"{sig}:{ts}"


def verify_signature(name: str, version: str, signature: str,
                     secret: str, nonce: Optional[str] = None) -> bool:
    """验证模块签名（恒定时间比较 + 时效性检查 + nonce 防重放）。

    Args:
        name: 模块名。
        version: 版本号字符串。
        signature: 签名串，格式为 "sig_hex:timestamp"。
        secret: 签名密钥。
        nonce: 可选的防重放 nonce。

    Returns:
        True 如果签名有效且未过期、未重放。
    """
    if not signature or not secret:
        return False

    # 解析签名和时间戳
    parts = signature.rsplit(":", 1)
    if len(parts) != 2:
        # 旧格式（无时间戳）— 使用当前签名重新验证
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{name}:{version}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()[:16]
        return hmac.compare_digest(expected, signature)

    sig_hex, ts_str = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False

    # 时效性检查：必须在 ±_SIGNATURE_MAX_AGE 秒内
    now = time.time()
    if abs(now - ts) > _SIGNATURE_MAX_AGE:
        return False

    # 重新计算签名
    msg = f"{name}:{version}:{ts}".encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"), msg, hashlib.sha256
    ).hexdigest()[:16]

    if not hmac.compare_digest(expected, sig_hex):
        return False

    # Nonce 防重放
    if nonce:
        if _check_and_record_nonce(nonce):
            return False  # 已使用过的 nonce

    return True


def _check_and_record_nonce(nonce: str) -> bool:
    """检查 nonce 是否已被使用，若未使用则记录。

    Args:
        nonce: 一次性随机值。

    Returns:
        True 如果 nonce 已存在（重放攻击）。
    """
    now = time.time()
    # 清理过期 nonce
    expired = [k for k, v in _nonce_cache.items() if v < now]
    for k in expired:
        del _nonce_cache[k]

    # 如果缓存太大，清理最旧的一半
    if len(_nonce_cache) > _NONCE_CACHE_MAX_SIZE:
        sorted_items = sorted(_nonce_cache.items(), key=lambda x: x[1])
        for k, _ in sorted_items[:len(sorted_items) // 2]:
            del _nonce_cache[k]

    if nonce in _nonce_cache:
        return True

    # 记录 nonce，过期时间与签名时效性一致
    _nonce_cache[nonce] = now + _SIGNATURE_MAX_AGE
    return False
