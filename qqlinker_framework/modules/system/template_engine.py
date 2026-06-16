"""配置模板引擎 — 定义/加载/校验/切换配置模板。

模板是配置节的校验规则载体，不包含实际配置值（隐私节除外）。
隐私节（标记为 private）的值永不读取、永不覆盖，必须由用户手动设置。

模板类型:
  保守   — 最少配置，仅核心互通 (地址+令牌)
  默认   — 推荐默认配置
  激进   — 全部功能启用
  调试   — 开发/测试用，打开调试开关

存储:
  内置模板: core/ipc/templates/ (源码目录)
  外部/市场模板: data/模板/

模板 JSON 结构:
{
  "name": "默认配置",
  "version": "1.0",
  "type": "default",
  "description": "...",
  "sections": {
    "网络连接": {"地址": "required", "令牌": "private"},
    "消息转发": {"链接的群聊": "optional"},
    "AI助手": {"API密钥": "private"}
  }
}
"""
import json
import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

TEMPLATE_TYPES = ("保守", "默认", "激进", "调试")
FIELD_MARKERS = ("required", "optional", "private")

# 数据目录下的模板存储路径
TEMPLATES_DIR = "模板"
BACKUPS_DIR = "模板备份"


# ═══════════════════════════════════════════════════════════
# 内置模板数据
# ═══════════════════════════════════════════════════════════

_BUILTIN_TEMPLATES: Dict[str, dict] = {
    "保守": {
        "name": "保守",
        "version": "1.0",
        "type": "保守",
        "description": "仅核心互通。适合只用群服互通的服主，不开 AI，不接外部服务。",
        "sections": {
            "网络连接": {"地址": "required", "令牌": "private"},
        },
    },
    "默认": {
        "name": "默认",
        "version": "1.0",
        "type": "默认",
        "description": "推荐配置。核心互通 + 消息转发 + 基本模块管理。",
        "sections": {
            "网络连接": {"地址": "required", "令牌": "private"},
            "消息转发": {"链接的群聊": "optional", "游戏到群.是否启用": "optional",
                        "群到游戏.是否启用": "optional"},
            "模块管理": {"禁用模块": "optional", "模式": "optional"},
        },
    },
    "激进": {
        "name": "激进",
        "version": "1.0",
        "type": "激进",
        "description": "全部功能。核心互通 + AI + 转发 + ACG + 主动发言。消耗最大。",
        "sections": {
            "网络连接": {"地址": "required", "令牌": "private"},
            "AI助手": {"API密钥": "private", "API地址": "required",
                      "模型": "optional", "是否启用": "optional"},
            "消息转发": {"链接的群聊": "optional", "游戏到群.是否启用": "optional",
                        "群到游戏.是否启用": "optional"},
            "ACG冷却限制": {"单群每分钟": "optional", "单人每分钟": "optional"},
            "主动发言": {"是否启用": "optional"},
            "模块管理": {"禁用模块": "optional", "模式": "optional"},
        },
    },
    "调试": {
        "name": "调试",
        "version": "1.0",
        "type": "调试",
        "description": "开发/测试用。开调试引擎 + 控制台 + 去重本地模式。",
        "sections": {
            "网络连接": {"地址": "required", "令牌": "private"},
            "调试": {"生产模式禁用": "optional"},
            "去重": {"启用Redis": "optional"},
            "模块管理": {"禁用模块": "optional", "模式": "optional"},
        },
    },
}


# ═══════════════════════════════════════════════════════════
# TemplateEngine
# ═══════════════════════════════════════════════════════════

