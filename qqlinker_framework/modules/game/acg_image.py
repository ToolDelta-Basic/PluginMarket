"""随机二次元图片模块 — 直接通过 URL 发送 ACG 图片到 QQ 群"""
import logging
import time

from ...core.module import Module
from ...core.decorators import command

logger = logging.getLogger(__name__)


class ACGImageModule(Module):
    """随机二次元图片模块。

    命令：
        .来张图 / .二次元 / .随机图片 — 发送一张随机 ACG 图片到群

    原理：
        将 ACG API 地址直接嵌入 CQ 码 [CQ:image,file=URL]，
        由 OneBot 客户端自行下载，无需本地中转。
    """

    name = "acg_image"
    version = (1, 0, 1)
    dependencies: list[str] = []
    required_services = ["message", "config"]

    default_config = {
        "acg_image": {
            "ACG图片API地址": "http://183.66.27.45:8092/acg/api?format=original",
            "冷却秒": 5,
            "冷却提示": "[CQ:at,qq={qqid}] 太快了！请等待 {remain} 秒后再试。",
            "发送中提示": "[CQ:at,qq={qqid}] 正在为你寻找图片...",
            "失败提示": "[CQ:at,qq={qqid}] 获取图片失败，请稍后再试。",
        }
    }

    async def on_init(self) -> None:
        """注册配置、命令和冷却字典。"""
        self._cooldowns: dict[int, float] = {}

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
        cache_buster = int(time.time() * 1000)
        sep = "&" if "?" in api_url else "?"
        image_url = f"{api_url}{sep}_t={cache_buster}"

        # 发送 CQ 码
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
