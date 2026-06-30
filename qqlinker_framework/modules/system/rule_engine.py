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
from ...core.kernel.events import GroupMessageEvent
from ...libraries.core.engine import Engine, EngineConfig

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

# ── v1.7 新增常量 ──
MAX_ACTIONS_PER_RULE = 20      # 动作链最大动作数
MAX_NESTING_LEVEL = 3          # 条件嵌套最大层级
MAX_LOOP_COUNT = 10            # 循环最大次数
MAX_DELAY_SECONDS = 300        # 延迟最大秒数
MAX_RULE_CALL_DEPTH = 5        # 规则调用最大深度

# 条件运算符
_COND_OPS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "包含": lambda a, b: str(b) in str(a),
    "不包含": lambda a, b: str(b) not in str(a),
}


def _strip_cq(text: str) -> str:
    """剥离 CQ 码,只保留纯文本。"""
    return re.sub(r'\[CQ:[^\]]+\]', '', text)


def _replace_vars(template: str, ctx: dict) -> str:
    """替换动作链中的变量（含事件上下文变量和规则变量）。"""
    # 事件上下文变量
    vars_map = {
        "user_id": str(ctx.get("user_id", "")),
        "group_id": str(ctx.get("group_id", "")),
        "nickname": str(ctx.get("nickname", "")),
        "message": str(ctx.get("message", "")),
        "match": str(ctx.get("match", "")),
        "msg_id": str(ctx.get("msg_id", "")),
        "time": str(int(time.time())),
    }
    # 规则变量（v1.7: 设变量 产生的变量）
    rule_vars = ctx.get("_rule_vars", {})
    result = template
    for key, val in vars_map.items():
        result = result.replace("{" + key + "}", val)
    for key, val in rule_vars.items():
        if isinstance(val, str):
            result = result.replace("{" + key + "}", val)
        else:
            result = result.replace("{" + key + "}", str(val))
    return result


def _match_rule(rule: dict, text: str) -> Optional[str]:
    """检查规则是否匹配消息文本。返回匹配内容或 None。"""
    pattern = rule.get("匹配模式", "")
    match_type = rule.get("匹配类型", "正则")
    if not pattern or not text:
        return None
    plain = _strip_cq(text).strip()
    if not plain:
        return None
    try:
        if match_type == "完全匹配":
            return pattern if plain == pattern.strip() else None
        elif match_type == "关键词":
            return pattern if pattern in plain else None
        else:  # 正则
            m = re.search(pattern, plain)
            return m.group() if m else None
    except re.error:
        return None


def _convert_var_value(value: str, convert_type: str, separator: str = ",") -> Any:
    """将字符串值按指定类型转换。

    Args:
        value: 原始字符串值。
        convert_type: "数字" / "列表" / "布尔"。
        separator: 列表分隔符。

    Returns:
        转换后的 Python 对象。
    """
    if convert_type == "数字":
        try:
            return int(value.strip())
        except (ValueError, TypeError):
            try:
                return float(value.strip())
            except (ValueError, TypeError):
                return 0
    elif convert_type == "列表":
        return [item.strip() for item in value.split(separator) if item.strip()]
    elif convert_type == "布尔":
        v = value.strip().lower()
        return v in ("true", "是", "1", "yes", "y")
    return value


def _evaluate_condition(condition: dict, variables: dict) -> bool:
    """评估单个条件。

    Args:
        condition: {"变量": "var_name", ">": 3} 或 {"变量": "var_name", "包含": "x"}
        variables: 规则变量字典。

    Returns:
        条件评估结果。
    """
    var_name = condition.get("变量", "")
    var_value = variables.get(var_name)
    if var_value is None:
        # 变量不存在 → 所有比较均视为 False
        return False
    for op_key, op_func in _COND_OPS.items():
        if op_key in condition:
            right = condition[op_key]
            try:
                return op_func(var_value, right)
            except (TypeError, ValueError):
                return False
    return False


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


