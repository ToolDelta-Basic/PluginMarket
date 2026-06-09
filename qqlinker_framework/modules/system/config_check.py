"""配置检查与统一入口模块 — .配置 命令路由器

启动时检查核心配置状态，在终端高亮提示未配置项。

命令:
  .配置            → 检查全部核心配置 + 报告问题
  .配置 向导        → 交互式配置引导
  .配置 修复 <群号>  → 修复指定群子配置 (委托 config_repair)
  .配置 状态        → 查看所有群子配置状态 (委托 config_repair)
  .配置 预览 <群号> <节名> → 预览某群某节配置 (委托 config_repair)
"""
import asyncio
import json
import logging
import os
import re
import socket
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.services import UID_NOBODY

_log = logging.getLogger(__name__)

# ── 核心配置项定义 ──
CORE_CONFIGS: List[Tuple[str, Any, str, str]] = [
    ("网络连接.地址", "ws://127.0.0.1:3001",
     "OneBot WebSocket 连接地址",
     "配置位置: 核心.json → 网络连接.地址\n格式: ws://IP:端口"),
    ("网络连接.令牌", "",
     "OneBot 访问令牌 (Token)",
     "配置位置: 安全.json → 网络连接.令牌\n在 NapCat/LLOneBot 面板中查看"),
]