class TemplateEngine:
    """配置模板引擎：加载、校验、切换。"""

    def __init__(self, data_dir: str, config_mgr):
        self._data_dir = data_dir
        self._templates_dir = os.path.join(data_dir, TEMPLATES_DIR)
        self._backups_dir = os.path.join(data_dir, BACKUPS_DIR)
        self._config_mgr = config_mgr
        os.makedirs(self._templates_dir, exist_ok=True)
        os.makedirs(self._backups_dir, exist_ok=True)

    # ── 加载 ──

    @staticmethod
    def list_builtin() -> List[str]:
        """列出内置模板名称。"""
        return sorted(_BUILTIN_TEMPLATES.keys())

    def list_external(self) -> List[Dict[str, str]]:
        """列出外部模板。"""
        result = []
        if not os.path.isdir(self._templates_dir):
            return result
        for fname in sorted(os.listdir(self._templates_dir)):
            if not fname.endswith('.json'):
                continue
            fp = os.path.join(self._templates_dir, fname)
            try:
                tpl = self._load_file(fp)
                if tpl:
                    result.append({
                        "name": tpl.get("name", fname),
                        "version": tpl.get("version", "?"),
                        "type": tpl.get("type", "?"),
                        "file": fname,
                    })
            except Exception:
                pass
        return result

    def get_template(self, name_or_file: str) -> Optional[dict]:
        """获取模板数据。先查内置，再查外部。"""
        # 内置
        for key, tpl in _BUILTIN_TEMPLATES.items():
            if key == name_or_file or tpl.get("name") == name_or_file:
                return dict(tpl)
        # 外部
        fp = os.path.join(self._templates_dir, name_or_file)
        if os.path.isfile(fp):
            return self._load_file(fp)
        return None

    @staticmethod
    def _load_file(fp: str) -> Optional[dict]:
        """加载模板 JSON 文件。"""
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "name" not in data or "sections" not in data:
                _log.warning("模板文件 %s 缺少 name/sections", fp)
                return None
            if "version" not in data:
                data["version"] = "0.0"
            return data
        except Exception as e:
            _log.warning("加载模板 %s 失败: %s", fp, e)
            return None

    def save_template(self, tpl: dict, filename: str = None) -> str:
        """保存模板到外部目录。"""
        if filename is None:
            filename = f'{tpl["name"]}.json'
        fp = os.path.join(self._templates_dir, filename)
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(tpl, f, ensure_ascii=False, indent=2)
        return fp

    # ── 校验 ──

    def check(self, tpl: dict) -> Dict[str, Any]:
        """校验当前配置是否符合模板。

        Returns:
            {
              "ok": True/False,
              "missing_required": [{"path": "...", "section": "...", "key": "..."}],
              "missing_private": [{"path": "...", "desc": "需要手动设置"}],
              "missing_optional": [...]
            }
        """
        result = {
            "ok": True,
            "template": tpl.get("name", "?"),
            "type": tpl.get("type", "?"),
            "missing_required": [],
            "missing_private": [],
            "missing_optional": [],
        }

        sections = tpl.get("sections", {})
        for section, fields in sections.items():
            for key, marker in fields.items():
                path = f"{section}.{key}"
                val = self._config_mgr.get(path, None)

                if val is None or val == "" or (isinstance(val, list) and not val):
                    entry = {"path": path, "section": section, "key": key}
                    if marker == "private":
                        entry["desc"] = f"🔒 {key} (隐私) — 需要手动设置: 配置 设置 {path} <值>"
                        result["missing_private"].append(entry)
                        result["ok"] = False
                    elif marker == "required":
                        entry["desc"] = f"❌ {key} — 未设置 (必填)"
                        result["missing_required"].append(entry)
                        result["ok"] = False
                    elif marker == "optional":
                        entry["desc"] = f"⚠️ {key} — 未设置 (可选)"
                        result["missing_optional"].append(entry)

        return result

    def check_active(self) -> Optional[Dict[str, Any]]:
        """检查当前激活模板的状态。"""
        # 尝试从保存的激活模板名读取
        active_file = os.path.join(self._data_dir, ".active_template")
        if os.path.isfile(active_file):
            with open(active_file) as f:
                name = f.read().strip()
            tpl = self.get_template(name)
            if tpl:
                return self.check(tpl)
        return None

    # ── 切换 ──

    def switch(self, template_name: str) -> Tuple[bool, str]:
        """切换到指定模板。备份当前配置，应用新模板的非隐私默认值。"""
        tpl = self.get_template(template_name)
        if not tpl:
            return False, f"模板 '{template_name}' 未找到"

        # 备份当前配置
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_fp = os.path.join(
            self._backups_dir,
            f"config_backup_{ts}.json",
        )
        try:
            current_data = dict(self._config_mgr._data)
            with open(backup_fp, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            _log.info("配置已备份到 %s", backup_fp)
        except Exception as e:
            _log.error("配置备份失败: %s", e)

        # 应用新模板的非隐私默认值
        applied = []
        skipped_private = []
        sections = tpl.get("sections", {})
        for section, fields in sections.items():
            for key, marker in fields.items():
                if marker == "private":
                    skipped_private.append(f"{section}.{key}")
                    continue
                path = f"{section}.{key}"
                # 只填充框架已有的配置节（不创建新节）
                existing = self._config_mgr.get(path, "__NONE__")
                if existing == "__NONE__":
                    continue
                # 使用框架默认值
                defaults = self._config_mgr._defaults.get(section, {})
                if key in defaults:
                    self._config_mgr.set(path, defaults[key])
                    applied.append(path)

        # 保存激活模板名
        active_file = os.path.join(self._data_dir, ".active_template")
        with open(active_file, 'w') as f:
            f.write(template_name)

        msg = (
            f"✅ 已切换到模板 '{tpl.get('name')}' (v{tpl.get('version')})\n"
            f"  应用了 {len(applied)} 个默认值\n"
        )
        if skipped_private:
            msg += f"  🔒 {len(skipped_private)} 项隐私配置需要手动设置:\n"
            for sp in skipped_private[:5]:
                msg += f"    配置 设置 {sp} <值>\n"
        msg += f"  备份: {backup_fp}"
        return True, msg

    def save_active(self, name: str):
        """保存当前激活的模板名。"""
        active_file = os.path.join(self._data_dir, ".active_template")
        with open(active_file, 'w') as f:
            f.write(name)


# ═══════════════════════════════════════════════════════════
# TemplateModule — 宿主框架命令
# ═══════════════════════════════════════════════════════════

from ...core.module import Module
from ...core.kernel.decorators import command


class TemplateModule(Module):
    """配置模板模块 — 注册为宿主框架服务，提供统一的模板管理约定。

    命令:
      .模板              → 查看当前模板状态 + 可用列表
      .模板 列表         → 列出所有模板
      .模板 检查         → 检查当前模板完成情况
      .模板 状态         → 显示当前激活模板和完成状态
      .模板 切换 <名称>   → 备份配置并切换到指定模板

    约定:
      其他模块通过 services.get("template") 获取 TemplateEngine 引用。
      TemplateEngine 在 TemplateModule.on_init 中注册到服务容器。
    """

    name = "template"
    mid = 100
    version = (1, 0, 0)
    required_services = ["config"]
    background = True

    async def on_init(self):
        data_dir = self._get_data_dir()
        self._engine = TemplateEngine(data_dir, self.config)
        # 注册为宿主框架服务，其他模块可通过 services.get("template") 获取
        self.services.register("template", self._engine)
        _log.info("模板引擎已注册为服务 'template'")

    @command(".模板", description="配置模板管理 (列表/检查/切换/状态)")
    async def _cmd_template(self, ctx):
        args = ctx.args if ctx.args else []
        if not args:
            await self._cmd_status(ctx)
            return
        sub = args[0]
        if sub == "列表":
            await self._cmd_list(ctx)
        elif sub == "检查":
            await self._cmd_check(ctx)
        elif sub == "状态":
            await self._cmd_status(ctx)
        elif sub == "切换":
            await self._cmd_switch(ctx)
        else:
            await ctx.reply(
                "📋 .模板 <列表|检查|状态|切换> [参数]\n"
                "  列表         — 列出所有模板\n"
                "  检查         — 检查当前模板完成情况\n"
                "  状态         — 显示当前模板状态\n"
                "  切换 <名称>  — 切换模板"
            )

    async def _cmd_list(self, ctx):
        active_name = "?"
        active_file = os.path.join(self._get_data_dir(), ".active_template")
        if os.path.isfile(active_file):
            with open(active_file) as f:
                active_name = f.read().strip()

        lines = ["📋 可用配置模板\n"]
        for name in self._engine.list_builtin():
            mark = " ← 当前" if name == active_name else ""
            tmpl = self._engine.get_template(name)
            desc = tmpl.get("description", "")[:50] if tmpl else ""
            lines.append(f"  {name}{mark}\n    {desc}")
        for ext in self._engine.list_external():
            mark = " ← 当前" if ext.get("name") == active_name else ""
            lines.append(
                f"  📦 {ext['name']} v{ext['version']} "
                f"({ext['file']}){mark}"
            )
        lines.append("\n发送 .模板 切换 <名称> 切换模板")
        await ctx.reply("\n".join(lines))

    async def _cmd_check(self, ctx):
        result = self._engine.check_active()
        if result is None:
            await ctx.reply("未选择模板。使用 .模板 列表 查看可用模板，.模板 切换 <名称> 切换")
            return
        if result["ok"]:
            await ctx.reply(
                f"✅ 模板 '{result['template']}' ({result['type']}) 通过\n"
                f"   所有必填项和隐私项已配置完成"
            )
            return
        lines = [
            f"⚠️ 模板 '{result['template']}' ({result['type']}) 未完成",
            "",
        ]
        for r in result.get("missing_required", []):
            lines.append(f"  ❌ {r['desc']}")
        for r in result.get("missing_private", []):
            lines.append(f"  🔒 {r['desc']}")
        await ctx.reply("\n".join(lines))

    async def _cmd_status(self, ctx):
        result = self._engine.check_active()
        if result is None:
            await ctx.reply(
                "📋 未选择配置模板\n\n"
                "使用 .模板 列表 查看可用模板\n"
                "使用 .模板 切换 <名称> 选择模板"
            )
            return
        status_icon = "✅" if result["ok"] else "⚠️"
        lines = [
            f"{status_icon} 当前模板: {result['template']} ({result['type']})",
        ]
        req_n = len(result.get("missing_required", []))
        priv_n = len(result.get("missing_private", []))
        opt_n = len(result.get("missing_optional", []))
        parts = []
        if req_n:
            parts.append(f"{req_n} 必填缺失")
        if priv_n:
            parts.append(f"{priv_n} 隐私需设置")
        if opt_n:
            parts.append(f"{opt_n} 可选未设")
        if parts:
            lines.append(f"  {' · '.join(parts)}")
        else:
            lines.append("  全部配置完成 ✓")
        lines.append("\n.模板 检查 → 查看详情")
        await ctx.reply("\n".join(lines))

    async def _cmd_switch(self, ctx):
        args = ctx.args[1:] if len(ctx.args) > 1 else []
        if not args:
            await ctx.reply(
                "用法: .模板 切换 <名称>\n\n"
                "先使用 .模板 列表 查看可用模板"
            )
            return
        target = args[0]
        ok, msg = self._engine.switch(target)
        await ctx.reply(msg)

    def _get_data_dir(self) -> str:
        try:
            return self.config.get_data_dir() or "."
        except Exception:
            return "."
