"""用户自定义AI人设模块 —— 提供 .设定 / .清除人设 命令，并向服务容器注册 persona 服务。"""
import json
import os
import secrets
import time
import logging
from typing import Optional
from ...core.module import Module
from ...core.decorators import command

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)


class UserPersonaService:
    """用户人设持久化服务。"""

    def __init__(self, data_path: str):
        self._file = os.path.join(data_path, "personas.json")
        self._pending_file = os.path.join(data_path, "pending_personas.json")
        self._personas: dict[str, str] = {}
        self._pending: dict[str, dict] = {}
        self._load()

    def _load(self):
        """从文件加载人设数据与待审数据。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._personas = json.load(f)
            except Exception:
                self._personas = {}
        if os.path.exists(self._pending_file):
            try:
                with open(self._pending_file, "r", encoding="utf-8") as f:
                    self._pending = json.load(f)
            except Exception:
                self._pending = {}

    def _save(self):
        """保存人设数据到文件。"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._personas, f, ensure_ascii=False, indent=2)

    def _save_pending(self):
        """保存待审人设到文件。"""
        with open(self._pending_file, "w", encoding="utf-8") as f:
            json.dump(self._pending, f, ensure_ascii=False, indent=2)

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

    # ── 待审管理 ──

    def add_pending(self, user_id: int, persona: str):
        """将人设申请加入待审列表。"""
        key = str(user_id)
        self._pending[key] = {
            "user_id": user_id,
            "persona_text": persona,
            "submitted_at": time.time(),
        }
        self._save_pending()
        _logger.debug("[Persona] 待审添加 user_id=%d", user_id)

    def get_pending_list(self) -> list[dict]:
        """获取所有待审人设列表。"""
        return list(self._pending.values())

    def approve_pending(self, user_id: int) -> Optional[str]:
        """通过待审人设，将其转入正式人设库。

        Returns:
            被通过的人设文本，若用户不在待审列表则返回 None。
        """
        key = str(user_id)
        entry = self._pending.pop(key, None)
        if entry is None:
            return None
        persona_text = entry["persona_text"]
        self.set_persona(user_id, persona_text)
        self._save_pending()
        _logger.debug("[Persona] 审批通过 user_id=%d", user_id)
        return persona_text

    def reject_pending(self, user_id: int) -> Optional[str]:
        """驳回待审人设。

        Returns:
            被驳回的人设文本，若用户不在待审列表则返回 None。
        """
        key = str(user_id)
        entry = self._pending.pop(key, None)
        if entry is None:
            return None
        self._save_pending()
        _logger.debug("[Persona] 驳回 user_id=%d", user_id)
        return entry["persona_text"]


