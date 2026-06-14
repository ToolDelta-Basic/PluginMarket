"""群级AI人设模块 — 提供 .群设 / .清除群设 命令，绑定到群聊而非用户。"""
import json
import os
import logging
from ...core.module import Module
from ...core.kernel.decorators import command

_logger = logging.getLogger(__name__)


class GroupPersonaService:
    """群级人设持久化服务。每个人设绑定到 group_id 而非 user_id。"""

    def __init__(self, data_path: str):
        self._file = os.path.join(data_path, "group_personas.json")
        self._personas: dict[str, str] = {}
        self._load()

    def _load(self):
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._personas = json.load(f)
            except Exception:
                self._personas = {}

    def _save(self):
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._personas, f, ensure_ascii=False, indent=2)

    def get_persona(self, group_id: int) -> str:
        """获取群聊人格配置。"""
        val = self._personas.get(str(group_id), "")
        _logger.debug("[GroupPersona] 读取人设 group_id=%d -> '%s'", group_id, val)
        return val

    def set_persona(self, group_id: int, persona: str):
        """设置群聊人格配置。"""
        _logger.debug("[GroupPersona] 写入人设 group_id=%d -> '%s'", group_id, persona)
        self._personas[str(group_id)] = persona
        self._save()

    def clear_persona(self, group_id: int):
        """清除群聊人格配置。"""
        _logger.debug("[GroupPersona] 清除人设 group_id=%d", group_id)
        self._personas.pop(str(group_id), None)
        self._save()


class GroupPersonaModule(Module):
    """群级人设管理模块。"""

    name = "group_persona"
    tier = 300
    version = (1, 0, 0)
    dependencies = ["ai_core"]
    required_services = ["config", "message"]

    def create_exports(self) -> dict:
        """创建模块导出。"""
        data_dir = self.data_dir
        persona_service = GroupPersonaService(data_dir)
        return {"group_persona": persona_service}

    async def on_init(self):
        pass

    @command(".群设")
    async def _cmd_set(self, ctx):
        """.群设 <描述>  — 为当前群设定 AI 人设。
        .群设 清除   — 清除当前群的人设。
        """
        args = ctx.args
        if not args:
            svc = self.services.get("group_persona")
            current = svc.get_persona(ctx.group_id)
            if current:
                await ctx.reply(f"当前群人设: {current}\n\n用法: .群设 <描述> 或 .群设 清除")
            else:
                await ctx.reply("当前群未设人设。\n用法: .群设 <描述>")
            return

        svc = self.services.get("group_persona")

        if args[0] == "清除":
            svc.clear_persona(ctx.group_id)
            await ctx.reply("已清除当前群的人设")
            return

        persona = " ".join(args)
        if len(persona) > 200:
            await ctx.reply("人设描述不能超过200字")
            return

        svc.set_persona(ctx.group_id, persona)

        try:
            ai_core = self.services.get("ai_core")
            await ai_core.clear_group_history(ctx.group_id)
            await ctx.reply(
                f"已设定本群人设：{persona}\nAI 将在下一次回复中确认此角色。")
        except KeyError:
            await ctx.reply(f"已设定本群人设：{persona}（但 AI 核心未就绪）")
