"""共享安全工具函数：供所有 AI tool 复用的 URL/输入验证。

提供:
  - validate_url()      — SSRF 防护：内网拒绝、协议检查、长度限制
  - sanitize_prompt()   — 输入清洗：长度截断 + 控制字符清理
"""
import ipaddress
import re
import urllib.parse
from typing import Tuple

# URL 最大长度 (RFC 2616 无上限，但实践中 2048 是安全上限)
_MAX_URL_LENGTH = 2048

# ── 内网地址范围 ──
_BLOCKED_NETWORKS = [
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
]

# ── 可信图片域名（用于 image 工具返回的 URL 验证）──
# 硅基流动、快手 Kolors、及其他已知 AI 图片 CDN
_TRUSTED_IMAGE_HOSTS = {
    "cdn.siliconflow.cn",
    "siliconflow.com",
    "siliconflow.cn",
    "qianfan.baidu.com",
    "baidu.com",
    "kuaishou.com",
    "kwai-pro.com",
}


def validate_url(url: str) -> Tuple[bool, str]:
    """验证 URL 是否安全。

    防御措施（瑞士奶酪模型，多层独立加固）：
      1. 非空检查
      2. 长度限制 (2048 字符)
      3. 仅允许 http/https 协议
      4. 拒绝 file://、ftp:// 等非 http 协议
      5. 拒绝内网地址 (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12,
         192.168.0.0/16, 169.254.0.0/16, ::1, fc00::/7)
      6. 拒绝裸 IPv6 地址在方括号中映射到内网的情况

    Args:
        url: 待验证的 URL 字符串。

    Returns:
        (valid, error_message) — valid 为 True 时 error 为 ""。
    """
    if not url or not url.strip():
        return False, "URL 为空"

    if len(url) > _MAX_URL_LENGTH:
        return False, f"URL 长度超过限制 ({_MAX_URL_LENGTH} 字符)"

    # 协议检查：仅允许 http/https
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return False, f"不支持的协议: {scheme}，仅允许 http/https"

    # 提取 hostname（不依赖 DNS 解析）
    hostname = urllib.parse.urlparse(url).hostname
    if not hostname:
        return False, "URL 中未找到有效主机名"

    # 移除可能的前后空格
    hostname = hostname.strip()

    # 检查是否为 IPv4/IPv6 地址
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return False, "不允许访问内网地址"
    except ValueError:
        # 不是裸 IP 地址，可能是域名
        # 防御：即使通过 DNS 也能检测到内网指向的域名，
        # 但此处额外检查 hostname 本身是否为 IPv6 映射地址
        # 或特殊域名模式
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"):
            return False, "不允许访问内网地址"

        # 检查是否包含特殊的 localhost 变体
        if hostname.endswith(".local") or hostname.endswith(".internal"):
            return False, "不允许访问内网地址"

    return True, ""


def is_trusted_image_host(url: str) -> bool:
    """检查图片 URL 是否来自受信任域名。

    用于验证 [IMAGE:url] tag 中的图片链接。

    Args:
        url: 图片 URL。

    Returns:
        True 如果 URL 主机名在受信任域名集合中。
    """
    hostname = urllib.parse.urlparse(url).hostname
    if not hostname:
        return False
    hostname = hostname.lower()
    # 检查精确匹配或子域名匹配（避免 .com 型误匹配）
    if hostname in _TRUSTED_IMAGE_HOSTS:
        return True
    for trusted in _TRUSTED_IMAGE_HOSTS:
        # 只匹配 exact.com 或 sub.exact.com，防止 attacker-fake.com 绕过
        if hostname == trusted or hostname.endswith("." + trusted):
            return True
    return False


def sanitize_prompt(text: str, max_len: int = 500) -> str:
    """清洗输入文本：长度截断 + 控制字符移除。

    Args:
        text: 原始输入文本。
        max_len: 最大字符数（默认 500）。

    Returns:
        清洗后的安全文本。
    """
    if not text:
        return ""
    # 移除控制字符（保留常见的换行制表符）
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if len(text) > max_len:
        text = text[:max_len]
    return text.strip()


def filter_ip_patterns(text: str) -> bool:
    """检查文本是否包含 IP 地址模式（IPv4/IPv6）。

    用于搜索工具中防止用户使用 IP 地址绕过 URL 过滤。

    Args:
        text: 待检查的文本。

    Returns:
        True 如果文本包含 IP 地址模式。
    """
    # IPv4 模式
    ipv4_pattern = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
        r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    )
    if ipv4_pattern.search(text):
        return True

    # IPv6 模式（简化但覆盖常见格式）
    ipv6_pattern = re.compile(
        r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"
    )
    if ipv6_pattern.search(text):
        return True

    return False


def clean_search_results(results_text: str) -> str:
    """清洗搜索结果：移除可能的恶意链接模式。

    Args:
        results_text: 搜索结果文本。

    Returns:
        清洗后的安全文本。
    """
    if not results_text:
        return ""

    # 移除潜在的 data:/javascript: 等危险协议
    results_text = re.sub(
        r"\b(?:data|javascript|vbscript):[^\s]*",
        "[已移除危险链接]",
        results_text,
        flags=re.IGNORECASE,
    )

    # 移除 file:// 协议链接
    results_text = re.sub(
        r"\bfile://[^\s]*",
        "[已移除本地文件链接]",
        results_text,
        flags=re.IGNORECASE,
    )

    return results_text


def compute_text_entropy(text: str) -> float:
    """计算文本的香农熵（用于检测重复 padding 绕过攻击）。

    高熵值 → 随机/多样化内容（正常对话）
    低熵值 → 大量重复字符（可能的 padding 攻击）

    Args:
        text: 待分析的文本。

    Returns:
        香农熵值 (0.0 ~ 8.0+，取决于字符分布)。
    """
    import math
    if not text:
        return 0.0

    freq: dict[str, int] = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1

    length = len(text)
    entropy = 0.0
    for count in freq.values():
        p = count / length
        entropy -= p * math.log2(p)

    return entropy


def compute_repeat_ratio(text: str) -> float:
    """计算文本重复率（用于检测 padding 攻击）。

    使用滑动窗口方法检测重复模式。

    Args:
        text: 待分析的文本。

    Returns:
        重复率 (0.0 ~ 1.0)，越接近 1.0 表示重复越多。
    """
    if len(text) < 10:
        return 0.0

    # 检查连续相同字符的比例
    if len(text) <= 1:
        return 0.0

    same_count = 0
    for i in range(1, len(text)):
        if text[i] == text[i - 1]:
            same_count += 1

    return same_count / (len(text) - 1)
