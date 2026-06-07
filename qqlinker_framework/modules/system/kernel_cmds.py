"""CMD 交互式命令会话引擎 + 命令实现 (kernel_cmds)

═══════════════════════════════════════════════════════════════════════════
CMD 会话是轮询式的管理控制台：

 1. 用户输入 .cmd 进入 CMD 会话
 2. 后续以 '.' 开头的消息在当前会话中处理
 3. .exit / .quit 退出，或 300s 无输入自动超时

内置命令:
 .kill — 杀死/卸载模块
 .grant — 提升模块级别
 .revoke — 降级模块到 nobody
 .ulist — 列出所有模块
 .help — 帮助信息
 .exit — 退出会话

权限: 仅 uid=0（终端持有者）或被授权的管理员可进入 .cmd
═══════════════════════════════════════════════════════════════════════════
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.host import FrameworkHost

from ...core.kernel.services import (
    UID_ROOT,
    UID_NOBODY,
    uid_label,
)
from ...core.module import Module
from ...core.kernel.decorators import command, listen

_log = logging.getLogger(__name__)

# ── 会话状态 ──────────────────────────────────────────────

class SessionState:
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"

SESSION_TIMEOUT_SECONDS = 300


def parse_args(text: str) -> Tuple[str, Dict[str, str]]:
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
    def __init__(self, host: "FrameworkHost", ctx: Any) -> None:
        self.host = host
        self.ctx = ctx
        self.state = SessionState.ACTIVE
        self._last_activity = time.monotonic()
        self._caller_uid = getattr(ctx, 'sender_uid', UID_NOBODY)
        _log.info("CMD 会话已创建 (caller_uid=%s)", self._caller_uid)

    def is_timed_out(self) -> bool:
        return (time.monotonic() - self._last_activity) > SESSION_TIMEOUT_SECONDS

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    def handle(self, text: str) -> str:
        self._touch()
        if self.state == SessionState.EXITED:
            return "CMD 会话已退出。重新进入请发送 .cmd"
        if not text.startswith("."):
            return "CMD 命令必须以 '.' 开头。输入 .help 查看可用命令。"
        cmd_name, params = parse_args(text)
        if not cmd_name:
            return "空命令。输入 .help 查看可用命令。"
        try:
            return self._dispatch(cmd_name, params)
        except Exception as e:
            _log.exception("CMD 命令 '.%s' 执行异常", cmd_name)
            return f"✗ 命令执行异常: {e}"

    def _dispatch(self, cmd: str, params: Dict[str, str]) -> str:
        handlers = {
            "kill": self._cmd_kill, "grant": self._cmd_grant,
            "revoke": self._cmd_revoke, "ulist": self._cmd_ulist,
            "exec": self._cmd_exec, "run": self._cmd_run,
            "help": self._cmd_help, "exit": self._cmd_exit, "quit": self._cmd_exit,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return f"未知命令: .{cmd}\n输入 .help 查看可用命令列表。"
        return handler(params)

    def _cmd_kill(self, params):
        target_name = params.get("name", "")
        mode = params.get("mode", "graceful").lower()
        confirm = params.get("confirm", "").lower()
        if not target_name:
            return "用法: .kill --name <模块名> [--mode graceful|force|hard] --confirm yes"
        if mode not in ("graceful", "force", "hard"):
            return f"无效的 mode: '{mode}'"
        if confirm != "yes":
            mod = self.host.module_mgr._loaded_modules.get(target_name)
            if mod is None:
                return f"✗ 模块 '{target_name}' 未加载"
            uid = getattr(mod, 'uid', '?')
            return f"⚠️ 即将{self._mode_label(mode)}模块:\n 名称: {target_name}\n UID: {uid}\n 模式: {mode}\n\n此操作不可撤销！确认请追加: --confirm yes"
        try:
            ok = self.host.module_mgr.unload_module(target_name)
            return f"✓ 模块 '{target_name}' 已卸载" if ok else f"✗ 卸载失败"
        except Exception as e:
            return f"✗ 异常: {e}"

    def _cmd_grant(self, params):
        return "✗ grant: UID 分配器模块需另行实现。请使用 auth 模块的 .grant 命令。"

    def _cmd_revoke(self, params):
        return "✗ revoke: UID 分配器模块需另行实现。请使用 auth 模块的 .revoke 命令。"

    def _cmd_ulist(self, params):
        loaded = self.host.module_mgr._loaded_modules
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
        return "✗ .exec 功能暂未实现。"

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

    def _cmd_help(self, params):
        return (
            "══════ CMD 控制台 ══════\n"
            ".kill --name <模块> [--mode graceful|force|hard] --confirm yes  卸载模块\n"
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
    """CMD 交互式命令会话模块"""

    name = "kernel_cmds"
    tier = 0
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
        try:
            host = self._root_services.get("_host")
        except Exception:
            host = None
        if host is None:
            await ctx.reply("✗ 框架主机引用不可用")
            return
        self._sessions[ctx.user_id] = CmdSession(
            host,
            ctx,
        )
        await ctx.reply("CMD 会话已启动。输入 .help 查看命令，.exit 退出。")

    @listen("GroupMessageEvent", priority=50)
    async def _on_cmd_input(self, event):
        session = self._sessions.get(event.user_id)
        if session is None:
            return
        if session.is_timed_out():
            del self._sessions[event.user_id]
            await self.message.send_group(event.group_id, "CMD 会话已超时自动关闭。")
            return
        reply = session.handle(event.message)
        event.handled = True
        await self.message.send_group(event.group_id, reply)
        if session.state == SessionState.EXITED:
            del self._sessions[event.user_id]


def can_enter_cmd(caller_uid: int, admin_uids: Optional[List[int]] = None) -> bool:
    if caller_uid == UID_ROOT:
        return True
    if admin_uids and caller_uid in admin_uids:
        return True
    return False
