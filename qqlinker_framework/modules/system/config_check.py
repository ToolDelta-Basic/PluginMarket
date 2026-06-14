"""配置检查 + 模板引擎集成模块。

启动时引导用户选择模板（保守/默认/激进/调试）。
命令: 配置 [检查|模板|向导|修复|状态|预览]
"""
import asyncio
import logging
import os
import re
import socket
import sys
import time
from typing import Any, List, Tuple

from ...core.module import Module
from ...core.kernel.decorators import command

_log = logging.getLogger(__name__)

# 核心互通配置（仅这两项是必需的）
CORE_CONFIGS: List[Tuple[str, Any, str, str]] = [
    ("网络连接.地址", "ws://127.0.0.1:3001",
     "OneBot WebSocket 连接地址",
     "核心.json → 网络连接.地址\n格式: ws://IP:端口"),
    ("网络连接.令牌", "",
     "OneBot 访问令牌 (Token)",
     "安全.json → 网络连接.令牌\n在 NapCat/LLOneBot 面板中查看"),
]


async def _check_ws(address: str, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        parsed = re.match(r'wss?://([^:/]+)(?::(\d+))?(/.*)?', address)
        if not parsed:
            return False, f"地址格式错误: {address}"
        host = parsed.group(1)
        port = int(parsed.group(2) or (443 if address.startswith("wss") else 80))
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
    """配置路由模块。"""
    background = True
    name = "config_router"
    tier = 100
    version = (1, 0, 0)
    required_services = ["config", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._template_engine = None

    async def on_init(self):
        await self._startup_check()

    async def _startup_check(self):
        """启动时检查：如果未选择模板则引导，否则检查配置。"""
        try:
            from .template_engine import TemplateEngine
            data_dir = self._get_data_dir()
            self._template_engine = TemplateEngine(data_dir, self.config)
            active = self._template_engine.check_active()

            if active is None:
                self._print_banner("🎉 欢迎使用 QQLinker！",
                    "发送 配置 模板 选择并应用配置模板：",
                    "  保守 — 仅核心互通",
                    "  默认 — 推荐的默认配置",
                    "  激进 — 全部功能 (高消耗)",
                    "  调试 — 开发测试用",
                    "",
                    "或编辑 data/配置/ 目录下的 JSON 文件")
                _log.info("首次启动: 发送 配置 模板 选择配置模板")
                return

            if not active["ok"]:
                req = len(active["missing_required"])
                priv = len(active["missing_private"])
                self._print_banner(
                    f"⚠️ 配置模板 '{active['template']}' 未完成！",
                    f"{req} 项必填 + {priv} 项隐私需设置",
                    "发送 配置 检查并修复配置问题")
                _log.warning("模板 %s 有 %d 项未完成", active["template"], req + priv)
                return

        except Exception as e:
            _log.debug("模板引擎跳过: %s", e)

        # 回退：基础核心检查
        issues = []
        for path, default, _, help_text in CORE_CONFIGS:
            val = self.config.get(path, default)
            if val is None or val == "" or (isinstance(val, list) and not val):
                if default != "":
                    issues.append(f"  ❌ {path} — {help_text.split(chr(10))[0]}")

        if issues:
            msg = "\n╔══════════════════════════════════════════════╗\n"
            msg += "║  ⚠️ QQLinker 核心配置未完成！              ║\n"
            msg += "║                                            ║\n"
            for issue in issues:
                msg += f"║ {issue:<42s} ║\n"
            msg += "║                                            ║\n"
            msg += "║  发送 配置 检查并修复配置问题            ║\n"
            msg += "║  或编辑 data/配置/ 目录下的 JSON 文件    ║\n"
            msg += "╚══════════════════════════════════════════════╝\n"
            print(msg, file=sys.stderr)
            _log.warning("核心配置未完成，发送 配置 开始配置")

    # ═══════════════════════════════════════════════════════════
    # 配置 统一入口
    # ═══════════════════════════════════════════════════════════

    @command(".配置", description="配置管理 (检查/模板/修复/预览/状态/向导)")
    async def _cmd_config(self, ctx):
        args = ctx.args if ctx.args else []
        if not args:
            await self._do_check(ctx)
        elif args[0] == "模板":
            await self._do_template(ctx)
        elif args[0] == "向导":
            await self._do_wizard(ctx)
        elif args[0] == "修复":
            await self._delegate_repair(ctx)
        elif args[0] == "状态":
            await self._delegate_status(ctx)
        elif args[0] == "预览":
            await self._delegate_preview(ctx)
        else:
            await ctx.reply(
                "📋 配置命令:\n"
                "  配置               → 检查核心配置\n"
                "  配置 模板 [名称]    → 查看/切换配置模板\n"
                "  配置 向导           → 交互式引导\n"
                "  配置 修复 <群号>    → 修复群子配置\n"
                "  配置 状态           → 所有群配置状态\n"
                "  配置 预览 <群> <节>  → 预览群配置节")

    async def _do_check(self, ctx):
        lines = ["🔍 配置检查报告\n"]
        issues = []

        for path, default, desc, help_text in CORE_CONFIGS:
            val = self.config.get(path, default)
            is_empty = val is None or val == "" or (isinstance(val, list) and not val)
            is_default = val == default

            if is_empty and default != "":
                issues.append(f"❌ {path} — 未设置\n   {help_text}")
            elif is_default:
                lines.append(f"⚠️ {path} = {val} (默认)\n   {help_text}")
            else:
                lines.append(f"✅ {path} = {_fmt(val)}")

        try:
            ws_addr = self.config.get("网络连接.地址", "ws://127.0.0.1:3001")
            ws_ok, ws_msg = await asyncio.wait_for(_check_ws(ws_addr), timeout=5.0)
            lines.append(f"{'✅' if ws_ok else '❌'} WebSocket — {ws_msg}")
        except asyncio.TimeoutError:
            lines.append("⏳ WebSocket — 检查超时")

        if issues:
            lines.append(f"\n🚨 {len(issues)} 项需要处理:")
            lines.extend(issues)

        # 模板状态
        if self._template_engine:
            active = self._template_engine.check_active()
            if active:
                lines.append(f"\n当前模板: {active['template']} ({active['type']})")
                if active["ok"]:
                    lines.append("  ✅ 模板校验通过")
                else:
                    req = active["missing_required"]
                    priv = active["missing_private"]
                    if req:
                        lines.append(f"  ❌ {len(req)} 项必填缺失")
                        for r in req:
                            lines.append(f"    {r['desc']}")
                    if priv:
                        lines.append(f"  🔒 {len(priv)} 项隐私需手动设置")

        text = "\n".join(lines)
        if len(text) > 2000:
            text = text[:1990] + "...\n(截断)"
        await ctx.reply(text)

    async def _do_template(self, ctx):
        """配置 模板 — 查看/切换配置模板。"""
        if not self._template_engine:
            await ctx.reply("模板引擎未初始化")
            return

        args = ctx.args[1:] if len(ctx.args) > 1 else []
        if not args:
            # 列出可用模板
            active_name = "?"
            active_file = os.path.join(self._get_data_dir(), ".active_template")
            if os.path.isfile(active_file):
                with open(active_file) as f:
                    active_name = f.read().strip()

            lines = ["📋 可用配置模板\n"]
            for name in self._template_engine.list_builtin():
                mark = " ← 当前" if name == active_name else ""
                tmpl = self._template_engine.get_template(name)
                desc = tmpl.get("description", "")[:50] if tmpl else ""
                lines.append(f"  {name}{mark}\n    {desc}")
            for ext in self._template_engine.list_external():
                mark = " ← 当前" if ext.get("name") == active_name else ""
                lines.append(
                    f"  📦 {ext['name']} v{ext['version']} "
                    f"({ext['file']}){mark}"
                )
            lines.append("\n发送 配置 模板 <名称> 切换模板")
            await ctx.reply("\n".join(lines))
            return

        target = args[0]
        ok, msg = self._template_engine.switch(target)
        await ctx.reply(msg)

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
        if not self._find_module("config_repair"):
            await ctx.reply("config_repair 模块未加载")
            return
        try:
            await self.gatekeeper.call("模块.调用",
                "config_repair", "_cmd_repair", [ctx])
        except Exception as e:
            await ctx.reply(f"调用失败: {e}")

    async def _delegate_status(self, ctx):
        if not self._find_module("config_repair"):
            await ctx.reply("config_repair 模块未加载")
            return
        try:
            await self.gatekeeper.call("模块.调用",
                "config_repair", "_cmd_status", [ctx])
        except Exception as e:
            await ctx.reply(f"调用失败: {e}")

    async def _delegate_preview(self, ctx):
        if not self._find_module("config_repair"):
            await ctx.reply("config_repair 模块未加载")
            return
        try:
            await self.gatekeeper.call("模块.调用",
                "config_repair", "_cmd_preview", [ctx])
        except Exception as e:
            await ctx.reply(f"调用失败: {e}")

    def _find_module(self, name: str) -> bool:
        """通过 Gatekeeper bridge 安全查找模块是否加载。"""
        try:
            return self.gatekeeper.call("模块.已加载", name) is True
        except Exception:
            return False

    def _get_loaded_module(self, name: str):
        """获取已加载模块的引用（Gatekeeper 安全访问）。"""
        if not self._find_module(name):
            return None
        return True  # 模块存在，调用方通过 gatekeeper.模块.调用 执行方法

    def _get_data_dir(self) -> str:
        try:
            return self.config.get_data_dir() or "."
        except Exception:
            return "."

    @staticmethod
    def _print_banner(title: str, *lines):
        msg = "\n╔══════════════════════════════════════════════╗\n"
        msg += f"║  {title:<42s} ║\n"
        msg += "║                                            ║\n"
        for line in lines:
            msg += f"║  {line:<42s} ║\n"
        msg += "╚══════════════════════════════════════════════╝\n"
        print(msg, file=sys.stderr)


def _fmt(val) -> str:
    if isinstance(val, str) and len(val) > 30:
        return val[:12] + "…" + val[-8:]
    if isinstance(val, list) and len(val) > 3:
        return str(val[:3])[:-1] + ", …]"
    return str(val)
