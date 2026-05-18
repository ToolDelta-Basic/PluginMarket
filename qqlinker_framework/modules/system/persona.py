"""用户自定义AI人设模块 —— 提供 .设定 / .清除人设 命令，并向服务容器注册 persona 服务。"""
import json
import os
import secrets
import logging
from ...core.module import Module
from ...core.decorators import command

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)


class UserPersonaService:
    """用户人设持久化服务。"""

    def __init__(self, data_path: str):
        self._file = os.path.join(data_path, "personas.json")
        self._personas: dict[str, str] = {}
        self._load()

    def _load(self):
        """从文件加载人设数据。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._personas = json.load(f)
            except Exception:
                self._personas = {}

    def _save(self):
        """保存人设数据到文件。"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._personas, f, ensure_ascii=False, indent=2)

    def get_persona(self, user_id: int) -> str:
        """获取用户人设，若未设定则返回空字符串。"""
        val = self._personas.get(str(user_id), "")
        _logger.debug("[Persona] 读取人设 user_id=%d -> '%s'", user_id, val)
        return val

    def set_persona(self, user_id: int, persona: str):
        """设定用户人设，自动持久化。"""
        _logger.debug(
            "[Persona] 写入人设 user_id=%d -> '%s'", user_id, persona
        )
        self._personas[str(user_id)] = persona
        self._save()

    def clear_persona(self, user_id: int):
        """清除用户人设，自动持久化。"""
        _logger.debug("[Persona] 清除人设 user_id=%d", user_id)
        self._personas.pop(str(user_id), None)
        self._save()


class UserPersonaModule(Module):
    """人设管理模块，暴露 persona 服务。"""

    name = "user_persona"
    version = (1, 0, 0)
    dependencies = ["ai_core"]        # 确保 AI 核心先加载
    required_services = ["config", "message"]

    async def on_init(self):
        """实例化服务，注册到容器，绑定命令。"""
        data_dir = self.get_data_dir()
        persona_service = UserPersonaService(data_dir)
        self.services.register("persona", persona_service)

        self.register_command(
            ".设定",
            self._cmd_set,
            description="设置你的AI人设，例如：.设定 我是程序员",
            argument_hint="<描述>",
        )
        self.register_command(
            ".清除人设",
            self._cmd_clear,
            description="清除你的AI人设，恢复默认",
        )

    @command(".设定")
    async def _cmd_set(self, ctx):
        """处理 .设定 命令：审核人设、清除记忆、生成令牌并通知 AI 确认。"""
        persona = " ".join(ctx.args) if ctx.args else ""
        if not persona:
            await ctx.reply("请提供人设描述，例如：.设定 我喜欢编程")
            return
        if len(persona) > 200:
            await ctx.reply("人设描述不能超过200字")
            return

        # 审核人设内容
        audit_mgr = None
        try:
            audit_mgr = self.services.get("audit")
        except KeyError:
            pass
        if audit_mgr:
            reason = await audit_mgr.check_message(ctx.user_id, 0, persona)
            if reason:
                await ctx.reply(f"人设包含违规内容：{reason}，已拒绝设置。")
                return

        svc = self.services.get("persona")
        svc.set_persona(ctx.user_id, persona)

        # 获取 ai_core 服务（此时已确保加载顺序）
        try:
            ai_core = self.services.get("ai_core")
            _logger.debug("[Persona] 清除 AI 记忆 user_id=%d", ctx.user_id)
            ai_core.clear_history(ctx.user_id)
            token = secrets.token_hex(4)
            _logger.debug(
                "[Persona] 设置令牌 user_id=%d token=%s",
                ctx.user_id, token,
            )
            ai_core.set_pending_persona_token(ctx.user_id, token)
            await ctx.reply(
                f"已设定你的人设：{persona}\n"
                "AI 将在下一次回复中确认此角色。"
            )
        except KeyError:
            _logger.error("[Persona] ai_core 服务不可用！")
            await ctx.reply(
                f"已设定你的人设：{persona}"
                "（但 AI 核心未就绪，角色可能延迟生效）"
            )

    @command(".清除人设")
    async def _cmd_clear(self, ctx):
        """处理 .清除人设 命令，移除用户人设。"""
        svc = self.services.get("persona")
        svc.clear_persona(ctx.user_id)

        try:
            ai_core = self.services.get("ai_core")
            _logger.debug("[Persona] 清除 AI 记忆 user_id=%d", ctx.user_id)
            ai_core.clear_history(ctx.user_id)
        except KeyError:
            _logger.error("[Persona] ai_core 服务不可用！")

        await ctx.reply("已清除你的人设")