class RuleEngineModule(Module, Engine):
    """用户自定义规则引擎 v1.7。

    v1.7 新增:
      - 变量系统（设变量 + 类型转换: 数字/列表/布尔）
      - 条件动作（如果/否则，支持 > < >= <= == != 包含 不包含）
      - 循环与延迟动作（最大 10 次循环 / 300 秒延迟）
      - 规则引用（调用规则，最大深度 5，循环检测）
      - 详细规则帮助（.规则 帮助 或 .帮助 规则）
    """

    name = "rule_engine"
    mid = 200
    uid = 200
    tier = 200
    version = (1, 7, 0)
    background = True
    required_services = ["message", "config", "group_config"]

    config = EngineConfig(
        name="rule_engine",
        version="1.7.0",
        mounts=["message", "config", "group_config"],
        pipeline=["match", "cooldown_check", "execute_actions"],
        provides=["rule"],
    )

    def __init__(self, services, event_bus):
        Module.__init__(self, services, event_bus)
        self._mounted = False
        self._rule_service = RuleService(base_path="")
        self._creating: Dict[str, dict] = {}
        self._cooldown_global: Dict[str, float] = {}
        self._cooldown_group: Dict[tuple, float] = {}

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    async def on_init(self):
        self._rule_service._base_path = self.data_dir

        # v1.7: 注册帮助详情
        try:
            help_svc = self.services.try_get("help_service")
            if help_svc:
                help_svc.register_help(".规则", {
                    "description": "用户自定义规则引擎 — 自动匹配群消息并执行动作链",
                    "usage": ".规则 <列表|创建|删除|启用|禁用|测试|查看|帮助> [参数]",
                    "examples": [
                        ".规则 列表",
                        ".规则 创建",
                        ".规则 查看 欢迎",
                        ".规则 测试 你好",
                        ".规则 帮助",
                    ],
                    "sub_commands": [
                        ("列表", "查看本群所有规则"),
                        ("创建", "交互式创建规则向导"),
                        ("删除 <规则名>", "删除指定规则"),
                        ("启用 <规则名>", "启用指定规则"),
                        ("禁用 <规则名>", "禁用指定规则"),
                        ("测试 <消息>", "测试消息匹配(不执行)"),
                        ("查看 <规则名>", "查看规则详情"),
                        ("帮助", "规则引擎 DSL 完整参考"),
                    ],
                    "module": "rule_engine",
                    "see_also": [".帮助 规则"],
                })
        except Exception as e:
            _log.debug("rule_engine.on_init help register: %s", e)

        gid = list(self.config.get("消息转发.链接的群聊", [963953936]))[0]
        _log.debug("rules_path for group %d: %s", gid, self._rules_path(gid))

    # ═══════════════════════════════════════════════════════════
    # 命令入口
    # ═══════════════════════════════════════════════════════════

    @command(".规则", min_uid=200)
    async def _cmd_rule(self, ctx):
        """.规则 列表|创建|删除|启用|禁用|测试|查看|帮助 [参数]"""
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
        elif sub == "帮助":
            await self._cmd_rule_help(ctx)
        else:
            await self._show_help(ctx)

    async def _show_help(self, ctx):
        await ctx.reply(
            "📐 .规则 <列表|创建|删除|启用|禁用|测试|查看|帮助> [参数]\n"
            "  列表              — 查看本群规则\n"
            "  创建              — 交互式创建规则\n"
            "  删除 <规则名>     — 删除规则\n"
            "  启用 <规则名>     — 启用规则\n"
            "  禁用 <规则名>     — 禁用规则\n"
            "  测试 <消息>       — 测试匹配(不执行)\n"
            "  查看 <规则名>     — 查看规则详情\n"
            "  帮助              — 规则引擎 DSL 完整参考"
        )

    async def _cmd_rule_help(self, ctx):
        """显示规则引擎 DSL 完整参考。"""
        msg = self._format_rule_help()
        await ctx.reply(msg)

    # ═══════════════════════════════════════════════════════════
    # 子命令实现
    # ═══════════════════════════════════════════════════════════

    async def _cmd_list(self, ctx):
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
        uid = str(ctx.user_id) if hasattr(ctx, 'user_id') else "0"
        self._creating[uid] = {
            "step": "name",
            "data": {},
            "group_id": ctx.group_id,
            "_ts": time.time(),
        }
        try:
            tracker = self.services.get("session_tracker")
            tracker.enter(ctx.user_id, ctx.group_id, "rule_create")
        except Exception as e:
            _log.warning("rule_engine._cmd_create: %s", e)
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
                    if isinstance(a, dict):
                        lines.append(f"    {i}. {json.dumps(a, ensure_ascii=False)[:80]}")
                    else:
                        lines.append(f"    {i}. {str(a)[:80]}")
                await ctx.reply("\n".join(lines))
                return
        await ctx.reply(f"未找到规则 '{args[0]}'")

    # ═══════════════════════════════════════════════════════════
    # 消息监听：交互式创建 + 规则匹配 + 动作执行
    # ═══════════════════════════════════════════════════════════

    @listen(GroupMessageEvent, priority=200)
    async def _on_rule_input(self, event):
        text = getattr(event, "message", "") or ""
        user_id = getattr(event, "user_id", 0)
        uid = str(user_id)

        # 交互式创建流程
        if uid in self._creating:
            session = self._creating[uid]
            text = _strip_cq(text).strip()
            if not text:
                return
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
            text = getattr(event, "message", "") or ""
            nickname = getattr(event, "nickname", "") or ""
            msg_id = getattr(event, "msg_id", 0)

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

            for rule, match_result in matches:
                rule_name = rule.get("规则名", "?")
                skip_on_fail = rule.get("失败跳过", True)
                ctx = {
                    "user_id": user_id, "group_id": group_id,
                    "nickname": nickname, "message": text,
                    "match": match_result, "msg_id": msg_id,
                    "_rule_vars": {},           # v1.7: 规则变量
                    "_rule_name": rule_name,    # v1.7: 当前规则名（用于日志）
                }
                actions = rule.get("动作链", [])
                if len(actions) > MAX_ACTIONS_PER_RULE:
                    _log.warning(
                        "规则 '%s' 动作链过长 (%d > %d)，截断执行",
                        rule_name, len(actions), MAX_ACTIONS_PER_RULE,
                    )
                    actions = actions[:MAX_ACTIONS_PER_RULE]

                # v1.7: 使用新动作执行引擎
                try:
                    await self._execute_actions(actions, ctx, skip_on_fail, depth=0)
                except Exception as e:
                    _log.error("规则 '%s' 执行异常: %s", rule_name, e)

                _log.info(
                    "规则 '%s' 触发: group=%d user=%d match='%s'",
                    rule_name, group_id, user_id, str(match_result)[:50],
                )
        except Exception as e:
            _log.error("规则匹配异常: %s", e)

    # ═══════════════════════════════════════════════════════════
    # v1.7 动作执行引擎
    # ═══════════════════════════════════════════════════════════

    async def _execute_actions(
        self,
        actions: list,
        ctx: dict,
        skip_on_fail: bool = True,
        depth: int = 0,
        nesting: int = 0,
    ) -> None:
        """执行动作列表。

        Args:
            actions: 动作列表（可包含字符串或字典）。
            ctx: 执行上下文（含变量）。
            skip_on_fail: 单个动作失败时是否继续。
            depth: 规则调用深度（调用规则）。
            nesting: 条件/循环嵌套层级。
        """
        group_id = ctx.get("group_id", 0)
        user_id = ctx.get("user_id", 0)

        if nesting > MAX_NESTING_LEVEL:
            _log.warning(
                "规则 '%s': 嵌套层级超出上限 (%d > %d)，跳过嵌套动作",
                ctx.get("_rule_name", "?"), nesting, MAX_NESTING_LEVEL,
            )
            return

        for action in actions:
            try:
                if isinstance(action, str):
                    # 传统字符串动作（向后兼容）
                    await self._exec_string_action(action, ctx, group_id, user_id)
                elif isinstance(action, dict):
                    await self._exec_dict_action(action, ctx, group_id, user_id,
                                                 skip_on_fail, depth, nesting)
                # 忽略非 str/dict 的动作
            except Exception as e:
                _log.warning("动作执行失败: %s", e)
                if not skip_on_fail:
                    raise

    async def _exec_string_action(self, action: str, ctx: dict, group_id: int, user_id: int):
        """执行传统字符串动作。"""
        rendered = _replace_vars(action, ctx)
        if not rendered:
            return
        if rendered.startswith(".output ") or rendered.startswith(".输出 "):
            output_text = rendered.split(" ", 1)[1] if " " in rendered else ""
            if output_text:
                await self._send_group_msg(group_id, output_text)
        elif rendered.startswith("."):
            self._route_command(rendered, user_id, group_id)
        else:
            await self._send_group_msg(group_id, rendered)

    async def _exec_dict_action(self, action: dict, ctx: dict, group_id: int,
                                user_id: int, skip_on_fail: bool,
                                depth: int, nesting: int):
        """执行字典型动作（v1.7 新动作类型）。"""
        # ── 设变量 ──
        if "设变量" in action:
            var_name = action["设变量"]
            cmd_text = action.get("命令", "")
            convert_type = action.get("转为", "")
            separator = action.get("分隔符", ",")
            field = action.get("取字段", "")

            # 构造执行上下文来获取命令返回值
            rendered = _replace_vars(cmd_text, ctx) if cmd_text else ""
            if rendered:
                # 执行命令获取输出
                try:
                    result_text = await self._capture_command_output(
                        rendered, user_id, group_id
                    )
                except Exception as e:
                    _log.warning("设变量 '%s' 命令执行失败: %s", var_name, e)
                    result_text = ""

                # 取字段（从 JSON 或文本中提取）
                if field and result_text:
                    result_text = self._extract_field(result_text, field)

                # 类型转换
                if convert_type:
                    value = _convert_var_value(
                        result_text, convert_type,
                        action.get("转为数字", ""),  # 兼容 "转为数字" 旧写法
                    )
                else:
                    value = result_text

                ctx.setdefault("_rule_vars", {})[var_name] = value
                _log.debug("设变量: %s = %s", var_name, repr(value)[:60])
            return

        # ── 如果/否则 ──
        if "如果" in action:
            condition = action["如果"]
            if not isinstance(condition, dict):
                _log.warning("条件格式无效: %s", condition)
                return
            then_actions = action.get("则", [])
            else_actions = action.get("否则", [])
            if _evaluate_condition(condition, ctx.get("_rule_vars", {})):
                await self._execute_actions(
                    then_actions, ctx, skip_on_fail, depth, nesting + 1,
                )
            elif else_actions:
                await self._execute_actions(
                    else_actions, ctx, skip_on_fail, depth, nesting + 1,
                )
            return

        # ── 循环 ──
        if "循环" in action:
            count = action.get("循环", 0)
            if not isinstance(count, int) or count < 1:
                _log.warning("循环次数无效: %s", count)
                return
            if count > MAX_LOOP_COUNT:
                _log.warning(
                    "规则 '%s': 循环次数超出上限 (%d > %d)，限制为 %d",
                    ctx.get("_rule_name", "?"), count, MAX_LOOP_COUNT, MAX_LOOP_COUNT,
                )
                count = MAX_LOOP_COUNT
            sub_actions = action.get("动作", [])
            for _ in range(count):
                await self._execute_actions(
                    sub_actions, ctx, skip_on_fail, depth, nesting + 1,
                )
            return

        # ── 延迟 ──
        if "延迟" in action:
            delay_secs = action.get("延迟", 0)
            if not isinstance(delay_secs, (int, float)) or delay_secs < 0:
                _log.warning("延迟时间无效: %s", delay_secs)
                return
            if delay_secs > MAX_DELAY_SECONDS:
                _log.warning(
                    "规则 '%s': 延迟超出上限 (%s > %d)，限制为 %d",
                    ctx.get("_rule_name", "?"), delay_secs, MAX_DELAY_SECONDS, MAX_DELAY_SECONDS,
                )
                delay_secs = MAX_DELAY_SECONDS
            sub_actions = action.get("动作", [])
            if delay_secs > 0:
                await asyncio.sleep(delay_secs)
            if sub_actions:
                await self._execute_actions(
                    sub_actions, ctx, skip_on_fail, depth, nesting + 1,
                )
            return

        # ── 调用规则 ──
        if "调用规则" in action:
            target_name = action["调用规则"]
            if depth >= MAX_RULE_CALL_DEPTH:
                _log.warning(
                    "规则 '%s': 调用深度超出上限 (%d >= %d)，停止递归",
                    ctx.get("_rule_name", "?"), depth, MAX_RULE_CALL_DEPTH,
                )
                return
            await self._call_rule(target_name, ctx, skip_on_fail, depth + 1, group_id)
            return

        # ── 未知 dict 动作 — 尝试作为传统动作处理 ──
        # 检查是否有 "发送群消息" / "发送私聊" / "触发命令" 键
        if "发送群消息" in action:
            msg = _replace_vars(str(action["发送群消息"]), ctx)
            await self._send_group_msg(group_id, msg)
            return
        if "发送私聊" in action:
            msg = _replace_vars(str(action["发送私聊"]), ctx)
            await self.message.send_private(user_id, msg)
            return
        if "触发命令" in action:
            cmd = _replace_vars(str(action["触发命令"]), ctx)
            self._route_command(cmd, user_id, group_id)
            return

        _log.warning("未知动作类型: %s", json.dumps(action, ensure_ascii=False)[:80])

    async def _capture_command_output(self, cmd_text: str, user_id: int, group_id: int) -> str:
        """执行命令并捕获其返回字符串。

        通过构造事件并等待回复来获取命令输出。使用 rule_accessible 标记的命令。
        如果命令不支持 rule_accessible，返回空字符串。
        """
        try:
            command_mgr = self.services.try_get("command")
            if not command_mgr:
                return ""
            # 查找命令
            cmd_info = command_mgr.find_command(cmd_text.strip())
            if not cmd_info:
                _log.debug("设变量: 未找到命令 '%s'", cmd_text[:30])
                return ""
            if not cmd_info.get("rule_accessible", False):
                _log.debug("设变量: 命令 '%s' 未标记为 rule_accessible", cmd_text[:30])
                return ""
            # 执行命令并捕获输出
            # 使用一个临时队列来捕获回复
            callback = cmd_info.get("callback")
            if not callable(callback):
                return ""

            # 构造模拟上下文
            proto = self.services.try_get("protocol")
            if proto:
                fake_event = proto.GroupMessageEvent(
                    user_id=user_id, group_id=group_id,
                    nickname="[规则引擎]", message=cmd_text,
                    raw_data={"_rule_uid": RULE_EXEC_UID},
                )
            else:
                fake_event = GroupMessageEvent(
                    user_id=user_id, group_id=group_id,
                    nickname="[规则引擎]", message=cmd_text,
                    raw_data={"_rule_uid": RULE_EXEC_UID},
                )

            # 创建一个捕获器来拦截 ctx.reply 输出
            captured: List[str] = []

            class _CaptureCtx:
                def __init__(self):
                    self.user_id = user_id
                    self.group_id = group_id
                    self.args = []
                    self.message = cmd_text

                async def reply(self, text: str):
                    captured.append(text)

            capture_ctx = _CaptureCtx()
            await callback(capture_ctx)
            return "\n".join(captured) if captured else ""
        except Exception as e:
            _log.debug("捕获命令输出失败: %s", e)
            return ""

    def _extract_field(self, text: str, field: str) -> str:
        """从文本中提取字段。支持 JSON 路径和简单键值。"""
        if not text or not field:
            return text
        # 尝试 JSON 解析
        try:
            data = json.loads(text)
            if isinstance(data, dict) and field in data:
                val = data[field]
                return str(val) if not isinstance(val, str) else val
            if isinstance(data, list):
                try:
                    idx = int(field)
                    val = data[idx]
                    return str(val) if not isinstance(val, str) else val
                except (ValueError, IndexError):
                    pass
        except (json.JSONDecodeError, Exception):
            pass
        # 简单键值对匹配: "key: value" 或 "key=value"
        for sep in (": ", "=", ":"):
            prefix = field + sep
            if prefix in text:
                rest = text.split(prefix, 1)[1]
                # 取到换行符或逗号
                for delim in ("\n", ",", "，"):
                    if delim in rest:
                        rest = rest.split(delim, 1)[0]
                        break
                return rest.strip()
        return text

    async def _call_rule(self, rule_name: str, ctx: dict, skip_on_fail: bool,
                         depth: int, group_id: int) -> None:
        """调用另一个规则的动作链。

        包含循环引用检测：使用调用栈记录已调用的规则名。
        """
        # 循环引用检测
        call_stack = ctx.get("_call_stack", [])
        if rule_name in call_stack:
            _log.warning(
                "规则 '%s': 检测到循环引用，调用链 %s → %s",
                ctx.get("_rule_name", "?"), " → ".join(call_stack), rule_name,
            )
            return
        call_stack.append(rule_name)
        ctx["_call_stack"] = call_stack

        # 查找目标规则
        rules = self._get_rules(group_id)
        target_rule = None
        for r in rules:
            if r.get("规则名") == rule_name:
                target_rule = r
                break
        if not target_rule:
            _log.warning("规则 '%s': 未找到目标规则 '%s'", ctx.get("_rule_name", "?"), rule_name)
            call_stack.pop()
            return

        _log.info(
            "规则调用: %s → %s (depth=%d)",
            ctx.get("_rule_name", "?"), rule_name, depth,
        )

        # 保留原始上下文（不污染被调用规则的变量）
        saved_vars = ctx.get("_rule_vars", {}).copy()
        saved_name = ctx.get("_rule_name", "")

        ctx["_rule_name"] = rule_name
        actions = target_rule.get("动作链", [])
        if len(actions) > MAX_ACTIONS_PER_RULE:
            actions = actions[:MAX_ACTIONS_PER_RULE]

        try:
            await self._execute_actions(actions, ctx, skip_on_fail, depth, 0)
        finally:
            ctx["_rule_name"] = saved_name
            ctx["_rule_vars"] = saved_vars
            call_stack.pop()

    # ═══════════════════════════════════════════════════════════
    # 交互式创建
    # ═══════════════════════════════════════════════════════════

    async def _handle_create_step(self, event, session: dict, text: str, uid: str):
        step = session["step"]
        data = session["data"]
        gid = session["group_id"]
        text = text.strip()

        async def next_step(s):
            session["step"] = s
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
            await self.message.send_group(gid,
                f"Step 4/5: 请输入匹配模式 [{val}]")
            return

        if step == "pattern":
            if not text:
                await self.message.send_group(gid, "❌ 匹配模式不能为空,请重新输入")
                return
            data["匹配模式"] = text
            data["动作链"] = []
            await next_step("actions")
            await self.message.send_group(gid,
                "Step 5/5: 请输入动作链,每行一条\n"
                "  .命令 {user_id} 参数\n"
                "  .输出 文本或CQ码\n"
                "  纯文本消息\n"
                "变量: {user_id} {group_id} {nickname} {message} {match}\n"
                "输入 '完成' 保存规则")
            return

        if step == "actions":
            if text == "完成":
                await next_step("confirm")
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
            # v1.7: 支持 JSON 动作输入
            parsed = self._try_parse_action_json(text)
            data["动作链"].append(parsed)
            if len(data["动作链"]) >= MAX_ACTIONS_PER_RULE:
                await next_step("confirm")
                await self.message.send_group(gid,
                    f"⚠️ 已达到动作链上限 ({MAX_ACTIONS_PER_RULE} 条)，"
                    f"自动进入确认步骤")
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

    @staticmethod
    def _try_parse_action_json(text: str) -> Any:
        """尝试解析 JSON 动作，失败则返回原始字符串。"""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, Exception):
            pass
        return text

    # ═══════════════════════════════════════════════════════════
    # 辅助
    # ═══════════════════════════════════════════════════════════

    def _get_rules(self, group_id: int) -> list:
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
        return os.path.join(self.data_dir, '..', _RULES_PREFIX, f'{group_id}.json')

    def _leave_session(self, user_id):
        try:
            tracker = self.services.try_get("session_tracker")
            if tracker:
                tracker.leave(int(user_id) if isinstance(user_id, str) else user_id)
        except Exception as e:
            _log.warning("rule_engine._leave_session: %s", e)

    async def _send_group_msg(self, group_id: int, message: str):
        await self.message.send_group(group_id, message)

    def _route_command(self, cmd_text: str, user_id: int, group_id: int):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        try:
            proto = self.services.get("protocol")
            fake_event = proto.GroupMessageEvent(
                user_id=user_id,
                group_id=group_id,
                nickname="[规则引擎]",
                message=cmd_text,
                raw_data={"_rule_uid": RULE_EXEC_UID},
            )
        except Exception:
            fake_event = GroupMessageEvent(
                user_id=user_id,
                group_id=group_id,
                nickname="[规则引擎]",
                message=cmd_text,
                raw_data={"_rule_uid": RULE_EXEC_UID},
            )
        asyncio.ensure_future(
            self.event_bus.publish(fake_event)
        )

    # ═══════════════════════════════════════════════════════════
    # v1.7 规则帮助
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _format_rule_help() -> str:
        """生成规则引擎 DSL 完整参考。"""
        return (
            "📐 规则引擎 DSL 完整参考 (v1.7)\n"
            "\n"
            "━━━ 动作类型 ━━━\n"
            "支持在动作链中使用字符串或 JSON 对象：\n"
            "  纯文本          → 直接发送到群\n"
            "  .命令 参数      → 路由到对应命令\n"
            "  .输出 文本      → 直接发送（不走命令路由）\n"
            "  {\"发送群消息\": \"...\"}   → 发送群消息\n"
            "  {\"发送私聊\": \"...\"}     → 发送私聊消息\n"
            "  {\"触发命令\": \".cmd\"}   → 触发指定命令\n"
            "\n"
            "━━━ 变量系统 ━━━\n"
            "  {\"设变量\": \"count\", \"命令\": \".在线人数\"}\n"
            "      → 执行命令并将返回文本存入变量 count\n"
            "  {\"设变量\": \"num\", \"命令\": \".count\", \"转为\": \"数字\"}\n"
            "      → 转换为数字（int）存入 num\n"
            "  {\"设变量\": \"items\", \"命令\": \".list\", \"转为\": \"列表\", \"分隔符\": \",\"}\n"
            "      → 按分隔符拆分为列表\n"
            "  {\"设变量\": \"flag\", \"命令\": \".status\", \"转为\": \"布尔\"}\n"
            "      → 转为布尔（true/是/1 → True）\n"
            "  {\"设变量\": \"field\", \"命令\": \".status\", \"取字段\": \"online\"}\n"
            "      → 从 JSON 返回中提取字段\n"
            "\n"
            "  支持的类型转换:\n"
            "    · 数字 — int() 转换，失败返回 0\n"
            "    · 列表 — 按分隔符 split，默认 \",\"\n"
            "    · 布尔 — \"true\"/\"是\"/\"1\" → True\n"
            "\n"
            "━━━ 条件动作（如果/否则）━━━\n"
            "  {\"如果\": {\"变量\": \"count\", \">\": 3},\n"
            "   \"则\": [...],\n"
            "   \"否则\": [...]}\n"
            "\n"
            "  支持的运算符:\n"
            "    >  <  >=  <=  ==  !=  包含  不包含\n"
            "  最大嵌套层级: 3\n"
            "\n"
            "━━━ 循环与延迟 ━━━\n"
            "  {\"循环\": 3, \"动作\": [...]}\n"
            "      → 重复执行 N 次（最大 10 次）\n"
            "  {\"延迟\": 30, \"动作\": [...]}\n"
            "      → 等待 N 秒后执行（最大 300 秒）\n"
            "\n"
            "━━━ 规则引用 ━━━\n"
            "  {\"调用规则\": \"other_rule_name\"}\n"
            "      → 调用另一个规则的动作链\n"
            "  最大调用深度: 5\n"
            "  自动循环引用检测（同名规则不可递归）\n"
            "\n"
            "━━━ 事件上下文变量 ━━━\n"
            "  {user_id}     — 发送者 QQ 号\n"
            "  {group_id}    — 群号\n"
            "  {nickname}    — 发送者昵称\n"
            "  {message}     — 消息原文\n"
            "  {match}       — 正则匹配结果\n"
            "  {msg_id}      — 消息 ID\n"
            "  {time}        — 当前时间戳\n"
            "\n"
            "━━━ 安全限制 ━━━\n"
            "  · 最大动作数: 20 条/规则（防洪水放大）\n"
            "  · 条件嵌套: 最多 3 层\n"
            "  · 循环次数: 最多 10 次\n"
            "  · 延迟时间: 最多 300 秒\n"
            "  · 规则调用: 最多 5 层深度\n"
            "  · 所有超出限制的操作自动截断并发出警告\n"
        )

    # ═══════════════════════════════════════════════════════════
    # Engine 生命周期
    # ═══════════════════════════════════════════════════════════

    async def ignite(self) -> None:
        if not self._verify_mounts():
            _log.warning("规则引擎启动: 部分依赖库未就绪，继续以降级模式运行")
        _log.info("规则引擎已启动 v%s", self.config.version)

    async def extinguish(self) -> None:
        self._creating.clear()
        self._cooldown_global.clear()
        self._cooldown_group.clear()
        _log.info("规则引擎已停止")
