import asyncio
import logging
import time
from typing import Callable, Dict, Optional

_log = logging.getLogger(__name__)

# 注册表
_registry: Dict[str, dict] = {}


def demo_scene(
    *,
    name: str,
    interval: float = 3.0,
    description: str = "",
    group_only: int = 0,
):
    """标记一个 async 函数为演示场景。"""

    def decorator(fn: Callable):
        _registry[name] = {
            "fn": fn,
            "name": name,
            "interval": interval,
            "description": description,
            "group_only": group_only,
        }
        return fn
    return decorator


class DemoContext:
    """演示场景执行上下文。

    user(name, text) — 模拟用户发送的消息
    bot(text)       — 模拟机器人回复（可加括号说明含义）
    sleep(seconds)  — 等待
    log(msg)        — 记录日志
    """

    def __init__(self, adapter, group_id: int):
        self._adapter = adapter
        self._group_id = group_id

    async def user(self, name: str, text: str):
        """模拟用户消息。"""
        msg = f"「{name}」{text}"
        try:
            self._adapter.send_group_msg(self._group_id, msg)
        except Exception as e:
            _log.error("演示消息发送失败: %s", e)

    async def bot(self, text: str):
        """模拟机器人回复。"""
        try:
            self._adapter.send_group_msg(self._group_id, text)
        except Exception as e:
            _log.error("演示消息发送失败: %s", e)

    async def sleep(self, seconds: float):
        """等待指定秒数。"""
        await asyncio.sleep(seconds)

    def log(self, msg: str):
        """记录演示日志。"""
        _log.info("[演示] %s", msg)


from ...core.module import Module
from ...core.kernel.decorators import command


class DemoModule(Module):
    """演示模式模块。"""

    name = "demo"
    mid = 300
    version = (1, 3, 0)
    required_services = ["message", "config", "adapter"]
    background = False

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._demo_tasks: dict[int, asyncio.Task] = {}

    async def on_init(self):
        pass

    async def on_stop(self):
        for gid, task in list(self._demo_tasks.items()):
            if not task.done():
                task.cancel()
                _log.info("取消演示任务: group=%d", gid)
        self._demo_tasks.clear()

    @command(".演示", description="演示模式: 列表|场景名")
    async def _cmd_demo(self, ctx):
        args = ctx.args if ctx.args else []
        if not args:
            await ctx.reply(".演示 <列表|场景名>\n  列表     — 查看演示场景\n  <场景名> — 执行演示")
            return

        sub = args[0]
        if sub == "列表":
            scenes = list_scenes()
            if not scenes:
                await ctx.reply("暂无演示场景")
                return
            lines = [f"📋 演示场景 ({len(scenes)} 个):"]
            for s in scenes:
                lines.append(f"  • {s['name']}")
                if s.get("description"):
                    lines.append(f"    {s['description']}")
            await ctx.reply("\n".join(lines))
            return

        scene = get_scene(sub)
        if scene is None:
            await ctx.reply(f"未找到演示场景 '{sub}'。使用 .演示 列表 查看可用场景")
            return

        gid = scene.get("group_only", 0)
        if gid and gid != ctx.group_id:
            await ctx.reply(f"演示场景 '{sub}' 仅限群 {gid} 使用")
            return

        existing = self._demo_tasks.get(ctx.group_id)
        if existing and not existing.done():
            await ctx.reply("⏳ 本群已有演示正在进行，请等待完成")
            return

        interval = scene.get("interval", 3.0)
        runner = DemoRunner(self.adapter, ctx.group_id, interval)
        task = asyncio.create_task(runner.run(scene["fn"], scene.get("group_only", 0)))
        self._demo_tasks[ctx.group_id] = task
        task.add_done_callback(lambda _t, g=ctx.group_id: self._demo_tasks.pop(g, None))
        await ctx.reply(f"🎬 演示 '{sub}' 开始 (间隔{interval}s)")


class DemoRunner:
    """演示场景执行器。"""

    def __init__(self, adapter, group_id: int, interval: float = 3.0):
        self._adapter = adapter
        self._group_id = group_id
        self._interval = interval

    async def run(self, scene_fn: Callable, group_only: int = 0):
        if group_only and group_only != self._group_id:
            _log.warning("演示限定群 %d ≠ %d，拒绝", group_only, self._group_id)
            return
        ctx = DemoContext(self._adapter, self._group_id)
        _log.info("演示开始: group=%d", self._group_id)
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(scene_fn(ctx), timeout=300.0)
        except asyncio.TimeoutError:
            _log.warning("演示超时 (300s)")
        except Exception as e:
            _log.error("演示异常: %s", e)
        elapsed = time.monotonic() - t0
        _log.info("演示结束: group=%d 耗时 %.1fs", self._group_id, elapsed)


def list_scenes() -> list[dict]:
    return [
        {"name": v["name"], "description": v["description"],
         "interval": v["interval"], "group_only": v["group_only"]}
        for v in _registry.values()
    ]


def get_scene(name: str) -> Optional[dict]:
    return _registry.get(name)