async def _check_ws(address: str, timeout: float = 3.0) -> Tuple[bool, str]:
    """TCP 握手检查 WebSocket 地址是否可达。"""
    try:
        parsed = re.match(r'wss?://([^:/]+)(?::(\d+))?(/.*)?', address)
        if not parsed:
            return False, f"地址格式错误: {address}"
        host = parsed.group(1)
        default_port = 443 if address.startswith("wss") else 80
        port = int(parsed.group(2) or default_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            return True, f"{host}:{port} 可达"
        return False, f"{host}:{port} 无法连接 (错误码 {result})"
    except Exception as e:
        return False, str(e)


class ConfigRouter(Module):
    """配置统一入口模块。"""

    name = "config_router"
    tier = 100
    version = (1, 0, 0)
    required_services = ["config", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)

    async def on_init(self):
        """注册命令 + 启动时检查核心配置。"""
        # 启动时高亮提示
        await self._startup_check()

    async def _startup_check(self):
        """启动时检查核心配置，在终端和日志中输出高亮报告。"""
        issues: List[str] = []
        for path, default, _, help_text in CORE_CONFIGS:
            val = self.config.get(path, default)
            is_empty = val is None or val == "" or (isinstance(val, list) and not val)
            if is_empty and default != "":
                issues.append(f"  ❌ {path} — {help_text.split(chr(10))[0]}")

        if issues:
            msg = (
                "\n╔══════════════════════════════════════════════╗\n"
                "║  ⚠️ QQLinker 核心配置未完成！              ║\n"
                "║                                            ║\n"
            )
            for issue in issues:
                msg += f"║ {issue:<42s} ║\n"
            msg += (
                "║                                            ║\n"
                "║  发送 .配置 检查并修复配置问题            ║\n"
                "║  或编辑 data/配置/ 目录下的 JSON 文件    ║\n"
                "╚══════════════════════════════════════════════╝\n"
            )
            # 终端输出 (stderr 确保可见)
            print(msg, file=sys.stderr)
            _log.warning("核心配置未完成，共 %d 项需要设置。发送 .配置 开始配置。", len(issues))
        else:
            _log.info("核心配置检查通过 ✅")

    # ═══════════════════════════════════════════════════════════
    # .配置 统一入口
    # ═══════════════════════════════════════════════════════════

    @command("配置", description="配置管理 (检查/修复/预览/状态/向导)")
    async def _cmd_config(self, ctx):
        args = ctx.args if ctx.args else []
        if not args:
            await self._do_check(ctx)
            return

        sub = args[0]
        if sub == "向导":
            await self._do_wizard(ctx)
        elif sub == "修复":
            await self._delegate_repair(ctx)
        elif sub == "状态":
            await self._delegate_status(ctx)
        elif sub == "预览":
            await self._delegate_preview(ctx)
        else:
            await ctx.reply(
                "📋 配置命令:\n"
                "  配置             → 检查核心配置\n"
                "  配置 向导         → 交互式引导\n"
                "  配置 修复 <群号>   → 修复群子配置\n"
                "  配置 状态         → 所有群配置状态\n"
                "  配置 预览 <群> <节> → 预览群配置节")

    async def _do_check(self, ctx):
        """.配置 — 完整检查。"""
        lines = ["🔍 配置检查报告\n"]
        issues = []

        for path, default, desc, help_text in CORE_CONFIGS:
            val = self.config.get(path, default)
            is_empty = val is None or val == "" or (isinstance(val, list) and not val)
            is_default = val == default

            if is_empty and default != "":
                issues.append(f"❌ {path} — 未设置\n   {help_text}")
            elif is_default:
                lines.append(f"⚠️ {path} = {self._fmt(val)} (默认)\n   {help_text}")
            else:
                lines.append(f"✅ {path} = {self._fmt(val)}")

        # 网络检查 (不阻塞, 超时 5s)
        ws_addr = self.config.get("网络连接.地址", "ws://127.0.0.1:3001")
        try:
            ws_ok, ws_msg = await asyncio.wait_for(_check_ws(ws_addr), timeout=5.0)
            lines.append(f"{'✅' if ws_ok else '❌'} WebSocket — {ws_msg}")
        except asyncio.TimeoutError:
            lines.append("⏳ WebSocket — 检查超时")

        api_key = self.config.get("AI助手.API密钥", "")
        if api_key and len(api_key) > 5:
            api_addr = self.config.get("AI助手.API地址", "https://api.deepseek.com/v1")
            try:
                api_ok, api_msg = await asyncio.wait_for(
                    _check_http_api(api_addr, api_key), timeout=8.0
                )
                lines.append(f"{'✅' if api_ok else '❌'} LLM API — {api_msg}")
            except asyncio.TimeoutError:
                lines.append("⏳ LLM API — 检查超时")
        else:
            issues.append("❌ AI助手.API密钥 — 未设置\n   配置位置: 安全.json → AI助手.API密钥")

        if issues:
            lines.append(f"\n🚨 {len(issues)} 项需要立即处理:")
            lines.extend(issues)

        text = "\n".join(lines)
        if len(text) > 2000:
            text = text[:1990] + "...\n(截断)"
        await ctx.reply(text)

    async def _do_wizard(self, ctx):
        await ctx.reply(
            "📋 配置向导\n\n"
            "编辑 data/配置/ 目录下的 JSON 文件:\n"
            "  核心.json  → 网络连接\n"
            "  安全.json  → 令牌/密钥\n"
            "  管理.json  → 模型/转发/模块\n\n"
            "修改后发送 配置 验证。"
        )

    async def _delegate_repair(self, ctx):
        """委托给 config_repair 模块的修复功能。"""
        repair_mod = self._find_module("config_repair")
        if repair_mod:
            await repair_mod._cmd_repair(ctx)
        else:
            await ctx.reply("config_repair 模块未加载")

    async def _delegate_status(self, ctx):
        repair_mod = self._find_module("config_repair")
        if repair_mod:
            await repair_mod._cmd_status(ctx)
        else:
            await ctx.reply("config_repair 模块未加载")

    async def _delegate_preview(self, ctx):
        repair_mod = self._find_module("config_repair")
        if repair_mod:
            await repair_mod._cmd_preview(ctx)
        else:
            await ctx.reply("config_repair 模块未加载")

    def _find_module(self, name: str):
        """查找已加载的模块实例。"""
        try:
            mgr = self.services.try_get("command")
            if mgr and hasattr(mgr, 'host') and hasattr(mgr.host, 'module_mgr'):
                return mgr.host.module_mgr._loaded_modules.get(name)
        except Exception:
            pass
        return None

    @staticmethod
    def _fmt(val) -> str:
        if isinstance(val, str) and len(val) > 30:
            return val[:12] + "…" + val[-8:]
        if isinstance(val, list) and len(val) > 3:
            return str(val[:3])[:-1] + ", …]"
        return str(val)
