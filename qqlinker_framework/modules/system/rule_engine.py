"""规则引擎 - 用户自定义规则,匹配消息/事件后执行动作链。

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 规则不是自己执行操作,而是伪造虚拟消息走现有的命令路由。
 这意味着用户定义的任何命令都可以作为规则动作。

 规则结构 (JSON, 存于群子配置 模块管理.规则列表):
 {
   "规则名": "...",
   "匹配事件": "群消息",          // 群消息 | 群成员增加
   "匹配模式": "...",            // 正则或关键词
   "匹配类型": "正则",           // 正则 | 关键词 | 完全匹配
   "失败跳过": true,             // 动作链中某条失败是否继续
   "冷却": {"全局": 5, "单群": 10},  // 秒,0=不限
   "启用": true,
   "动作链": [
     ".命令 {user_id} 参数",
     "[CQ:at,qq={user_id}] 文本"
   ]
 }

 变量: {user_id} {group_id} {nickname} {message} {match} {msg_id} {time}

 UID:
   - 创建/编辑规则: min_uid ≤ RULE_MANAGE_UID (200)
   - 规则执行: 伪造消息 caller_uid = RULE_EXEC_UID (200)
═══════════════════════════════════════════════════════════════════════════
"""
import copy

import asyncio
import json
import logging
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional

from ...core.module import Module
from ...core.kernel.decorators import command, listen
from ...core.kernel.services import UID_NOBODY

_log = logging.getLogger(__name__)

# 规则管理/执行 UID
RULE_MANAGE_UID = 200
RULE_EXEC_UID = 200

# 默认冷却(秒)
DEFAULT_COOLDOWN_GLOBAL = 1
DEFAULT_COOLDOWN_GROUP = 0

# 规则存储前缀(独立文件,不经过 ConfigManager HMAC 签名)
_RULES_PREFIX = "rules"

# 交互式创建状态(user_id → 创建会话)
_create_sessions: Dict[int, dict] = {}

# 动作链最大消息数（防止洪水放大攻击）
MAX_ACTIONS_PER_RULE = 20

def _strip_cq(text: str) -> str:
    """剥离 CQ 码,只保留纯文本。"""
    import re as _re
    return _re.sub(r'\[CQ:[^\]]+\]', '', text)


def _replace_vars(template: str, ctx: dict) -> str:
    """替换动作链中的变量。"""
    vars_map = {
        "user_id": str(ctx.get("user_id", "")),
        "group_id": str(ctx.get("group_id", "")),
        "nickname": str(ctx.get("nickname", "")),
        "message": str(ctx.get("message", "")),
        "match": str(ctx.get("match", "")),
        "msg_id": str(ctx.get("msg_id", "")),
        "time": str(int(time.time())),
    }
    result = template
    for key, val in vars_map.items():
        result = result.replace("{" + key + "}", val)
    return result


def _match_rule(rule: dict, text: str) -> Optional[str]:
    """检查规则是否匹配消息文本。返回匹配内容或 None。"""
    pattern = rule.get("匹配模式", "")
    match_type = rule.get("匹配类型", "正则")
    if not pattern or not text:
        return None
    try:
        if match_type == "完全匹配":
            return pattern if text.strip() == pattern.strip() else None
        elif match_type == "关键词":
            return pattern if pattern in text else None
        else:  # 正则
            m = re.search(pattern, text)
            return m.group() if m else None
    except re.error:
        return None


class RuleService:
    """规则持久化与匹配服务。"""

    def __init__(self, base_path: str = ""):
        self._base_path = base_path
        self._cooldown_global: Dict[str, float] = {}
        self._cooldown_group: Dict[tuple, float] = {}

    def _check_cooldown(self, rule_name: str, group_id: int, cooldown_cfg: dict) -> bool:
        now = time.time()
        global_cd = cooldown_cfg.get("全局", DEFAULT_COOLDOWN_GLOBAL)
        group_cd = cooldown_cfg.get("单群", DEFAULT_COOLDOWN_GROUP)

        if global_cd > 0:
            last = self._cooldown_global.get(rule_name, 0)
            if now - last < global_cd:
                return False
        if group_cd > 0:
            last = self._cooldown_group.get((rule_name, group_id), 0)
            if now - last < group_cd:
                return False
        return True

    def _update_cooldown(self, rule_name: str, group_id: int):
        now = time.time()
        self._cooldown_global[rule_name] = now
        self._cooldown_group[(rule_name, group_id)] = now

    def match_rules(self, text: str, group_id: int) -> List[tuple]:
        """匹配所有规则，返回 [(规则dict, match_result)]。"""
        results = []
        if not self._rule_service or not hasattr(self, '_rules_path'):
            return results
        rules_path = self._rules_path(group_id)
        if not os.path.exists(rules_path):
            return results
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            rules = data.get('rules', []) if isinstance(data, dict) else []
        except Exception:
            return results

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if not rule.get("启用", True):
                continue
            if rule.get("匹配事件", "群消息") != "群消息":
                continue

            match_result = _match_rule(rule, text)
            if not match_result:
                continue

            if not self._check_cooldown(rule.get("规则名", ""), group_id, rule.get("冷却", {})):
                continue

            self._update_cooldown(rule.get("规则名", ""), group_id)
            results.append((rule, match_result))

        return results


