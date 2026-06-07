"""审核拦截器：基于正则匹配违规词，自动处理违规用户。

增强特性:
  - 分层检测：正则初筛 → LLM 复核（若 audit 服务可用）
  - 违规记录持久化到 data_dir/violations.json，跨重启保留
  - 处理动作支持禁言/踢出/封禁，可调用 Orion 封禁系统
"""
import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from ...core.kernel.defguard import escape_player_name

_logger = logging.getLogger(__name__)


class Auditor:
    """审核拦截器，检测消息违规并自动执行处理动作。

    Attributes:
        patterns: 编译后的违规词正则模式列表。
        violation_counts: 内存中的违规计数（运行期）。
        _violations_file: 违规记录持久化路径。
        _load_violations: 启动时从文件恢复违规计数。
    """

    def __init__(self, ai_module):
        self.ai = ai_module
        self.config = ai_module.config
        self.patterns: List = []            # re.Pattern 列表
        self.violation_counts: Dict[int, int] = {}
        self._compiled: bool = False
        # ── 持久化路径 ──
        self._violations_file: str = ""
        self._compile_patterns()

        # ── 去抖：同一用户同一分钟内不重复发送群警告 ──
        self._last_warn: Dict[int, float] = {}

        # ── 并发安全 ──
        self._vio_lock = asyncio.Lock()
        self._save_pending = False          # 脏标记：缓冲写
        self._save_task: Optional[asyncio.Task] = None
        self._save_cooldown = 2.0           # 缓冲窗口（秒）

    # ── 初始化辅助 ────────────────────────────────────────────

    def _resolve_data_dir(self) -> str:
        """安全获取 data_dir（可能在 init 前被调用时返回空）。"""
        try:
            return self.ai.data_dir
        except (AttributeError, TypeError):
            return ""

    def init_persistence(self) -> None:
        """模块 on_init 后调用，设置持久化路径并加载历史记录。"""
        data_dir = self._resolve_data_dir()
        if data_dir:
            self._violations_file = os.path.join(data_dir, "violations.json")
            os.makedirs(data_dir, exist_ok=True)
            self._load_violations()

    def _load_violations(self) -> None:
        """从磁盘加载违规记录。"""
        if not self._violations_file or not os.path.exists(self._violations_file):
            return
        try:
            with open(self._violations_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # 兼容 {"user_id": count} 格式
                self.violation_counts = {
                    int(k): v for k, v in data.items()
                }
                _logger.info("已加载 %d 条违规记录", len(self.violation_counts))
        except (json.JSONDecodeError, OSError) as e:
            _logger.warning("加载违规记录失败: %s", e)

    async def _save_violations_async(self) -> None:
        """异步持久化违规记录到磁盘（通过线程池避免阻塞事件循环）。"""
        if not self._violations_file:
            return
        try:
            counts = dict(self.violation_counts)  # 快照副本
            await asyncio.to_thread(self._do_save_violations, counts)
        except Exception as e:
            _logger.error("保存违规记录失败: %s", e)

    def _do_save_violations(self, counts: dict) -> None:
        """同步写入磁盘（在 to_thread 中执行）。"""
        try:
            tmp = self._violations_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(counts, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._violations_file)  # 原子替换
        except OSError as e:
            _logger.error("保存违规记录失败: %s", e)

    def _schedule_save(self) -> None:
        """缓冲写：合并短时间内的多次写入为一次。"""
        self._save_pending = True
        if self._save_task is not None and not self._save_task.done():
            return
        self._save_task = asyncio.ensure_future(self._deferred_save())

    async def _deferred_save(self) -> None:
        """延迟写入：等待 cooldown 窗口后刷盘。"""
        await asyncio.sleep(self._save_cooldown)
        if self._save_pending:
            self._save_pending = False
            await self._save_violations_async()

    # ── 模式编译 ──────────────────────────────────────────────

    def _compile_patterns(self) -> None:
        """从配置编译正则表达式列表。"""
        words = self.config.get("AI助手.审核.违规词模式", [])
        import re
        self.patterns = [
            re.compile(re.escape(w), re.IGNORECASE) for w in words
        ]
        self._compiled = True

    # ── 分层检测 ──────────────────────────────────────────────

    def check_violation(self, user_id: int, text: str) -> bool:
        """分层检测：正则初筛 → LLM 复核（若可用）。

        NOTE: 此方法为同步路径，_llm_confirm_violation 始终返回 True
        以保证同步路径不绕过检测。异步 LLM 复核应在 process_message 中完成。
        调用此方法的异步路径（如 _validate_ai_request）应改用
        process_message 流的异步检测方式，避免 LLM 复核被绕过。

        Returns:
            True 表示确认违规。
        """
        # 第一层：正则初筛
        if not self._regex_first_pass(text):
            return False

        # 第二层：LLM 复核（若 audit 服务可用）
        if self._should_llm_review():
            if not self._llm_confirm_violation(user_id, text):
                _logger.debug("用户 %d: 正则命中但 LLM 复核未确认", user_id)
                return False

        self._record_violation_sync(user_id)
        return True

    def _regex_first_pass(self, text: str) -> bool:
        """正则模式初筛，命中任一模式返回 True。"""
        for pattern in self.patterns:
            if pattern.search(text):
                return True
        return False

    def _should_llm_review(self) -> bool:
        """检查 audit 服务是否可用以进行 LLM 复核。"""
        try:
            audit = self.ai.services.get("audit")
            return audit is not None
        except (KeyError, AttributeError):
            return False

    def _llm_confirm_violation(
        self, user_id: int, text: str,
    ) -> bool:
        """调用 audit LLM 确认是否真的违规。

        注意：这是同步方法（check_violation 为同步）。
        在同步上下文中，我们通过简单判断来模拟 LLM 复核；
        真正的异步 LLM 调用在 process_message 中触发。
        这里返回 True 表示先假定命中（避免绕过），
        process_message 中的异步流程会做精准确认。
        """
        # 同步方法中无法 await，信任正则命中 + 异步回调确认
        return True

    async def _async_llm_confirm(
        self, user_id: int, group_id: int, text: str,
    ) -> Tuple[bool, Optional[str]]:
        """异步调用 audit 服务确认违规（在 process_message 中调用）。

        Returns:
            (confirmed, reason) — confirmed 表示确实违规，reason 为 LLM 给出的原因。
        """
        try:
            audit = self.ai.services.get("audit")
            if not audit:
                return True, None
            prompt = (
                "你是一个内容安全审核员。请判断以下消息是否包含明显的"
                "侮辱、谩骂、人身攻击或恶意骚扰内容。\\n"
                "注意：仅当上下文明确且攻击性强时标记为违规。"
                "玩笑式的朋友间用语不算违规。\\n\\n"
                "如果消息只是朋友间开玩笑或无害表达，请回复：SAFE。\\n"
                "如果存在明显辱骂或恶意攻击，请回复：VIOLATION: <简短原因>"
                f"\\n\\n用户消息：{text[:300]}"
            )
            reason = await audit.check_message(user_id, group_id, prompt)
            if reason and reason.strip().upper() != "SAFE":
                return True, reason.strip()
            return False, None
        except (KeyError, AttributeError, Exception) as e:
            _logger.warning("LLM 复核失败: %s", e)
            # LLM 不可用时信任正则命中
            return True, None

    # ── 违规记录 ──────────────────────────────────────────────

    def _record_violation_sync(self, user_id: int) -> None:
        """同步记录违规（仅用于同步路径如 check_violation）。

        同步路径无法 await，直接修改计数并调度异步写入。
        """
        count = self.violation_counts.get(user_id, 0) + 1
        self.violation_counts[user_id] = count
        self._schedule_save()  # 缓冲写
        limit = self.config.get("AI助手.审核.违规次数上限", 3)
        if count >= limit:
            self._apply_action(user_id)
            self.violation_counts[user_id] = 0
            self._schedule_save()

    async def _record_violation(self, user_id: int) -> None:
        """异步记录一次违规并检查是否达到处理阈值。

        使用 asyncio.Lock 保护 violation_counts 防止竞态。
        """
        async with self._vio_lock:
            count = self.violation_counts.get(user_id, 0) + 1
            self.violation_counts[user_id] = count
            self._schedule_save()  # 缓冲写
            limit = self.config.get("AI助手.审核.违规次数上限", 3)
            if count >= limit:
                self._apply_action(user_id)
                self.violation_counts[user_id] = 0
                self._schedule_save()

    def get_violation_count(self, user_id: int) -> int:
        """获取用户当前违规次数。"""
        return self.violation_counts.get(user_id, 0)

    async def reset_violations(self, user_id: int) -> None:
        """重置用户违规计数。"""
        async with self._vio_lock:
            self.violation_counts.pop(user_id, None)
        self._schedule_save()

    # ── 处理动作 ──────────────────────────────────────────────

    def _apply_action(self, user_id: int) -> None:
        """根据配置执行违规处理动作，尝试调用 Orion 封禁系统。

        支持三种动作类型：
          - 禁言：发送游戏禁言指令，阻止发言
          - 踢出：发送游戏踢出指令
          - 封禁：记录到封禁系统（若 Orion 可用调用其 ban 方法）
        """
        action = self.config.get("AI助手.审核.处理动作", "禁言")
        _logger.warning(
            "用户 %d 违规次数达到上限，执行 %s", user_id, action,
        )

        if action == "禁言":
            self._do_mute(user_id)
        elif action == "踢出":
            self._do_kick(user_id)
        elif action == "封禁":
            self._do_ban(user_id)
        else:
            _logger.warning("未知处理动作: %s", action)

    def _do_mute(self, user_id: int) -> None:
        """禁言用户（通过游戏指令）。"""
        try:
            player_name = self._resolve_player_name(user_id)
            if player_name:
                # 默认禁言 30 分钟
                self.ai.adapter.send_game_command(
                    f'mute "{player_name}" 1800 "AI审核：违规发言"'
                )
                _logger.info("用户 %d (玩家 %s) 已被禁言", user_id, player_name)
            else:
                _logger.warning(
                    "用户 %d: 无法解析玩家名，跳过禁言", user_id,
                )
        except Exception as e:
            _logger.error("禁言用户 %d 失败: %s", user_id, e)

    def _do_kick(self, user_id: int) -> None:
        """踢出用户（通过游戏指令）。"""
        try:
            player_name = self._resolve_player_name(user_id)
            if player_name:
                safe_name = escape_player_name(player_name)
                self.ai.adapter.send_game_command(
                    f'kick "{safe_name}" AI审核：多次违规发言'
                )
                _logger.info("用户 %d (玩家 %s) 已被踢出", user_id, player_name)
            else:
                _logger.warning(
                    "用户 %d: 无法解析玩家名，跳过踢出", user_id,
                )
        except Exception as e:
            _logger.error("踢出用户 %d 失败: %s", e)

    def _do_ban(self, user_id: int) -> None:
        """封禁用户，优先使用 Orion 封禁系统。

        如果 Orion bridge 可用，调用其 add_ban_with_reason 方法；
        否则 fallback 到游戏原生命令永久封禁。
        """
        try:
            player_name = self._resolve_player_name(user_id)
            if not player_name:
                _logger.warning(
                    "用户 %d: 无法解析玩家名，跳过封禁", user_id,
                )
                return

            # ★ 尝试调用 Orion 封禁系统
            orion = self._get_orion_bridge()
            if orion:
                try:
                    orion.add_ban_with_reason(
                        player_name,
                        reason="AI审核：多次违规发言",
                        duration=1440,  # 默认封禁 24 小时（分钟）
                    )
                    _logger.info(
                        "用户 %d (玩家 %s) 已通过 Orion 封禁", user_id, player_name,
                    )
                    return
                except AttributeError:
                    # add_ban_with_reason 不存在 — 使用 ban_player fallback
                    if hasattr(orion, "ban_player") and callable(orion.ban_player):
                        orion.ban_player(
                            player_name,
                            reason="AI审核：多次违规发言",
                            duration=1440,
                        )
                        _logger.info(
                            "用户 %d (玩家 %s) 已通过 Orion ban_player 封禁",
                            user_id, player_name,
                        )
                        return
                    # Fallback：使用游戏原生命令
                    _logger.warning(
                        "用户 %d: Orion 无可用封禁接口，回退到原生命令", user_id,
                    )
                except Exception as e:
                    _logger.error("Orion 封禁失败: %s，回退到原生指令", e)

            # ★ Fallback：使用游戏原生命令
            self.ai.adapter.send_game_command(
                f'ban "{player_name}" AI审核：多次违规发言'
            )
            _logger.info(
                "用户 %d (玩家 %s) 已通过原生指令封禁", user_id, player_name,
            )
        except Exception as e:
            _logger.error("封禁用户 %d 失败: %s", e)

    def _resolve_player_name(self, user_id: int) -> Optional[str]:
        """通过 user_id 解析玩家名。

        尝试路径：
          1. game_binding 服务（QQ ↔ 游戏名绑定）
          2. 在线玩家列表匹配
        """
        # 尝试绑定服务
        try:
            binding = self.ai.services.get("game_binding")
            if binding:
                name = binding.get_player_name(user_id)
                if name:
                    return name
        except (KeyError, AttributeError):
            pass

        # Fallback：通过在线玩家列表推断（搜索包含 QQ 号的玩家名）
        try:
            players = self.ai.adapter.get_online_players()
            user_str = str(user_id)
            for p in players:
                if user_str in p:
                    return p
        except Exception:
            pass

        return None

    def _get_orion_bridge(self) -> Optional[object]:
        """获取 Orion 封禁系统实例（若已注册）。"""
        try:
            return self.ai.services.get("orion_bridge")
        except (KeyError, AttributeError):
            return None

    # ── 消息处理入口 ──────────────────────────────────────────

    async def process_message(
        self, user_id: int, group_id: int, message: str,
    ) -> None:
        """处理群消息：正则初筛 → 异步 LLM 复核 → 记录 + 警告。

        若 audit 服务可用，正则命中后进行 LLM 复核确认，
        避免误判朋友间玩笑用语。
        """
        # 正则初筛
        hit = self._regex_first_pass(message)
        if not hit:
            return

        # 异步 LLM 复核（若可用）
        confirmed = True
        reason = None
        if self._should_llm_review():
            confirmed, reason = await self._async_llm_confirm(
                user_id, group_id, message,
            )

        if not confirmed:
            _logger.debug(
                "用户 %d: 正则命中但 LLM 复核判定为 SAFE，跳过", user_id,
            )
            return

        # 确认违规：记录并发送警告
        await self._record_violation(user_id)

        # 去抖：同一用户 60 秒内不重复发警告
        now = time.time()
        last = self._last_warn.get(user_id, 0)
        if now - last < 60:
            return
        self._last_warn[user_id] = now

        warn_msg = (
            f"[CQ:at,qq={user_id}] 请注意文明用语"
        )
        if reason:
            warn_msg += f"（{reason}）"
        await self.ai.message.send_group(group_id, warn_msg)
