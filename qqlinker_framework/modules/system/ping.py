"""测试模块，提供 .ping 命令。"""
from ...core.module import Module
from ...core.decorators import command


class DummyModule(Module):
    """测试模块，提供 .ping 命令。"""

    name = "dummy"
    version = (0, 0, 1)
    required_services = ["message"]

    async def on_init(self):
        async def _dbg_ping(**kw):
            return "pong from debug"
        try:
            self.services.get("debug").register_module(self.name, {"ping": _dbg_ping})
        except KeyError:
            pass
        """初始化时打印日志。"""
        print("[DummyModule] 初始化完成")

    @command(".ping")
    async def cmd_ping(self, ctx):
        """回复 pong!"""
        await ctx.reply("pong!")