class RuleEngineModule(Module):
    """用户自定义规则引擎。"""

    name = "rule_engine"
    mid = 200
    uid = 200
    tier = 200  # noqa: PYL-R0201 (service-level module - manages cross-module rules)
    version = (1, 0, 0)
    background = True  # must preload: @listen("GroupMessageEvent") needs active subscription at startup
    required_services = ["message", "config", "group_config"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._rule_service = RuleService(base_path="")
        self._creating: Dict[str, dict] = {}
        self._cooldown_global: Dict[str, float] = {}
        self._cooldown_group: Dict[tuple, float] = {}

    async def on_init(self):
        # on_init 时 data_dir 已就绪，同步到 rule_service
        self._rule_service._base_path = self.data_dir
        
        # 诊断：打印规则文件路径
        gid = list(self.config.get("消息转发.链接的群聊", [963953936]))[0]
        _log.debug("rules_path for group %d: %s", gid, self._rules_path(gid))

    @command(".规则", min_uid=200)
    async def _cmd_rule(self, ctx):
        """.规则 列表|创建|删除|启用|禁用|测试|查看 [参数]"""
        _log.debug("规则命令触发: user=%d group=%d args=%s",
                  ctx.user_id, ctx.group_id, ctx.args)
        args = ctx.args if ctx.args else []
        if not args:
            await self._show_help(ctx)
            return
        sub = args[0]
        if sub == "列表":
            await self._cmd_list(ctx)
        elif sub == "创建":
            await self._cmd_create(ctx)
        elif sub == "删除":
            await self._cmd_delete(ctx, args[1:])
        elif sub == "启用":
            await self._cmd_toggle(ctx, args[1:], True)
        elif sub == "禁用":
            await self._cmd_toggle(ctx, args[1:], False)
        elif sub == "测试":
            await self._cmd_test(ctx, args[1:])
        elif sub == "查看":
            await self._cmd_view(ctx, args[1:])
        else:
            await self._show_help(ctx)

    async def _show_help(self, ctx):
        await ctx.reply(
            "📐 规则引擎:\n"
            "  .规则 列表              - 查看本群规则\n"
            "  .规则 创建              - 交互式创建规则\n"
            "  .规则 删除 <规则名>     - 删除规则\n"
            "  .规则 启用 <规则名>     - 启用规则\n"
            "  .规则 禁用 <规则名>     - 禁用规则\n"
            "  .规则 测试 <消息>       - 测试匹配(不执行)\n"
            "  .规则 查看 <规则名>     - 查看规则详情"
        )

    async def _cmd_list(self, ctx):
        _log.debug(".规则 列表: group=%d rules_path=%s", ctx.group_id, self._rules_path(ctx.group_id))
        rules = self._get_rules(ctx.group_id)
        if not rules:
            await ctx.reply("本群暂无规则。使用 .规则 创建 添加")
            return
        lines = [f"📋 本群规则 ({len(rules)} 条):"]
        for r in rules:
            name = r.get("规则名", "?")
            enabled = "✅" if r.get("启用", True) else "❌"
            match_type = r.get("匹配类型", "?")
            lines.append(f"  {enabled} {name} ({match_type})")
        await ctx.reply("\n".join(lines))

    async def _cmd_create(self, ctx):
        """进入交互式创建流程。"""
        uid = str(ctx.user_id) if hasattr(ctx, 'user_id') else "0"
        self._creating[uid] = {
            "step": "name",
            "data": {},
            "group_id": ctx.group_id,
            "_ts": time.time(),
        }
        # 进入交互式会话,豁免去重
        try:
            tracker = self.services.get("session_tracker")
            tracker.enter(ctx.user_id, ctx.group_id, "rule_create")
        except Exception:
            pass
        await ctx.reply(
            "📝 规则创建向导 (输入 取消 退出)\n"
            "Step 1/5: 请输入规则名称"
        )

    async def _cmd_delete(self, ctx, args):
        if not args:
            await ctx.reply("用法: .规则 删除 <规则名>")
            return
        name = args[0]
        rules = self._get_rules(ctx.group_id)
        new_rules = [r for r in rules if r.get("规则名") != name]
        if len(new_rules) == len(rules):
            await ctx.reply(f"未找到规则 '{name}'")
            return
        await self._save_rules(ctx.group_id, new_rules)
        await ctx.reply(f"✅ 已删除规则 '{name}'")

    async def _cmd_toggle(self, ctx, args, enabled: bool):
        if not args:
            await ctx.reply(f"用法: .规则 {'启用' if enabled else '禁用'} <规则名>")
            return
        rules = self._get_rules(ctx.group_id)
        found = False
        for r in rules:
            if r.get("规则名") == args[0]:
                r["启用"] = enabled
                found = True
                break
        if not found:
            await ctx.reply(f"未找到规则 '{args[0]}'")
            return
        await self._save_rules(ctx.group_id, rules)
        await ctx.reply(f"✅ 规则 '{args[0]}' 已{'启用' if enabled else '禁用'}")

    async def _cmd_test(self, ctx, args):
        if not args:
            await ctx.reply("用法: .规则 测试 <消息>")
            return
        text = " ".join(args)
        rules = self._get_rules(ctx.group_id)
        hit = []
        for r in rules:
            if r.get("匹配事件", "群消息") != "群消息":
                continue
            match_result = _match_rule(r, text)
            if match_result:
                hit.append((r.get("规则名", "?"), match_result))
        if hit:
            lines = ["🔍 匹配结果:"]
            for name, m in hit:
                lines.append(f"  ✅ {name} → 匹配: '{m}'")
        else:
            lines = ["未匹配到任何规则"]
        await ctx.reply("\n".join(lines))

    async def _cmd_view(self, ctx, args):
        if not args:
            await ctx.reply("用法: .规则 查看 <规则名>")
            return
        rules = self._get_rules(ctx.group_id)
        for r in rules:
            if r.get("规则名") == args[0]:
                lines = [
                    f"📐 {r.get('规则名', '?')}",
                    f"  事件: {r.get('匹配事件', '群消息')}",
                    f"  类型: {r.get('匹配类型', '?')}",
                    f"  模式: {r.get('匹配模式', '')}",
                    f"  启用: {'✅' if r.get('启用', True) else '❌'}",
                    f"  失败跳过: {'是' if r.get('失败跳过', True) else '否'}",
                    f"  冷却: 全局{r.get('冷却', {}).get('全局', 0)}s / "
                    f"单群{r.get('冷却', {}).get('单群', 0)}s",
                    "  动作链:",
                ]
                for i, a in enumerate(r.get("动作链", []), 1):
                    lines.append(f"    {i}. {a[:80]}")
                await ctx.reply("\n".join(lines))
                return
        await ctx.reply(f"未找到规则 '{args[0]}'")

    @listen("GroupMessageEvent", priority=200)
    async def _on_rule_input(self, event):
        """监听消息:处理交互式创建流程或规则匹配。"""
        text = getattr(event, "message", "") or ""
        user_id = getattr(event, "user_id", 0)
        uid = str(user_id)

        # 交互式创建流程
        if uid in self._creating:
            session = self._creating[uid]
            # 清理 CQ 码和前后空白
            text = _strip_cq(text).strip()
            if not text:
                return
            # 超时检查(5分钟无输入自动取消)
            if time.time() - session.get('_ts', 0) > 300:
                del self._creating[uid]
                self._leave_session(user_id)
                await self.message.send_group(event.group_id, "⏰ 规则创建已超时,自动取消")
                return
            session['_ts'] = time.time()
            if text == "取消":
                del self._creating[uid]
                self._leave_session(user_id)
                await self.message.send_group(event.group_id, "已取消创建")
                return
            await self._handle_create_step(event, session, text, uid)
            return

        # 规则匹配
        try:
            group_id = getattr(event, "group_id", 0)
            user_id = getattr(event, "user_id", 0)
            text = getattr(event, "message", "") or ""
            nickname = getattr(event, "nickname", "") or ""
            msg_id = getattr(event, "msg_id", 0)

            # 直接读规则文件并匹配（不走 RuleService 单独路径）
            rules = self._get_rules(group_id)
            matches = []
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                if not rule.get("启用", True):
                    continue
                if rule.get("匹配事件", "群消息") != "群消息":
                    continue
                match_result = _match_rule(rule, text)
                if not match_result:
                    continue
                rule_name = rule.get("规则名", "")
                cooldown_cfg = rule.get("冷却", {})
                now = time.time()
                global_cd = cooldown_cfg.get("全局", DEFAULT_COOLDOWN_GLOBAL)
                group_cd = cooldown_cfg.get("单群", DEFAULT_COOLDOWN_GROUP)
                if global_cd > 0:
                    last = self._cooldown_global.get(rule_name, 0)
                    if now - last < global_cd:
                        continue
                if group_cd > 0:
                    last = self._cooldown_group.get((rule_name, group_id), 0)
                    if now - last < group_cd:
                        continue
                self._cooldown_global[rule_name] = now
                self._cooldown_group[(rule_name, group_id)] = now
                matches.append((rule, match_result))
            if matches:
                _log.debug("规则匹配: text='%s' 命中 %d 条规则", text[:50], len(matches))
            elif not any(text.startswith(p) for p in ('.', '。')):
                _log.debug("规则匹配: text='%s' 未命中任何规则 (group=%d)", text[:50], group_id)
            for rule, match_result in matches:
                skip_on_fail = rule.get("失败跳过", True)
                ctx = {
                    "user_id": user_id, "group_id": group_id,
                    "nickname": nickname, "message": text,
                    "match": match_result, "msg_id": msg_id,
                }
                actions = rule.get("动作链", [])
                # v5.2: 洪水防护 — 执行动作链中最多 MAX_ACTIONS_PER_RULE 条
                if len(actions) > MAX_ACTIONS_PER_RULE:
                    _log.warning(
                        "规则 '%s' 动作链过长 (%d > %d)，截断执行",
                        rule.get("规则名", "?"), len(actions), MAX_ACTIONS_PER_RULE,
                    )
                    actions = actions[:MAX_ACTIONS_PER_RULE]
                for action in actions:
                    rendered = _replace_vars(action, ctx) if isinstance(action, str) else ""
                    if not rendered:
                        continue
                    try:
                        if rendered.startswith("."):
                            self._route_command(rendered, user_id, group_id)
                        else:
                            await self._send_group_msg(group_id, rendered)
                    except Exception:
                        if not skip_on_fail:
                            break
                _log.info(
                    "规则 '%s' 触发: group=%d user=%d match='%s'",
                    rule.get("规则名", "?"), group_id, user_id, match_result[:50],
                )
        except Exception as e:
            _log.error("规则匹配异常: %s", e)

    async def _handle_create_step(self, event, session: dict, text: str, uid: str):
        step = session["step"]
        data = session["data"]
        gid = session["group_id"]
        text = text.strip()
        _log.debug("规则创建: step=%s uid=%s text='%s'", step, uid, text[:50])

        async def next_step(s):
            session["step"] = s
            _log.debug("规则创建: uid=%s → step=%s", uid, s)
            return None

        if step == "name":
            data["规则名"] = text
            await next_step("event")
            await self.message.send_group(gid,
                "Step 2/5: 选择匹配事件\n1.群消息  2.群成员增加")
            return

        if step == "event":
            event_map = {"1": "群消息", "2": "群成员增加"}
            val = event_map.get(text)
            if val is None:
                await self.message.send_group(gid,
                    f"❌ '{text}' 不是有效选项,请输入 1 或 2")
                return
            data["匹配事件"] = val
            await next_step("match_type")
            await self.message.send_group(gid,
                "Step 3/5: 选择匹配类型\n1.正则  2.关键词  3.完全匹配")
            return

        if step == "match_type":
            type_map = {"1": "正则", "2": "关键词", "3": "完全匹配"}
            val = type_map.get(text)
            if val is None:
                await self.message.send_group(gid,
                    f"❌ '{text}' 不是有效选项,请输入 1/2/3")
                return
            data["匹配类型"] = val
            await next_step("pattern")
            msg_text = f"Step 4/5: 请输入匹配模式 [{val}]"
            _log.debug("规则创建: uid=%s 发送消息到群 %d: %s", uid, gid, msg_text[:60])
            await self.message.send_group(gid, msg_text)
            _log.debug("规则创建: uid=%s 消息已入队", uid)
            return

        if step == "pattern":
            if not text:
                _log.warning("规则创建: pattern 步骤收到空输入, uid=%s", uid)
                await self.message.send_group(gid, "❌ 匹配模式不能为空,请重新输入")
                return
            data["匹配模式"] = text
            data["动作链"] = []
            await next_step("actions")
            await self.message.send_group(gid,
                "Step 5/5: 请输入动作链,每行一条\n"
                "  .命令 {user_id} 参数\n"
                "  文本消息\n"
                "输入 '完成' 保存规则")
            return

        if step == "actions":
            if text == "完成":
                await next_step("confirm")
                # 显示预览
                preview = (
                    f"规则预览:\n"
                    f"  名称: {data.get('规则名', '?')}\n"
                    f"  事件: {data.get('匹配事件', '?')}\n"
                    f"  模式: {data.get('匹配类型', '?')} = '{data.get('匹配模式', '')}'\n"
                    f"  动作: {len(data.get('动作链', []))} 条\n"
                    f"确认创建? (是/否)"
                )
                await self.message.send_group(gid, preview)
                return
            data["动作链"].append(text)
            # 洪水防护：动作链上限
            if len(data["动作链"]) >= MAX_ACTIONS_PER_RULE:
                next_step("confirm")
                await self.message.send_group(gid,
                    f"⚠️ 已达到动作链上限 ({MAX_ACTIONS_PER_RULE} 条)，"
                    f"自动进入确认步骤")
                # 触发确认预览
                preview = (
                    f"规则预览:\n"
                    f"  名称: {data.get('规则名', '?')}\n"
                    f"  事件: {data.get('匹配事件', '?')}\n"
                    f"  模式: {data.get('匹配类型', '?')} = '{data.get('匹配模式', '')}'\n"
                    f"  动作: {len(data.get('动作链', []))} 条\n"
                    f"确认创建? (是/否)"
                )
                await self.message.send_group(gid, preview)
            return

        if step == "confirm":
            if text.strip().lower() in ("是", "yes", "y", "1", "true"):
                data["启用"] = True
                data["失败跳过"] = True
                data["冷却"] = {"全局": DEFAULT_COOLDOWN_GLOBAL,
                               "单群": DEFAULT_COOLDOWN_GROUP}

                # 保存
                rules = self._get_rules(gid)
                rules.append(data)
                await self._save_rules(gid, rules)

                del self._creating[uid]
                self._leave_session(uid)
                lines = [
                    f"✅ 规则 '{data['规则名']}' 创建成功",
                    f"  事件: {data['匹配事件']}",
                    f"  匹配: {data['匹配类型']} / {data['匹配模式'][:40]}",
                    f"  动作: {len(data['动作链'])} 条",
                ]
                await self.message.send_group(gid, "\n".join(lines))
            else:
                await self.message.send_group(gid, "已取消创建")
                del self._creating[uid]
                self._leave_session(uid)

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    def _get_rules(self, group_id: int) -> list:
        """从独立文件加载规则(不经过 ConfigManager HMAC)。

        返回深拷贝,调用方可安全修改而不污染内存缓存。
        """
        path = self._rules_path(group_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            rules = data.get('rules', []) if isinstance(data, dict) else []
            return copy.deepcopy(rules) if isinstance(rules, list) else []
        except Exception:
            return []

    async def _save_rules(self, group_id: int, rules: list):
        """保存规则到独立文件（原子写入）。"""
        path = self._rules_path(group_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            fd, tmp = tempfile.mkstemp(
                suffix='.json', prefix=f'{group_id}_',
                dir=os.path.dirname(path),
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump({'rules': rules}, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except Exception as e:
            _log.error("保存规则失败: %s", e)

    def _rules_path(self, group_id: int) -> str:
        """规则文件路径:存储于 data_dir 根目录的 rules/ 下。"""
        # data_dir = 基础数据路径(如 data/),不是模块子目录
        return os.path.join(self.data_dir, '..', _RULES_PREFIX, f'{group_id}.json')

    def _leave_session(self, user_id):
        """退出交互式会话 - 使用通用 InteractiveSessionTracker 约定。"""
        try:
            tracker = self.services.try_get("session_tracker")
            if tracker:
                tracker.leave(int(user_id) if isinstance(user_id, str) else user_id)
        except Exception:
            pass

    async def _send_group_msg(self, group_id: int, message: str):
        await self.message.send_group(group_id, message)

    def _route_command(self, cmd_text: str, user_id: int, group_id: int):
        """伪造用户消息走命令路由。在 asyncio 事件循环中异步执行。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        _log.debug("规则动作: 路由命令 '%s' (user=%d group=%d)", cmd_text[:60], user_id, group_id)
        from ...core.kernel.events import GroupMessageEvent  # noqa: F811
        fake_event = GroupMessageEvent(
            user_id=user_id,
            group_id=group_id,
            nickname="[规则引擎]",
            message=cmd_text,
            raw_data={"_rule_uid": RULE_EXEC_UID},
        )
        asyncio.ensure_future(
            self.event_bus.publish(fake_event, caller_uid=RULE_EXEC_UID)
        )
