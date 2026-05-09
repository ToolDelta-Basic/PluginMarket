# modules/dummy.py
from core.module import Module
from core.decorators import command

class DummyModule(Module):
    name = "dummy"
    version = (0, 0, 1)
    required_services = ["message"]

    async def on_init(self):
        self.register_command(".ping", self.cmd_ping)
        print("[DummyModule] 初始化完成")

    @command(".ping")
    async def cmd_ping(self, ctx):
        await ctx.reply("pong!")