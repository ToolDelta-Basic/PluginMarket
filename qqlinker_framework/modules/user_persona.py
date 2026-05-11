"""用户自定义AI人设模块 —— 提供 .设定 / .清除人设 命令，并向服务容器注册 persona 服务。"""
import json
import os
from ..core.module import Module
from ..core.decorators import command


class UserPersonaService:
    """用户人设持久化服务。"""

    def __init__(self, data_path: str):
        self._file = os.path.join(data_path, "personas.json")
        self._personas: dict[str, str] = {}
        self._load()

    def _load(self):
        """从文件加载人设数据。"""
        if os.path.exists(self._file):
            with open(self._file, "r", encoding="utf-8") as f:
                self._personas = json.load(f)
        else:
            self._personas = {}

    def _save(self):
        """保存人设数据到文件。"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._personas, f, ensure_ascii=False, indent=2)

    def get_persona(self, user_id: int) -> str:
        """获取用户人设，若未设定则返回空字符串。"""
        return self._personas.get(str(user_id), "")

    def set_persona(self, user_id: int, persona: str):
        """设定用户人设，自动持久化。"""
        self._personas[str(user_id)] = persona
        self._save()

    def clear_persona(self, user_id: int):
        """清除用户人设，自动持久化。"""
        self._personas.pop(str(user_id), None)
        self._save()


class UserPersonaModule(Module):
    """人设管理模块，暴露 persona 服务。"""

    name = "user_persona"
    version = (1, 0, 0)
    required_services = ["config", "message"]

    async def on_init(self):
        """实例化服务，注册到容器，绑定命令。"""
        # 使用模块专属数据目录
        module_data_dir = self.get_data_dir()
        persona_service = UserPersonaService(module_data_dir)
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
        """处理 .设定 命令，保存用户人设。"""
        persona = " ".join(ctx.args) if ctx.args else ""
        if not persona:
            await ctx.reply("请提供人设描述，例如：.设定 我喜欢编程")
            return
        if len(persona) > 200:
            await ctx.reply("人设描述不能超过200字")
            return
        svc = self.services.get("persona")
        svc.set_persona(ctx.user_id, persona)
        await ctx.reply(f"已设定你的人设：{persona}")

    @command(".清除人设")
    async def _cmd_clear(self, ctx):
        """处理 .清除人设 命令，移除用户人设。"""
        svc = self.services.get("persona")
        svc.clear_persona(ctx.user_id)
        await ctx.reply("已清除你的人设")
