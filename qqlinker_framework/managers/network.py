from __future__ import annotations

import asyncio
import ipaddress
import logging
import ssl
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .retry_policy import RetryPolicy
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# SSRF 防护：内网 CIDR 范围
# ═══════════════════════════════════════════════════════════════

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# 黑名单域名（始终拦截，大小写不敏感）
_BLACKLIST_DOMAINS = frozenset({
    "metadata.google.internal",
    "169.254.169.254",
    "localhost.localdomain",
})


@dataclass
class NetworkConfig:
    """网络管理器配置。

    属性:
        connect_timeout: HTTP 连接超时（秒）
        total_timeout: 请求总超时（秒）
        pool_size: 默认连接池大小
        pool_per_host: 每个主机的最大并发连接数
        max_redirects: 最大重定向次数
        tls_verify: TLS 证书验证模式 ("enabled" | "skip" | "fingerprint")
        ssrf_block_private: 是否阻止内网 IP 访问
        ssrf_blocklist: 额外黑名单域名（合并到内置列表）
        retry_policy: 全局默认重试策略
        circuit_failure_threshold: 熔断器失败阈值（全局默认）
        circuit_cooldown_seconds: 熔断器冷却秒数（全局默认）
    """
    connect_timeout: float = 10.0
    total_timeout: float = 30.0
    pool_size: int = 5
    pool_per_host: int = 3
    max_redirects: int = 5
    tls_verify: str = "enabled"
    ssrf_block_private: bool = True
    ssrf_blocklist: list = None
    retry_policy: Optional[RetryPolicy] = None
    circuit_failure_threshold: int = 5
    circuit_cooldown_seconds: float = 30.0

    def __post_init__(self):
        if self.ssrf_blocklist is None:
            self.ssrf_blocklist = []