class UserPersonaModule(Module):
    """人设管理模块，通过 create_exports 约定动态注册 persona 服务。"""

    name = "user_persona"
    uid = 2000  # app: 业务模块
    version = (1, 1, 0)
    dependencies = ["ai_core"]
    required_services = ["config", "message"]

    def create_exports(self) -> dict:
        """约定: 返回的服务 dict 由框架自动注册到容器。"""
        data_dir = self.data_dir
        persona_service = UserPersonaService(data_dir)
        return {"persona": persona_service}

    async def on_init(self):
        """框架已处理服务导出，模块只注册命令。"""

    # ── 审核辅助 ──

    def _get_audit(self):
        """安全获取 audit 服务，不可用时返回 None。"""
        try:
            return self.services.get("audit")
        except KeyError:
            return None

    @staticmethod
    def _extract_reject_reason(args: list[str]) -> str:
        """从命令参数中提取驳回原因。

        格式: .设定 驳回 <QQ> <原因>  →  剔除前两段后剩余部分为原因。
        """
        if len(args) >= 3:
            return " ".join(args[2:])
        return "管理员驳回"

    @staticmethod
    def _parse_qq(raw: str) -> Optional[int]:
        """将字符串解析为 QQ 号（int），失败返回 None。"""
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    # ── 命令 ──

    @command(".设定")
    async def _cmd_set(self, ctx):
        """处理 .设定 命令：
         - .设定 <描述>              → 用户申请/修改人设
         - .设定 审批                → 管理员列出待审人设
         - .设定 通过 <QQ>           → 管理员通过某人设
         - .设定 驳回 <QQ> [原因]     → 管理员驳回某人设
        """
        args = ctx.args
        if not args:
            await ctx.reply("请提供人设描述，例如：.设定 我喜欢编程")
            return

        # ── 待审审批子命令 ──
        first = args[0].strip()

        if first == "审批":
            await self._cmd_list_pending(ctx)
            return

        if first in ("通过", "驳回"):
            await self._cmd_approval_action(ctx, first, args)
            return

        # ── 正常设定流程 ──
        persona = " ".join(args)
        if len(persona) > 200:
            await ctx.reply("人设描述不能超过200字")
            return

        # 审核人设内容
        audit_mgr = self._get_audit()
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
            ai_core_present = True
        except KeyError:
            ai_core_present = False

        if ai_core_present:
            _logger.debug("[Persona] 清除 AI 记忆 user_id=%d", ctx.user_id)
            await ai_core.clear_history(ctx.user_id)
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
        else:
            _logger.error("[Persona] ai_core 服务不可用！")
            await ctx.reply(
                f"已设定你的人设：{persona}"
                "（但 AI 核心未就绪，角色可能延迟生效）"
            )

    async def _cmd_list_pending(self, ctx):
        """列出所有待审人设（仅管理员可操作）。"""
        svc = self.services.get("persona")
        pending_list = svc.get_pending_list()
        if not pending_list:
            await ctx.reply("当前没有待审的人设申请。")
            return
        lines = ["📋 待审人设申请："]
        for entry in pending_list:
            uid = entry["user_id"]
            text = entry["persona_text"]
            lines.append(f"  QQ {uid} → {text}")
        await ctx.reply("\n".join(lines))

    async def _cmd_approval_action(self, ctx, action: str, args: list[str]):
        """处理管理员审批操作（通过 / 驳回）。"""
        if len(args) < 2:
            await ctx.reply(f"用法：.设定 {action} <QQ号> [原因]")
            return

        target_qq = self._parse_qq(args[1])
        if target_qq is None:
            await ctx.reply(f"无效的 QQ 号：{args[1]}")
            return

        svc = self.services.get("persona")

        if action == "通过":
            persona_text = svc.approve_pending(target_qq)
            if persona_text is None:
                await ctx.reply(f"❌ 用户 {target_qq} 没有待审的人设申请")
                return
            await ctx.reply(f"✅ 已通过用户 {target_qq} 的人设：{persona_text}")

        else:  # 驳回
            reason = self._extract_reject_reason(args)
            persona_text = svc.reject_pending(target_qq)
            if persona_text is None:
                await ctx.reply(f"❌ 用户 {target_qq} 没有待审的人设申请")
                return
            await ctx.reply(
                f"🚫 已驳回用户 {target_qq} 的人设\n"
                f"原因：{reason}"
            )
            # ── 驳回联动：喂给 AI 审计系统 ──
            audit_mgr = self._get_audit()
            if audit_mgr:
                rejection = {
                    "user_id": target_qq,
                    "persona_text": persona_text,
                    "reject_reason": reason,
                    "time": time.time(),
                }
                try:
                    await audit_mgr.add_rejection(rejection)
                except Exception as e:
                    _logger.warning(
                        "[Persona] 驳回记录提交失败，降级到本地日志: %s", e
                    )
                    _logger.info(
                        "[Persona] 驳回记录（本地）: user_id=%s "
                        "persona=%s reason=%s",
                        target_qq, persona_text, reason,
                    )
            else:
                _logger.info(
                    "[Persona] audit 服务不可用，驳回记录仅记入日志: "
                    "user_id=%s persona=%s reason=%s",
                    target_qq, persona_text, reason,
                )

    @command(".清除人设")
    async def _cmd_clear(self, ctx):
        """处理 .清除人设 命令，移除用户人设。"""
        svc = self.services.get("persona")
        svc.clear_persona(ctx.user_id)

        try:
            ai_core = self.services.get("ai_core")
            _logger.debug("[Persona] 清除 AI 记忆 user_id=%d", ctx.user_id)
            await ai_core.clear_history(ctx.user_id)
        except KeyError:
            _logger.error("[Persona] ai_core 服务不可用！")

        await ctx.reply("已清除你的人设")
