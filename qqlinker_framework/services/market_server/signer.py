"""模块市场签名工具 — HMAC-SHA256 签名/验证。"""
import hashlib
import hmac


def sign_module(name: str, version: str, secret: str) -> str:
    """为模块生成 HMAC-SHA256 签名。"""
    msg = f"{name}:{version}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]


def verify_signature(name: str, version: str, signature: str, secret: str) -> bool:
    """验证模块签名（恒定时间比较）。"""
    return hmac.compare_digest(sign_module(name, version, secret), signature)
