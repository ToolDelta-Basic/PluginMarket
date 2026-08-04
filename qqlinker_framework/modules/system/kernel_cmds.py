import asyncio
import inspect
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from typing import TYPE_CHECKING

_CQ_RE = re.compile(r'\[CQ:[^\]]+\]')

if TYPE_CHECKING:
    from ...libraries.channel_host import ChannelHost as FrameworkHost

from ...core.module import Module
from ...core.kernel.decorators import command, listen
from ...core.kernel.events import GroupMessageEvent

_log = logging.getLogger(__name__)

# ── 会话状态 ──────────────────────────────────────────────

class SessionState:
    """CMD 会话状态枚举。"""
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"

SESSION_TIMEOUT_SECONDS = 300


def parse_args(text: str) -> Tuple[str, Dict[str, str]]:
    """解析 CMD 命令参数。"""
    tokens = text[1:].strip().split()
    if not tokens:
        return "", {}
    cmd = tokens[0].lower()
    params: Dict[str, str] = {}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:].lower()
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                params[key] = tokens[i + 1]
                i += 2
            else:
                params[key] = ""
                i += 1
        else:
            i += 1
    return cmd, params


class CmdSession:
    """CMD 交互式命令会话。"""
    def __init__(self, host, ctx: Any) -> None:
        self.host = host
        self.ctx = ctx
        self._modules_svc = host.services.try_get("modules")
        self.state = SessionState.ACTIVE
        self._last_activity = time.monotonic()
        self._caller_uid = getattr(ctx, 'sender_uid', 400)
        _log.info("CMD 会话已创建 (caller_uid=%s)", self._caller_uid)

    def is_timed_out(self) -> bool:
        """检查会话是否超时。"""
        return (time.monotonic() - self._last_activity) > SESSION_TIMEOUT_SECONDS

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    async def handle(self, text: str) -> str:
        self._touch()
        if self.state == SessionState.EXITED:
            return "CMD 会话已退出。重新进入请发送 .cmd"
        if not text.startswith("."):
            return "CMD 命令必须以 '.' 开头。输入 .help 查看可用命令。"
        cmd_name, params = parse_args(text)
        if not cmd_name:
            return "空命令。输入 .help 查看可用命令。"
        try:
            return await self._dispatch(cmd_name, params)
        except Exception as e:
            _log.exception("CMD 命令 '.%s' 执行异常", cmd_name)
            return f"✗ 命令执行异常: {e}"

    async def _dispatch(self, cmd: str, params: Dict[str, str]) -> str:
        handlers = {
            "kill": self._cmd_kill, "grant": self._cmd_grant,
            "revoke": self._cmd_revoke, "ulist": self._cmd_ulist,
            "exec": self._cmd_exec, "run": self._cmd_run,
            "freeze": self._cmd_freeze, "thaw": self._cmd_thaw,
            "help": self._cmd_help, "exit": self._cmd_exit, "quit": self._cmd_exit,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return f"未知命令: .{cmd}\n输入 .help 查看可用命令列表。"
        result = handler(params)
        if inspect.iscoroutine(result):
            result = await result
        return result

    async def _cmd_kill(self, params):
        """卸载模块并持久化写入注册表（改为禁用状态）。

        v7: 不仅从内存卸载，还会写入模块注册表 JSON，
        确保框架重启后模块不会被重新加载。
        """
        target_name = params.get("name", "")
        mode = params.get("mode", "graceful").lower()
        confirm = params.get("confirm", "").lower()
        if not target_name:
            return "用法: .kill --name <模块名> [--mode graceful|force|hard] --confirm yes"
        if mode not in ("graceful", "force", "hard"):
            return f"无效的 mode: '{mode}'"
        if confirm != "yes":
            mod = self._modules_svc.get(target_name)
            if mod is None:
                return f"✗ 模块 '{target_name}' 未加载"
            uid = getattr(mod, 'uid', '?')
            return f"⚠️ 即将{self._mode_label(mode)}模块:\n 名称: {target_name}\n UID: {uid}\n 模式: {mode}\n\n此操作不可撤销！确认请追加: --confirm yes"
        try:
            # v7: 先持久化写入注册表（设为禁用）
            registry = None  # TODO: registry via modules service
            if registry is not None:
                registry.set_enabled(target_name, False)
                _log.info(
                    "注册表: 模块 '%s' 已标记为禁用 (由 .kill 命令)",
                    target_name,
                )
            # 从内存卸载
            ok = await self._modules_svc.unload(target_name)
            if ok:
                return (
                    f"✓ 模块 '{target_name}' 已卸载并禁用"
                    if registry
                    else f"✓ 模块 '{target_name}' 已卸载"
                )
            return "✗ 卸载失败"
        except Exception as e:
            _log.exception(".kill 命令异常")
            return f"✗ 异常: {e}"

    def _cmd_grant(self, params):
        target_name = params.get("name", "")
        target_tier = params.get("tier", "").lower()
        if not target_name or not target_tier:
            return "用法: .grant --name <模块名> --tier <kernel|daemon|service|app|nobody>"
        valid = {"kernel", "daemon", "service", "app", "nobody"}
        if target_tier not in valid:
            return f"✗ 无效 tier: '{target_tier}'"

        # 查找模块
        loaded = self._modules_svc.list_loaded()
        mod = loaded.get(target_name)
        if mod is None:
            return f"✗ 模块 '{target_name}' 未加载"

        old_uid = getattr(mod, 'uid', 400)

        # 安全检查
        if target_tier == "kernel":
            return "✗ 不可将模块提权至 kernel(0)"
        if old_uid == 0:
            return "✗ 不可降级 uid=0 的内核模块"

        reverse_labels = {v: k for k, v in {0: "kernel", 100: "daemon", 200: "service", 300: "app", 400: "nobody"}.items()}
        new_uid = reverse_labels.get(target_tier, 400)

        # 持久化外部模块授权
        from ..core.drivers.autodiscover import grant_external_module_uid
        try:
            grant_external_module_uid(target_name, new_uid)
        except Exception as e:
            _log.warning("kernel_cmds.kernel_cmds: %s", e)

        # 刷新模块视图
        mod.refresh_view(new_uid, self.host.services)
        old_tier = {0: "kernel", 100: "daemon", 200: "service", 300: "app", 400: "nobody"}.get(old_uid, str(old_uid))
        return f"✓ 模块 '{target_name}': {old_tier}(uid={old_uid}) → {target_tier}(uid={new_uid})"

    def _cmd_revoke(self, params):
        target_name = params.get("name", "")
        if not target_name:
            return "用法: .revoke --name <模块名>"
        loaded = self._modules_svc.list_loaded()
        mod = loaded.get(target_name)
        if mod is None:
            return f"✗ 模块 '{target_name}' 未加载"
        old_uid = getattr(mod, 'uid', 400)
        if old_uid == 0:
            return "✗ 不可撤销 uid=0 的内核模块"
        from ..core.drivers.autodiscover import revoke_external_module_uid
        try:
            revoke_external_module_uid(target_name)
        except Exception as e:
            _log.warning("kernel_cmds._cmd_revoke: %s", e)
        mod.refresh_view(400, self.host.services)
        return f"✓ 模块 '{target_name}' 授权已撤销 → nobody(400)"

    async def _cmd_freeze(self, params):
        """.freeze --name <模块名>  冻结指定模块"""
        target_name = params.get("name", "")
        if not target_name:
            return "用法: .freeze --name <模块名>"
        try:
            ok = await self._modules_svc.freeze(target_name)
            if ok:
                return f"✓ 模块 '{target_name}' 已冻结"
            return f"✗ 模块 '{target_name}' 冻结失败（模块不存在/不可冻结/已冻结）"
        except Exception as e:
            _log.exception(".freeze 命令异常")
            return f"✗ 异常: {e}"

    async def _cmd_thaw(self, params):
        """.thaw --name <模块名>  解冻指定模块"""
        target_name = params.get("name", "")
        if not target_name:
            return "用法: .thaw --name <模块名>"
        try:
            ok = await self._modules_svc.thaw(target_name)
            if ok:
                return f"✓ 模块 '{target_name}' 已解冻"
            return f"✗ 模块 '{target_name}' 解冻失败（模块不存在/未冻结）"
        except Exception as e:
            _log.exception(".thaw 命令异常")
            return f"✗ 异常: {e}"

    def _cmd_ulist(self, params):
        loaded = self._modules_svc.list_loaded()
        if not loaded:
            return "（无已加载模块）"
        lines = ["当前已加载模块:"]
        for name, mod in sorted(loaded.items()):
            uid = getattr(mod, 'uid', '?')
            tier = getattr(type(mod), 'tier', '?')
            enabled = "✓" if getattr(mod, 'enabled', True) else "✗"
            lines.append(f"  [{enabled}] {name}  uid={uid}  tier={tier}")
        return "\n".join(lines)

    def _cmd_exec(self, params):
        call_target = params.get("call", "")
        if not call_target:
            return "用法: .exec --call <模块名.方法名> [arg1 arg2]"
        parts = call_target.split(".", 1)
        if len(parts) != 2:
            return "✗ 格式: .exec --call <模块.方法>"
        mod_name, method_name = parts
        loaded = self._modules_svc.list_loaded()
        mod = loaded.get(mod_name)
        if mod is None:
            return f"✗ 模块 '{mod_name}' 未加载"
        method = getattr(mod, method_name, None)
        if method is None or not callable(method):
            return f"✗ '{method_name}' 在 '{mod_name}' 中不存在"
        args = list(params.values()) if params else []
        try:
            result = method(*args) if args else method()
            return f"✓ {mod_name}.{method_name}: {str(result)[:500]}" if result is not None else f"✓ {mod_name}.{method_name} 执行完成"
        except Exception as e:
            return f"✗ {mod_name}.{method_name}: {e}"

    def _cmd_run(self, params):
        cmd = params.get("cmd", "")
        if not cmd:
            return "用法: .run --cmd <游戏指令>"
        adapter = self.host.services.try_get("adapter")
        if adapter is None:
            return "✗ 游戏适配器未就绪"
        try:
            adapter.send_game_command(cmd)
            return f"✓ 已执行: /{cmd}"
        except Exception as e:
            return f"✗ 执行失败: {e}"

    @staticmethod
    def _cmd_help(params):
        return (
            "══════ CMD 控制台 ══════\n"
            ".kill --name <模块> [--mode graceful|force|hard] --confirm yes  卸载模块\n"
            ".freeze --name <模块>  冻结模块（保留实例但取消事件/命令）\n"
            ".thaw --name <模块>  解冻模块（重新注册事件/命令）\n"
            ".ulist  列出所有已加载模块\n"
            ".run --cmd <游戏指令>  执行游戏指令\n"
            ".help  显示此帮助\n"
            ".exit  退出 CMD 会话"
        )

    def _cmd_exit(self, params):
        self.state = SessionState.EXITED
        return "CMD 会话已退出。再见。"

    @staticmethod
    def _mode_label(mode):
        return {"graceful": "优雅卸载", "force": "强制卸载", "hard": "硬卸载"}.get(mode, mode)


# ── 模块定义 ─────────────────────────────────────────────

class KernelCMDsModule(Module):
    """CMD 交互式命令会话模块。"""
    background = True

    name = "kernel_cmds"
    mid = 0
    tier = 0  # deprecated, use mid
    version = (1, 0, 0)
    required_services = ["message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._sessions: Dict[int, CmdSession] = {}

    async def on_init(self):
        pass

    @command(".cmd", min_uid=0)
    async def _cmd_enter(self, ctx):
        """进入 CMD 会话"""
        host = None
        try:
            host = self._root_services.get("_host")
        except Exception as e:
            _log.warning("kernel_cmds._cmd_enter: %s", e)
        if host is None:
            await ctx.reply("✗ 框架主机引用不可用")
            return
        self._sessions[ctx.user_id] = CmdSession(
            host,
            ctx,
        )
        await ctx.reply("CMD 会话已启动。输入 .help 查看命令，.exit 退出。")

    # ── v6: 冻结/解冻/状态 内核命令 ──

    @command(".冻结", min_uid=0)
    async def _cmd_freeze(self, ctx):
        """冻结指定模块（kernel 级命令）"""
        parts = ctx.message.split(None, 1) if ctx.message else []
        if len(parts) < 2:
            await ctx.reply("用法: .冻结 <模块名|列表>")
            return
        target = parts[1].strip()
        if target == "列表":
            # 显示已冻结模块
            try:
                modules_svc = self._root_services.get("modules")
            except Exception:
                modules_svc = None
            if modules_svc is None:
                await ctx.reply("✗ 框架主机引用不可用")
                return
            frozen = []
            if not frozen:
                await ctx.reply("当前没有已冻结的模块")
            else:
                await ctx.reply(
                    f"已冻结模块 ({len(frozen)} 个): "
                    + ", ".join(frozen)
                )
            return
        # 冻结指定模块
        try:
            modules_svc = self._root_services.get("modules")
        except Exception:
            modules_svc = None
        if modules_svc is None:
            await ctx.reply("✗ 框架主机引用不可用")
            return
        ok = await modules_svc.freeze(target)
        if ok:
            await ctx.reply(f"✓ 模块 '{target}' 已冻结")
        else:
            await ctx.reply(f"✗ 模块 '{target}' 冻结失败（不存在/不可冻结/已冻结）")

    @command(".解冻", min_uid=0)
    async def _cmd_thaw(self, ctx):
        """解冻指定模块（kernel 级命令）"""
        parts = ctx.message.split(None, 1) if ctx.message else []
        if len(parts) < 2:
            await ctx.reply("用法: .解冻 <模块名>")
            return
        target = parts[1].strip()
        try:
            modules_svc = self._root_services.get("modules")
        except Exception:
            modules_svc = None
        if modules_svc is None:
            await ctx.reply("✗ 框架主机引用不可用")
            return
        ok = await modules_svc.thaw(target)
        if ok:
            await ctx.reply(f"✓ 模块 '{target}' 已解冻")
        else:
            await ctx.reply(f"✗ 模块 '{target}' 解冻失败（不存在/未冻结）")

    @command(".状态", min_uid=100)
    async def _cmd_status(self, ctx):
        """显示框架健康摘要或单模块详情（daemon 级命令）"""
        try:
            modules_svc = self._root_services.get("modules")
        except Exception:
            modules_svc = None
        if modules_svc is None:
            await ctx.reply("✗ 框架主机引用不可用")
            return
        parts = ctx.message.split(None, 1) if ctx.message else []
        host = self._root_services.try_get("_host") if hasattr(self._root_services, 'try_get') else None
        telemetry = getattr(host, 'telemetry', None) if host else None

        if len(parts) < 2 or not parts[1].strip():
            # 显示框架整体健康摘要
            lines = ["📊 **框架健康摘要**"]
            if telemetry:
                summary = telemetry.summary()
                lines.append(f"  运行时间: {summary['uptime_human']}")
                lines.append(f"  指标数: {summary['total_metrics']}")
                lines.append(f"  告警规则: {summary['total_alerts']}")
                lines.append(f"  已触发告警: {summary['triggered_alerts']}")
                health = summary.get('health', {})
                if health:
                    lines.append(f"  健康模块: {health.get('healthy', '?')}")
                    lines.append(f"  注意模块: {health.get('attention', '?')}")
                    lines.append(f"  降级模块: {health.get('degraded', '?')}")
                    lines.append(f"  不健康模块: {health.get('unhealthy', '?')}")
            frozen = []
            if frozen:
                lines.append(f"  ❄️ 已冻结: {', '.join(frozen)}")
            loaded = modules_svc.list_loaded()
            lines.append(f"  已加载模块: {len(loaded)}")
            lines.append("\n💡 .状态 <模块名> 查看单模块详情")
            await ctx.reply("\n".join(lines))
        else:
            # 显示单模块详情
            target = parts[1].strip()
            mod = modules_svc.get(target)
            if mod is None:
                await ctx.reply(f"✗ 模块 '{target}' 未加载")
                return
            frozen = getattr(mod, 'frozen', False)
            uid = getattr(mod, 'uid', '?')
            enabled = getattr(mod, 'enabled', True)
            version = getattr(mod, 'version', (0, 0, 0))
            deps = getattr(mod, 'dependencies', [])
            req_svcs = getattr(mod, 'required_services', [])
            cmds = list(getattr(mod, '_commands', {}).keys())
            events = len(getattr(mod, '_event_handlers', []))

            lines = [
                f"📦 **{target}** 模块详情",
                f"  UID: {uid}",
                f"  状态: {'❄️ 已冻结' if frozen else ('✅ 启用' if enabled else '⛔ 禁用')}",
                f"  版本: {'.'.join(str(v) for v in version)}",
                f"  依赖: {', '.join(deps) if deps else '(无)'}",
                f"  所需服务: {', '.join(req_svcs) if req_svcs else '(无)'}",
                f"  命令数: {len(cmds)}",
                f"  事件订阅数: {events}",
            ]
            if cmds:
                lines.append(f"  命令: {', '.join(cmds[:10])}")
                if len(cmds) > 10:
                    lines.append(f"    ... 等 {len(cmds)} 个")
            await ctx.reply("\n".join(lines))

    @listen(GroupMessageEvent, priority=50)
    async def _on_cmd_input(self, event):
        session = self._sessions.get(event.user_id)
        if session is None:
            return
        if session.is_timed_out():
            del self._sessions[event.user_id]
            await self.message.send_group(event.group_id, "CMD 会话已超时自动关闭。")
            return
        # 剥离 CQ 码后再交给 CMD 会话处理
        clean_msg = _CQ_RE.sub('', event.message or '').strip()
        if not clean_msg:
            return
        reply = await session.handle(clean_msg)
        event.handled = True
        await self.message.send_group(event.group_id, reply)
        if session.state == SessionState.EXITED:
            del self._sessions[event.user_id]


def can_enter_cmd(caller_uid: int, admin_uids: Optional[List[int]] = None) -> bool:
    """检查是否可进入 CMD 会话。"""
    if caller_uid == 0:
        return True
    if admin_uids and caller_uid in admin_uids:
        return True
    return False
