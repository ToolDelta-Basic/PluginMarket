import collections
import logging
_log = logging.getLogger(__name__)
import time
from urllib.parse import urlparse

from ...core.module import Module
from ...core.kernel.decorators import command

logger = logging.getLogger(__name__)

# ── URL 安全验证 ──
import ipaddress

_BLOCKED_NETWORKS = [
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
]

# ── ACG 限流默认值 ──
_DEFAULT_GROUP_PER_MINUTE = 10
_DEFAULT_USER_PER_MINUTE = 3
_DEFAULT_ACG_TOKEN_COST = 1


def _is_safe_url(url: str) -> bool:
    """验证 URL 是否安全（拒绝内网、仅允许 http/https）。"""
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    hostname = hostname.strip()
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return False
    except ValueError:
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"):
            return False
        if hostname.endswith(".local") or hostname.endswith(".internal"):
            return False
    return True


class TimeWindowCounter:
    """时间窗口计数器 —— 用于 ACG 限流，不依赖 redis。

    使用双端队列记录时间戳，自动淘汰窗口外的旧记录。
    """

    def __init__(self, window_seconds: float = 60.0, max_hits: int = 10) -> None:
        self._window = window_seconds
        self._max = max_hits
        self._hits: collections.deque = collections.deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._hits and self._hits[0] < cutoff:
            self._hits.popleft()

    def check(self) -> bool:
        """检查是否在限流内（未超限返回 True）。"""
        now = time.time()
        self._prune(now)
        return len(self._hits) < self._max

    def hit(self) -> None:
        """记录一次命中。"""
        self._hits.append(time.time())

    @property
    def count(self) -> int:
        """当前窗口内计数。"""
        self._prune(time.time())
        return len(self._hits)