# ═══════════════════════════════════════════════════════════
# 内置演示场景
# ═══════════════════════════════════════════════════════════


@demo_scene(name="命令系统", interval=2.5,
            description="核心命令演示：帮助/在线/状态/ping")
async def _builtin_commands(ctx: DemoContext):
    await ctx.user("管理员", ".帮助")
    await ctx.bot("📋 QQLinker 命令列表:\n"
                  "  .帮助 — 查看命令帮助 (翻页浏览)\n"
                  "  .在线 — 查看在线玩家\n"
                  "  .状态 — 查看框架运行状态\n"
                  "  .ping — 心跳检测\n"
                  "  ... (共 17 条命令)")
    await ctx.sleep(3)
    await ctx.user("管理员", ".在线")
    await ctx.bot("当前在线 (3 人): Player1, Player2, Player3")
    await ctx.sleep(2)
    await ctx.user("管理员", ".状态")
    await ctx.bot("📊 框架状态\n"
                  "  运行时间: 2h 15m\n"
                  "  已加载模块: 12 个\n"
                  "  内存: 156MB / 800MB (正常)")
    await ctx.sleep(3)
    await ctx.user("管理员", ".ping")
    await ctx.bot("Pong! 🏓 (响应: 12ms)")
    await ctx.sleep(1.5)
    ctx.log("命令系统演示完成")


@demo_scene(name="规则引擎", interval=3.5,
            description="规则引擎：创建→匹配→触发 全流程演示")
async def _builtin_rules(ctx: DemoContext):
    await ctx.user("管理员", ".规则 创建")
    await ctx.bot("Step 1/5: 请输入规则名")
    await ctx.sleep(1.5)
    await ctx.user("管理员", "签到规则")
    await ctx.bot("Step 2/5: 选择匹配事件\n1.群消息  2.群成员增加")
    await ctx.sleep(1.5)
    await ctx.user("管理员", "1")
    await ctx.bot("Step 3/5: 选择匹配类型\n1.正则  2.关键词  3.完全匹配")
    await ctx.sleep(1.5)
    await ctx.user("管理员", "2")
    await ctx.bot("Step 4/5: 请输入匹配模式 [关键词]")
    await ctx.sleep(1.5)
    await ctx.user("管理员", "签到")
    await ctx.bot("Step 5/5: 请输入动作链\n(一行一条动作，输入'完成'结束)")
    await ctx.sleep(1.5)
    await ctx.user("管理员", "✅ 签到成功！积分+1")
    await ctx.bot("已添加动作 #1，继续输入或'完成'")
    await ctx.sleep(1.5)
    await ctx.user("管理员", "完成")
    await ctx.bot("规则预览:\n"
                  "  名称: 签到规则\n"
                  "  事件: 群消息\n"
                  "  模式: 关键词 = '签到'\n"
                  "  动作: 1 条\n"
                  "确认创建? (是/否)")
    await ctx.sleep(2)
    await ctx.user("管理员", "是")
    await ctx.bot("✅ 规则 '签到规则' 创建成功！")
    await ctx.sleep(2)
    await ctx.user("路人甲", "签到")
    await ctx.bot("✅ 签到成功！积分+1 (规则 '签到规则' 触发)")
    await ctx.sleep(2)
    await ctx.user("管理员", ".规则 列表")
    await ctx.bot("📋 本群规则 (1 条):\n"
                  "  • 签到规则 [群消息] 关键词='签到' → 1 条动作")
    await ctx.sleep(2)
    ctx.log("规则引擎演示完成")


@demo_scene(name="CMD会话", interval=2.5,
            description="CMD 管理控制台：进入→查看→退出")
async def _builtin_cmd(ctx: DemoContext):
    await ctx.user("管理员", ".cmd")
    await ctx.bot("已进入 CMD 会话 (300s 超时退出)\n输入 .help 查看可用命令")
    await ctx.sleep(2)
    await ctx.user("管理员", ".ulist")
    await ctx.bot("已加载模块 (12 个):\n"
                  "  help, kernel_auth, kernel_cmds, memory_guard,\n"
                  "  rule_engine, config_router, auth, game_admin,\n"
                  "  game_forwarder, webpanel, template, demo\n"
                  "  (UID 权限分级: daemon=100, service=200, app=300)")
    await ctx.sleep(3)
    await ctx.user("管理员", ".help")
    await ctx.bot("CMD 可用命令:\n"
                  "  .kill <模块>  — 卸载模块\n"
                  "  .grant <模块> <uid> — 提升权限\n"
                  "  .revoke <模块> — 降级到 nobody\n"
                  "  .ulist — 列出所有模块\n"
                  "  .freeze / .thaw — 冻结/解冻模块\n"
                  "  .help — 本帮助\n"
                  "  .exit — 退出")
    await ctx.sleep(3)
    await ctx.user("管理员", ".exit")
    await ctx.bot("CMD 会话已退出")
    await ctx.sleep(1.5)
    ctx.log("CMD 会话演示完成")
