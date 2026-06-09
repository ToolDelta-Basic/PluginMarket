"""帮助命令模块，提供自动生成的命令列表，支持分页浏览与超时自动关闭。

v2.1 — 锁外 I/O + 完整事件控制 + 防重入强化
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from ...core.module import Module
from ...core.kernel.decorators import command, listen
from ...core.kernel.services import UID_NOBODY

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

PAGE_SIZE = 8
SESSION_TIMEOUT = 120
CLEANUP_INTERVAL = 60  # 后台清理间隔（秒）


class HelpModule(Module):
    """提供 .帮助 命令，分页列出所有可用命令及其描述。

    v2.1 改进:
      - 全锁翻页状态机：所有 _sessions 的读写/删除锁定在单一块内
      - 防重入：同一用户不能同时有两个帮助会话
      - 锁内只做 session 状态变更，send_group 移到锁外（防 I/O 持锁）
      - event.handled 在锁外设置，确保路由层识别已处理事件
      - 超时检查在锁内完成（防 TOCTOU）
    """

    name = "help"
    tier = 300  # TIER_APP
    version = (2, 1, 0)
    required_services = ["command", "message", "config"]

    default_config = {
        "管理员": {
            "管理员QQ": [0]
        }
    }

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        # 翻页会话：user_id -> {
        #     "lines": list, "current": int,
        #     "total": int, "last_active": float
        # }
        self._sessions: Dict[int, dict] = {}
        # 会话锁：保护 _sessions 的所有并发访问
        self._session_lock = asyncio.Lock()
        # 后台清理任务
        self._cleanup_task: Optional[asyncio.Task] = None

    async def on_init(self):
        """注册 .帮助 命令。"""
        self.register_command(
            ".帮助", self._cmd_help,
            description="显示命令帮助（支持翻页）",
        )

    async def on_start(self):
        """启动后台过期会话清理任务。"""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def on_stop(self):
        """停止后台清理任务。"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self):
        """Layer 4: 后台被动清理过期 session（60s 间隔）。

        不删除正在活跃使用的 session（last_active 检查）。
        """
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
                now = time.time()
                async with self._session_lock:
                    expired = [
                        uid
                        for uid, session in self._sessions.items()
                        if now - session.get("last_active", 0) > SESSION_TIMEOUT
                    ]
                    for uid in expired:
                        self._sessions.pop(uid, None)
                if expired:
                    _logger.debug("后台清理: 移除 %d 个过期帮助会话", len(expired))
            except asyncio.CancelledError:
                break
            except Exception:
                _logger.exception("帮助会话后台清理异常")

    @command(".帮助")
    async def _cmd_help(self, ctx):
        """生成帮助页面并发送第一页，若多页则启动翻页会话。

        防重入：同一用户不能同时有两个帮助会话。
        """
        # ── 防重入检查 + 会话创建在一个锁块内完成（消除 TOCTOU） ──
        is_admin = self._is_admin(ctx.user_id)
        user_uid = self._get_user_uid(ctx.user_id)
        all_lines = self._build_command_lines(is_admin, user_uid)
        if not all_lines:
            await ctx.reply("当前没有任何可用命令。")
            return

        total_pages = (len(all_lines) - 1) // PAGE_SIZE + 1
        page_lines = all_lines[:PAGE_SIZE]
        msg = self._format_page(page_lines, 1, total_pages)

        if total_pages > 1:
            # 防重入检查 + 会话创建合并在一个锁块内
            async with self._session_lock:
                if ctx.user_id in self._sessions:
                    await ctx.reply(
                        "你已有帮助菜单进行中，请先输入 q 退出或等待超时。"
                    )
                    return
                self._sessions[ctx.user_id] = {
                    "lines": all_lines,
                    "current": 1,
                    "total": total_pages,
                    "last_active": time.time(),
                }
            await ctx.reply(msg)
        else:
            await ctx.reply(msg)

    @listen("GroupMessageEvent", priority=-20)
    async def _on_group_msg(self, event):
        """检测翻页指令，处理翻页或退出。

        关键设计：
          - 所有 _sessions 的读写/删除全在锁内（单一 async with 块）
          - 状态变更（pop / current / last_active）在锁内完成
          - 消息发送在锁外（避免 I/O 持锁阻塞其他用户）
          - event.handled 在锁外设置（信号路由层该事件已处理）
        """
        user_id = event.user_id
        text = event.message.strip() if event.message else ""

        # 快速过滤：非导航字符直接跳过（避免锁获取开销）
        if text not in ("+", "-", "q"):
            return

        # ── Layer 1: 全锁覆盖的翻页状态机 ──
        # 锁内：读 session → 判断 → 修改/删除 → 构建响应文本
        # 锁外：发送消息 + 设置 event.handled
        send_msg: Optional[str] = None

        async with self._session_lock:
            session = self._sessions.get(user_id)
            if session is None:
                # 没有活动会话，不拦截该事件（让路由层正常处理 q 等消息）
                return

            now = time.time()
            last_active = session.get("last_active", 0)

            # 超时检查（锁内，防 TOCTOU）
            if now - last_active > SESSION_TIMEOUT:
                self._sessions.pop(user_id, None)
                send_msg = "帮助会话已超时自动关闭。"
            elif text == "q":
                self._sessions.pop(user_id, None)
                send_msg = "帮助菜单已关闭。"
            elif text == "+":
                new_page = min(session["current"] + 1, session["total"])
                if new_page != session["current"]:
                    session["current"] = new_page
                    session["last_active"] = now
                    start = (new_page - 1) * PAGE_SIZE
                    page_lines = list(
                        session["lines"][start : start + PAGE_SIZE]
                    )
                    send_msg = self._format_page(
                        page_lines, new_page, session["total"]
                    )
                else:
                    # 已在最后一页，刷新活跃时间
                    session["last_active"] = now
            else:  # text == "-"
                new_page = max(session["current"] - 1, 1)
                if new_page != session["current"]:
                    session["current"] = new_page
                    session["last_active"] = now
                    start = (new_page - 1) * PAGE_SIZE
                    page_lines = list(
                        session["lines"][start : start + PAGE_SIZE]
                    )
                    send_msg = self._format_page(
                        page_lines, new_page, session["total"]
                    )
                else:
                    # 已在第一页，刷新活跃时间
                    session["last_active"] = now

        # ── 锁外：发送消息 + 标记事件已处理 ──
        if send_msg is not None:
            # event.handled 必须在 send_group 之前设置，确保路由层
            # 和其他监听器（如日志/转发模块）跳过该事件
            event.handled = True
            await self.message.send_group(event.group_id, send_msg)

    def _build_command_lines(self, is_admin: bool,
                             user_uid: int = 400) -> List[str]:
        """构建当前用户可见的所有命令行（按 UID 过滤）。"""
        lines: List[str] = []
        all_commands = self.command.get_group_commands()
        for cmd_info in all_commands:
            if cmd_info.get("op_only", False) and not is_admin:
                continue
            min_uid = cmd_info.get("min_uid", 400)
            if min_uid > 0 and user_uid > 0 and user_uid > min_uid:
                continue
            trigger = cmd_info["trigger"]
            desc = cmd_info.get("description", "")
            hint = cmd_info.get("argument_hint", "")
            line = f"• {trigger}"
            if hint:
                line += f" {hint}"
            if desc:
                line += f" —— {desc}"
            if cmd_info.get("op_only"):
                line += " (管理员)"
            if min_uid > 0 and min_uid < 400:
                tier_names = {1: "kernel", 100: "daemon", 200: "service"}
                tier = tier_names.get(min_uid, f"uid≤{min_uid}")
                line += f" ({tier})"
            lines.append(line)
        return lines

    @staticmethod
    def _format_page(
        page_lines: List[str], current: int, total: int
    ) -> str:
        """格式化单页帮助文本。"""
        header = f"📋 可用命令列表 ({current}/{total})"
        body = "\n".join(page_lines) if page_lines else "(空)"
        footer = "输入 + 下一页，- 上一页，q 结束"
        return f"{header}\n{body}\n{footer}"

    def _is_admin(self, user_id: int) -> bool:
        """判断用户是否为管理员。"""
        try:
            admin_list = self.config.get("管理员.管理员QQ", [])
            return user_id in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False

    def _get_user_uid(self, user_id: int) -> int:
        """查询用户的 UID，默认为 400(nobody)。"""
        try:
            return self.services.get("uid_lookup")(user_id)
        except Exception:
            return UID_NOBODY
