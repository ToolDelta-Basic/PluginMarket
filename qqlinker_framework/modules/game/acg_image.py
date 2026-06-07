"""随机二次元图片模块 — 直接通过 URL 发送 ACG 图片到 QQ 群

安全特性:
  - URL 验证（拒绝内网地址、仅允许 http/https）
  - 内容类型预期为 image/*（由 OneBot 客户端处理）
"""
import logging
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


def _is_safe_url(url: str) -> bool:
    """验证 URL 是否安全（拒绝内网、仅允许 http/https）。

    Args:
        url: 待验证的 URL。

    Returns:
        True 如果 URL 安全。
    """
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


class ACGImageModule(Module):
    """随机二次元图片模块。

    命令：
        .来张图 / .二次元 / .随机图片 — 发送一张随机 ACG 图片到群

    原理：
        将 ACG API 地址直接嵌入 CQ 码 [CQ:image,file=URL]，
        由 OneBot 客户端自行下载，无需本地中转。
    """

    name = "acg_image"
    tier = 300  # TIER_APP  # app: 业务模块
    version = (1, 0, 1)
    dependencies: list[str] = []
    required_services = ["message", "config"]

    default_config = {
        "acg_image": {
            "ACG图片API地址": "http://127.0.0.1:8092/acg/api?format=original",
            "冷却秒": 5,
            "冷却提示": "[CQ:at,qq={qqid}] 太快了！请等待 {remain} 秒后再试。",
            "发送中提示": "[CQ:at,qq={qqid}] 正在为你寻找图片...",
            "失败提示": "[CQ:at,qq={qqid}] 获取图片失败，请稍后再试。",
        }
    }

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._cooldowns: dict[int, float] = {}

    async def on_init(self) -> None:
        """注册配置、命令和冷却字典。"""
        # 冷却字典已在 __init__ 中初始化

        # 注册调试端点（供 debug 引擎调用）
        try:
            debug = self.services.get("debug")

            async def _dbg_test():
                """发送测试图片到日志，不实际推送到群。"""
                url = self.config.get("acg_image.ACG图片API地址")
                code = f"[CQ:image,file={url}#t={int(time.time())}]"
                logger.info("[acg_image debug] CQ码: %s", code)
                return f"OK: {code[:80]}..."

            await debug.register_module(self.name, {"test": _dbg_test})
            logger.info("[acg_image] 调试端点已注册")
        except KeyError:
            pass

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

    @command(".来张图", description="发送一张随机二次元图片")
    async def _cmd_image(self, ctx):
        """命令入口：冷却检查 → 构造 CQ 码 → 发送。"""
        # 冷却检查
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

        # ── URL 安全验证 ──
        if not _is_safe_url(api_url):
            logger.warning(
                "[acg_image] API 地址不安全，已拦截: %s", api_url[:100]
            )
            fail_msg = (
                self.config.get("acg_image.失败提示", "发送失败")
                .replace("{qqid}", str(ctx.user_id))
            )
            await ctx.reply(fail_msg)
            return

        cache_buster = int(time.time() * 1000)
        sep = "&" if "?" in api_url else "?"
        image_url = f"{api_url}{sep}_t={cache_buster}"

        # 发送 CQ 码（OneBot 客户端负责下载，期望返回 image/* 内容）
        image_code = f"[CQ:image,file={image_url}]"
        try:
            await ctx.reply(image_code)
            logger.info(
                "[acg_image] 群 %s → %s",
                ctx.group_id, image_code[:120],
            )
        except Exception as e:
            logger.error("[acg_image] 发送失败: %s", e)
            fail_msg = (
                self.config.get("acg_image.失败提示", "发送失败")
                .replace("{qqid}", str(ctx.user_id))
            )
            await ctx.reply(fail_msg)
