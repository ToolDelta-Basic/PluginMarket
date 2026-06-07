"""测试模块，提供 .ping 命令。"""
from ...core.module import Module
from ...core.kernel.decorators import command


class DummyModule(Module):
    """测试模块，提供 .ping 命令。"""

    name = "dummy"
    tier = 300  # TIER_APP  # 用户应用层
    version = (0, 0, 1)
    required_services = ["message"]

    async def on_init(self):
        """初始化时打印日志。"""

        async def _dbg_ping():
            """调试端点。"""
            return "pong from debug"

        try:
            debug = self.services.get("debug")
            await debug.register_module(
                self.name, {"ping": _dbg_ping}
            )
        except KeyError:
            pass

        print("[DummyModule] 初始化完成")

    @command(".ping")
    async def cmd_ping(self, ctx):
        """回复 pong!"""
        await ctx.reply("pong!")