class ACGImageModule(Module):
    """随机二次元图片模块（v2 限流版）。

    命令：
        .来张图 / .二次元 / .随机图片 — 发送一张随机 ACG 图片到群

    限流：
        - 单群每分钟上限（默认 10）
        - 单人每分钟上限（默认 3）
        - 使用时间窗口计数器（deque），不依赖 redis

    余额：
        - 可选启用余额制，每次消耗点数（默认 1）
    """

    name = "acg_image"
    mid = 300
    tier = 300  # TIER_APP
    version = (1, 2, 0)
    background = False  # lazy: command-only, no @listen subscriptions
    dependencies: list[str] = []
    required_services = ["message", "config"]

    default_config = {
        "acg_image": {
            "ACG图片API地址": "http://127.0.0.1:8092/acg/api?format=original",
            "冷却秒": 5,
            "冷却提示": "[CQ:at,qq={qqid}] 太快了！请等待 {remain} 秒后再试。",
            "发送中提示": "[CQ:at,qq={qqid}] 正在为你寻找图片...",
            "失败提示": "[CQ:at,qq={qqid}] 获取图片失败，请稍后再试。",
            # ── v2 新增 ──
            "ACG冷却限制.单群每分钟": 10,
            "ACG冷却限制.单人每分钟": 3,
            "ACG余额制启用": False,
            "ACG每次消耗点数": 1,
        }
    }

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._cooldowns: dict[int, float] = {}
        # v2 限流计数器
        self._group_counters: dict[int, TimeWindowCounter] = {}
        self._user_counters: dict[int, TimeWindowCounter] = {}
        self._group_limit: int = _DEFAULT_GROUP_PER_MINUTE
        self._user_limit: int = _DEFAULT_USER_PER_MINUTE
        self._acg_balance_enabled: bool = False
        self._acg_token_cost: int = _DEFAULT_ACG_TOKEN_COST

    async def on_init(self) -> None:
        """注册配置、命令和限流参数。"""
        self._group_limit = self.config.get(
            "acg_image.ACG冷却限制.单群每分钟", _DEFAULT_GROUP_PER_MINUTE,
        )
        self._user_limit = self.config.get(
            "acg_image.ACG冷却限制.单人每分钟", _DEFAULT_USER_PER_MINUTE,
        )
        self._acg_balance_enabled = self.config.get(
            "acg_image.ACG余额制启用", False,
        )
        self._acg_token_cost = self.config.get(
            "acg_image.ACG每次消耗点数", _DEFAULT_ACG_TOKEN_COST,
        )
        logger.info(
            "[acg_image] 限流: 单群=%d/min, 单人=%d/min, 余额制=%s, 每次消耗=%d",
            self._group_limit, self._user_limit,
            "启用" if self._acg_balance_enabled else "禁用",
            self._acg_token_cost,
        )

        try:
            debug = self.services.get("debug")

            async def _dbg_test():
                url = self.config.get("acg_image.ACG图片API地址")
                code = f"[CQ:image,file={url}#t={int(time.time())}]"
                logger.info("[acg_image debug] CQ码: %s", code)
                return f"OK: {code[:80]}..."

            await debug.register_module(self.name, {"test": _dbg_test})
            logger.info("[acg_image] 调试端点已注册")
        except KeyError as e:
            _log.debug("acg_image._dbg_test: %s", e)

        for trigger in [".来张图", ".二次元", ".随机图片"]:
            self.register_command(
                trigger=trigger,
                callback=self._cmd_image,
                description="发送一张随机二次元图片",
                op_only=False,
            )

        logger.info("[acg_image] 模块初始化完成 (v%s)", ".".join(
            str(x) for x in self.version
        ))

    def _get_or_create_group_counter(self, group_id: int) -> TimeWindowCounter:
        """获取或创建群维度限流计数器。"""
        if group_id not in self._group_counters:
            self._group_counters[group_id] = TimeWindowCounter(
                window_seconds=60.0, max_hits=self._group_limit,
            )
        return self._group_counters[group_id]

    def _get_or_create_user_counter(self, user_id: int) -> TimeWindowCounter:
        """获取或创建用户维度限流计数器。"""
        if user_id not in self._user_counters:
            self._user_counters[user_id] = TimeWindowCounter(
                window_seconds=60.0, max_hits=self._user_limit,
            )
        return self._user_counters[user_id]

    async def _check_balance(self, ctx) -> bool:
        """余额检查：若余额制启用，调用 Balancer 检查/消费。

        Returns:
            True 允许继续；False 余额不足已提示。
        """
        if not self._acg_balance_enabled:
            return True

        try:
            balancer = self.services.get("balancer")
            if not balancer:
                logger.warning("[acg_image] 余额制已启用但 balancer 服务未注册")
                return True  # 降级：允许继续
        except (KeyError, AttributeError):
            logger.warning("[acg_image] balancer 服务不可用")
            return True

        balance = await balancer.get(ctx.group_id)
        if balance < self._acg_token_cost:
            await ctx.reply(
                f"⚠ ACG 图片余额不足，需要 {self._acg_token_cost} 点，"
                f"当前余额: {balance}。"
            )
            return False

        ok = await balancer.spend(ctx.group_id, self._acg_token_cost)
        if not ok:
            await ctx.reply(
                f"⚠ ACG 图片余额不足，需要 {self._acg_token_cost} 点。"
            )
            return False
        return True

    @command(".来张图", description="发送一张随机二次元图片")
    async def _cmd_image(self, ctx):
        """命令入口：限流检查 → 余额检查 → 冷却检查 → 构造 CQ 码 → 发送。"""
        # v2: 群维度限流
        group_counter = self._group_counters.get(ctx.group_id)
        if not group_counter:
            group_counter = TimeWindowCounter(
                window_seconds=60.0, max_hits=self._group_limit,
            )
            self._group_counters[ctx.group_id] = group_counter
        if not group_counter.check():
            await ctx.reply(
                f"[CQ:at,qq={ctx.user_id}] 本群 ACG 请求过于频繁，请等一会儿再试。"
            )
            return

        # v2: 用户维度限流
        user_counter = self._get_or_create_user_counter(ctx.user_id)
        if not user_counter.check():
            await ctx.reply(
                f"[CQ:at,qq={ctx.user_id}] 你的 ACG 请求过于频繁，请稍后再试。"
            )
            return

        # v2: 余额检查
        if not await self._check_balance(ctx):
            return

        # 记录限流命中
        group_counter.hit()
        user_counter.hit()

        # 单人冷却检查
        cd = self.config.get("acg_image.冷却秒", 5)
        now = time.time()
        remain = cd - (now - self._cooldowns.get(ctx.user_id, 0))
        if remain > 0:
            msg = (
                self.config.get("acg_image.冷却提示", "")
                .replace("{qqid}", str(ctx.user_id))
                .replace("{remain}", str(int(remain)))
            )
            await ctx.reply(msg)
            return
        self._cooldowns[ctx.user_id] = now

        # 发送中提示
        hint = (
            self.config.get("acg_image.发送中提示", "寻找图片...")
            .replace("{qqid}", str(ctx.user_id))
        )
        await ctx.reply(hint)

        # 构造带时间戳的图片 URL（防缓存）
        api_url = self.config.get("acg_image.ACG图片API地址")

        if not _is_safe_url(api_url):
            logger.warning("[acg_image] API 地址不安全，已拦截: %s", api_url[:100])
            fail_msg = (
                self.config.get("acg_image.失败提示", "发送失败")
                .replace("{qqid}", str(ctx.user_id))
            )
            await ctx.reply(fail_msg)
            return

        cache_buster = int(time.time() * 1000)
        sep = "&" if "?" in api_url else "?"
        image_url = f"{api_url}{sep}_t={cache_buster}"

        image_code = f"[CQ:image,file={image_url}]"
        try:
            await ctx.reply(image_code)
            logger.info("[acg_image] 群 %s → %s", ctx.group_id, image_code[:120])
        except Exception as e:
            logger.error("[acg_image] 发送失败: %s", e)
            fail_msg = (
                self.config.get("acg_image.失败提示", "发送失败")
                .replace("{qqid}", str(ctx.user_id))
            )
            await ctx.reply(fail_msg)