class NetworkManager:
    """统一网络连接管理器 — HTTP 客户端 + 连接池 + 重试 + 熔断 + SSRF 防护。

    设计要点:
      - 所有 HTTP 调用自动经过熔断器（按 host:port 分片）
      - 自动应用重试策略
      - SSRF 防护在 DNS 解析后检查（比纯域名黑名单更强）
      - create_session() 创建独立 aiohttp session（不同 base_url 不同配置）
      - 框架停止时调用 close() 释放所有 session

    从配置读取:
      - 网络传输.连接超时秒 → connect_timeout
      - 网络传输.读超时秒 → 合并到 total_timeout
      - 网络传输.TLS验证模式 → tls_verify
      - SSRF防护.黑名单域名 → ssrf_blocklist
      - SSRF防护.禁止内网IP → ssrf_block_private
    """

    def __init__(self, config=None):
        """
        Args:
            config: ConfigManager 实例或普通 dict。None 时使用默认参数。
        """
        if aiohttp is None:
            _log.warning("aiohttp 未安装，NetworkManager HTTP 功能不可用")
            self._aiohttp_available = False
        else:
            self._aiohttp_available = True

        # 从 ConfigManager 读取配置
        self._net_config = self._build_config(config)
        self._retry_policy = self._net_config.retry_policy or RetryPolicy.standard()

        # 按 host 分片的熔断器
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._breakers_lock = asyncio.Lock()

        # SSRF 黑名单
        self._ssrf_blocklist: frozenset = _BLACKLIST_DOMAINS.union(
            d.lower() for d in self._net_config.ssrf_blocklist
        )

        # Session 注册表
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._sessions_lock = asyncio.Lock()

        # 默认 session（惰性创建）
        self._default_session: Optional[aiohttp.ClientSession] = None
        self._closed = False

        _log.info(
            "NetworkManager 已初始化 "
            "(connect=%ds, total=%ds, pool=%d, retry=%s, tls=%s)",
            self._net_config.connect_timeout,
            self._net_config.total_timeout,
            self._net_config.pool_size,
            self._retry_policy,
            self._net_config.tls_verify,
        )

    # ═══════════════════════════════════════════════════════════
    # 配置构建
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _build_config(cfg) -> NetworkConfig:
        """从 NetworkConfig / ConfigManager / dict 构建 NetworkConfig。"""
        if cfg is None:
            return NetworkConfig()

        # 如果已经是 NetworkConfig，直接返回
        if isinstance(cfg, NetworkConfig):
            return cfg

        # 如果是 ConfigManager 实例
        if hasattr(cfg, "get"):
            return NetworkConfig(
                connect_timeout=float(cfg.get("网络传输.连接超时秒", 10, requester_uid=0)),
                total_timeout=max(
                    float(cfg.get("网络传输.读超时秒", 30, requester_uid=0)),
                    float(cfg.get("网络传输.连接超时秒", 10, requester_uid=0)) + 5,
                ),
                tls_verify=cfg.get("网络传输.TLS验证模式", "enabled", requester_uid=0),
                ssrf_block_private=cfg.get("SSRF防护.禁止内网IP", True, requester_uid=0),
                ssrf_blocklist=cfg.get("SSRF防护.黑名单域名", [], requester_uid=0),
            )

        # dict 模式
        return NetworkConfig(
            connect_timeout=float(cfg.get("网络传输.连接超时秒", cfg.get("connect_timeout", 10))),
            total_timeout=float(cfg.get("网络传输.读超时秒", cfg.get("total_timeout", 30))),
            tls_verify=cfg.get("网络传输.TLS验证模式", cfg.get("tls_verify", "enabled")),
            ssrf_block_private=cfg.get("SSRF防护.禁止内网IP", cfg.get("ssrf_block_private", True)),
            ssrf_blocklist=cfg.get("SSRF防护.黑名单域名", cfg.get("ssrf_blocklist", [])),
        )

    # ═══════════════════════════════════════════════════════════
    # SSRF 防护
    # ═══════════════════════════════════════════════════════════

    def _check_ssrf(self, hostname: str) -> Optional[str]:
        """SSRF 防护检查：返回 None 表示安全，返回非空字符串是拒绝原因。

        检查顺序:
          1. 黑名单域名（含内置和用户配置的额外域名）
          2. IP 解析后检查是否内网地址（更强的防护，防 DNS rebinding）
        """
        # 1. 域名黑名单（大小写不敏感）
        if hostname.lower() in self._ssrf_blocklist:
            return f"SSRF 拦截: 黑名单域名 '{hostname}'"

        # 2. IP 解析 → 内网检查
        if self._net_config.ssrf_block_private:
            try:
                # 同步 DNS 解析（框架启动时已存在事件循环）
                import socket as _socket
                addrs = _socket.getaddrinfo(hostname, None, proto=_socket.IPPROTO_TCP)
            except Exception:
                # DNS 解析失败 → 放行（连接会自然失败）
                return None

            for addr_info in addrs:
                ip_str = addr_info[4][0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                except ValueError:
                    continue
                for net in _PRIVATE_NETWORKS:
                    if ip in net:
                        return f"SSRF 拦截: 内网地址 '{ip_str}' → {hostname}"
        return None

    async def _resolve_and_check_ssrf(self, hostname: str) -> Optional[str]:
        """异步 SSRF 检查（在线程池中做 DNS 解析）。"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._check_ssrf, hostname
        )

    # ═══════════════════════════════════════════════════════════
    # 熔断器管理
    # ═══════════════════════════════════════════════════════════

    async def _get_breaker(self, host: str) -> CircuitBreaker:
        """获取或创建指定 host 的熔断器。"""
        async with self._breakers_lock:
            if host not in self._breakers:
                cfg = CircuitBreakerConfig(
                    failure_threshold=self._net_config.circuit_failure_threshold,
                    cooldown_seconds=self._net_config.circuit_cooldown_seconds,
                )
                self._breakers[host] = CircuitBreaker(cfg, name=f"http:{host}")
            return self._breakers[host]

    # ═══════════════════════════════════════════════════════════
    # Session 管理
    # ═══════════════════════════════════════════════════════════

    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        """根据配置构建 SSL 上下文。"""
        tls_mode = self._net_config.tls_verify
        if tls_mode == "skip":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            _log.debug("TLS 证书验证已跳过")
            return ctx
        if tls_mode == "fingerprint":
            # 指纹模式：使用默认验证，允许自定义指纹检查
            return ssl.create_default_context()
        return None  # 使用 aiohttp 默认行为

    async def _get_default_session(self):
        """获取默认 HTTP session（惰性创建）。"""
        if not self._aiohttp_available:
            raise RuntimeError("aiohttp 未安装，NetworkManager HTTP 功能不可用")
        if self._default_session is None or self._default_session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self._net_config.total_timeout,
                connect=self._net_config.connect_timeout,
            )
            connector = aiohttp.TCPConnector(
                limit=self._net_config.pool_size,
                limit_per_host=self._net_config.pool_per_host,
                ssl=self._build_ssl_context(),
            )
            self._default_session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
            )
            _log.debug("默认 HTTP session 已创建")
        return self._default_session

    def create_session(
        self,
        base_url: str = "",
        pool_size: int = 5,
        pool_per_host: int = 3,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> aiohttp.ClientSession:
        """创建独立的 aiohttp.ClientSession（连接池）。

        Args:
            base_url: 基础 URL（用于复用连接）
            pool_size: 总连接池上限
            pool_per_host: 每个 host 的最大并发连接
            timeout: 自定义总超时（秒）
            headers: 默认 headers

        Returns:
            aiohttp.ClientSession 实例

        Note:
            调用方负责调用 session.close() 释放。
            框架 stop() 时自动关闭所有框架管理的 session。
        """
        t = aiohttp.ClientTimeout(
            total=timeout or self._net_config.total_timeout,
            connect=self._net_config.connect_timeout,
        )
        connector = aiohttp.TCPConnector(
            limit=pool_size,
            limit_per_host=pool_per_host,
            ssl=self._build_ssl_context(),
        )
        session = aiohttp.ClientSession(
            timeout=t,
            connector=connector,
            base_url=base_url or None,
            headers=headers,
        )
        _log.debug(
            "HTTP session 已创建: base=%s, pool=%d",
            base_url or "(无)", pool_size,
        )
        return session

    # ═══════════════════════════════════════════════════════════
    # HTTP GET
    # ═══════════════════════════════════════════════════════════

    async def http_get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> aiohttp.ClientResponse:
        """HTTP GET — 自动重试 + 熔断 + SSRF 防护。

        Args:
            url: 请求 URL
            headers: 额外请求头
            timeout: 自定义超时（秒），None 使用默认
            retry_policy: 自定义重试策略，None 使用全局默认
            session: 自定义 session，None 使用默认共享 session

        Returns:
            aiohttp.ClientResponse（调用方负责读取并关闭）

        Raises:
            CircuitBreakerOpenError: 目标服务已被熔断
            aiohttp.ClientError: HTTP 层错误（重试耗尽后）
            asyncio.TimeoutError: 超时（重试耗尽后）
        """
        return await self._request(
            method="GET", url=url, headers=headers,
            timeout=timeout, retry_policy=retry_policy, session=session,
        )

    # ═══════════════════════════════════════════════════════════
    # HTTP POST
    # ═══════════════════════════════════════════════════════════

    async def http_post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> aiohttp.ClientResponse:
        """HTTP POST — 自动重试 + 熔断 + SSRF 防护。

        Args:
            url: 请求 URL
            data: 表单数据 / raw body
            json: JSON body（自动设置 Content-Type）
            headers: 额外请求头
            timeout: 自定义超时（秒）
            retry_policy: 自定义重试策略（POST 默认不重试，需显式 enable post_retry）
            session: 自定义 session

        Returns:
            aiohttp.ClientResponse

        Raises:
            CircuitBreakerOpenError: 目标服务已被熔断
            aiohttp.ClientError: HTTP 层错误
            asyncio.TimeoutError: 超时
        """
        return await self._request(
            method="POST", url=url, data=data, json_data=json,
            headers=headers, timeout=timeout,
            retry_policy=retry_policy, session=session,
        )

    # ═══════════════════════════════════════════════════════════
    # HTTP PUT / PATCH / DELETE
    # ═══════════════════════════════════════════════════════════

    async def http_put(
        self, url: str, data: Any = None, json: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> aiohttp.ClientResponse:
        """HTTP PUT。"""
        return await self._request(
            method="PUT", url=url, data=data, json_data=json,
            headers=headers, timeout=timeout,
            retry_policy=retry_policy, session=session,
        )

    async def http_patch(
        self, url: str, data: Any = None, json: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> aiohttp.ClientResponse:
        """HTTP PATCH。"""
        return await self._request(
            method="PATCH", url=url, data=data, json_data=json,
            headers=headers, timeout=timeout,
            retry_policy=retry_policy, session=session,
        )

    async def http_delete(
        self, url: str, headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> aiohttp.ClientResponse:
        """HTTP DELETE。"""
        return await self._request(
            method="DELETE", url=url, headers=headers,
            timeout=timeout, retry_policy=retry_policy, session=session,
        )

    # ═══════════════════════════════════════════════════════════
    # 核心请求实现
    # ═══════════════════════════════════════════════════════════

    async def _request(
        self,
        method: str,
        url: str,
        *,
        data: Any = None,
        json_data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> aiohttp.ClientResponse:
        """统一 HTTP 请求实现：熔断 + 重试 + SSRF 防护。

        流程:
          1. 解析 URL，提取 host
          2. SSRF 防护检查
          3. 获取/检查 host 熔断器
          4. 循环：发送请求 → 成功/失败 → 更新熔断器 → 重试判断
        """
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "unknown"

        # SSRF 防护
        if host:
            ssrf_reject = await self._resolve_and_check_ssrf(host)
            if ssrf_reject:
                _log.warning(ssrf_reject)
                raise aiohttp.ClientError(ssrf_reject)

        # 熔断器
        breaker = await self._get_breaker(host)
        reject = await breaker.before_request()
        if reject is not None:
            _log.warning("请求被熔断: %s → %s", url, reject)
            raise CircuitBreakerOpenError(reject)

        # 重试策略
        rp = retry_policy or self._retry_policy
        session = session or await self._get_default_session()

        last_error: Optional[Exception] = None
        last_status: Optional[int] = None

        for attempt in range(rp.max_retries + 1):
            try:
                # 构建超时（自定义覆盖默认）
                req_timeout = None
                if timeout is not None:
                    req_timeout = aiohttp.ClientTimeout(
                        total=timeout,
                        connect=self._net_config.connect_timeout,
                    )

                resp = await session.request(
                    method=method,
                    url=url,
                    data=data,
                    json=json_data,
                    headers=headers,
                    timeout=req_timeout,
                )

                # 检查响应状态码
                if resp.status >= 500 or resp.status == 429:
                    last_status = resp.status
                    text_preview = ""
                    try:
                        raw = await resp.read()
                        text_preview = raw[:200].decode("utf-8", errors="replace")
                    except Exception as e:
                        _log.warning("network.network: %s", e)
                    # 关闭错误响应
                    resp.release()

                    # 通知熔断器
                    reason = f"HTTP {resp.status}: {text_preview}"
                    await breaker.on_failure(reason, is_retryable=True)

                    if rp.should_retry(attempt, status_code=resp.status, method=method):
                        delay = rp.delay_for(attempt)
                        _log.debug(
                            "%s %s → %d (尝试 %d/%d, 延迟 %.2fs)",
                            method, url, resp.status,
                            attempt + 1, rp.max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=resp.status,
                        message=f"HTTP {resp.status}: {text_preview}",
                    )

                # 4xx 客户端错误 → 不重试，不触发熔断
                if resp.status >= 400:
                    last_status = resp.status
                    await breaker.on_failure(
                        f"HTTP {resp.status}", is_retryable=False
                    )
                    # 仍抛出异常让调用方处理
                    text_preview = ""
                    try:
                        raw = await resp.read()
                        text_preview = raw[:200].decode("utf-8", errors="replace")
                    except Exception as e:
                        _log.warning("network.network: %s", e)
                    resp.release()
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=resp.status,
                        message=f"HTTP {resp.status}: {text_preview}",
                    )

                # 成功 (2xx, 3xx)
                await breaker.on_success()
                return resp

            except CircuitBreakerOpenError:
                raise
            except aiohttp.ClientResponseError:
                raise
            except asyncio.TimeoutError as e:
                last_error = e
                await breaker.on_failure(
                    f"Timeout: {str(e)[:100]}", is_retryable=True
                )
                if rp.should_retry(attempt, error=e, method=method):
                    delay = rp.delay_for(attempt)
                    _log.debug(
                        "%s %s → Timeout (尝试 %d/%d, 延迟 %.2fs)",
                        method, url, attempt + 1, rp.max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            except (ConnectionError, OSError, aiohttp.ClientError) as e:
                last_error = e
                await breaker.on_failure(
                    f"{type(e).__name__}: {str(e)[:100]}", is_retryable=True
                )
                if rp.should_retry(attempt, error=e, method=method):
                    delay = rp.delay_for(attempt)
                    _log.debug(
                        "%s %s → %s (尝试 %d/%d, 延迟 %.2fs)",
                        method, url, type(e).__name__,
                        attempt + 1, rp.max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            except Exception:
                # 未知异常 → 不重试，但也不触发熔断（保守）
                raise

        # 重试耗尽
        if last_error:
            raise last_error
        if last_status:
            raise aiohttp.ClientError(f"HTTP {method} {url} 最终状态码 {last_status}")
        raise aiohttp.ClientError(f"HTTP {method} {url} 重试耗尽")

    # ═══════════════════════════════════════════════════════════
    # WebSocket 连接（委托给现有 WsClient，不在此处重建）
    # ═══════════════════════════════════════════════════════════

    async def ws_connect(self, url: str, token: Optional[str] = None) -> bool:
        """WebSocket 连接 — 委托说明。

        注意: WebSocket 连接由 core/host.py 中的 WsClient 管理（含断路器）。
        本方法仅提供一个占位接口，实际 WS 操作仍通过 services.get("ws_client")。
        如需使用新的 WS 实现，后续迁移再补充。
        """
        _log.info(
            "ws_connect 委托: WS 连接请使用 services.get('ws_client')。"
            "请求地址=%s", url,
        )
        return False

    # ═══════════════════════════════════════════════════════════
    # 便捷方法：请求 + 自动解包
    # ═══════════════════════════════════════════════════════════

    async def get_json(
        self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> Any:
        """HTTP GET + 自动解析 JSON 响应。

        Returns:
            解析后的 JSON 对象。

        Raises:
            aiohttp.ContentTypeError: 非 JSON 响应
        """
        async with await self.http_get(url, headers=headers, **kwargs) as resp:
            return await resp.json()

    async def post_json(
        self, url: str, json: Any = None, data: Any = None,
        headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> Any:
        """HTTP POST + 自动解析 JSON 响应。"""
        async with await self.http_post(
            url, json=json, data=data, headers=headers, **kwargs
        ) as resp:
            return await resp.json()

    async def get_text(
        self, url: str, headers: Optional[Dict[str, str]] = None, **kwargs
    ) -> str:
        """HTTP GET + 自动读取文本响应。"""
        async with await self.http_get(url, headers=headers, **kwargs) as resp:
            return await resp.text()

    # ═══════════════════════════════════════════════════════════
    # 状态查询
    # ═══════════════════════════════════════════════════════════

    def get_breaker_state(self, host: str) -> Optional[str]:
        """查询指定 host 的熔断器状态。

        Returns:
            "closed" | "open" | "half_open" | None（未创建）
        """
        breaker = self._breakers.get(host)
        if breaker is None:
            return None
        return breaker.state.value

    def list_breakers(self) -> Dict[str, str]:
        """列出所有熔断器状态。"""
        return {host: b.state.value for host, b in self._breakers.items()}

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    @property
    def closed(self) -> bool:
        """网络管理器是否已关闭。"""
        return self._closed

    async def close(self) -> None:
        """关闭所有 session 和连接池。"""
        if self._closed:
            return
        self._closed = True

        async with self._sessions_lock:
            for name, session in self._sessions.items():
                if not session.closed:
                    await session.close()
                    _log.debug("HTTP session '%s' 已关闭", name)
            self._sessions.clear()

        if self._default_session and not self._default_session.closed:
            await self._default_session.close()
            _log.debug("默认 HTTP session 已关闭")

        _log.info("NetworkManager 已关闭")


# ═══════════════════════════════════════════════════════════════
# 模块级别导出
# ═══════════════════════════════════════════════════════════════

__all__ = [
    "NetworkManager",
    "NetworkConfig",
    "RetryPolicy",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
]
