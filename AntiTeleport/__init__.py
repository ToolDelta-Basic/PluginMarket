# -*- coding: utf-8 -*-

import json
import re
import time
import math

from tooldelta import plugin_entry, Plugin, ToolDelta, Player, Chat, game_utils
from tooldelta.constants import PacketIDS
from tooldelta.utils.timer_events import timer_event

LEGAL_TP_TAG = "legal_tp"
PERMANENT_TP_TAG = "互传"

DIM_END = 2

DEATH_PATTERNS = [
    "死了",
    "从高处摔了下来",
    "淹死了",
    "在火焰中凋零",
    "被",
    "试图在岩浆里游泳",
    "被刻意的游戏设计",
    "被魔法杀死了",
    "被炸死了",
    "被冻死了",
    "被铁砧压扁了",
    "被箭射死了",
    "死于",
    "获得了动能",
    "被闪电击中了",
    "离开了这个世界",
    "发现了底部",
    "没有注意到",
    "被刺穿了",
    "被压死了",
    "被甜蜜的浆果",
    "被烤熟了",
    "被活埋在",
    "被龙息烧",
    "凋零了",
]

class AntiTeleport(Plugin):

    name = "AntiTeleport"
    author = "江小白"
    version = (1, 0, 0)
    description = "检测玩家异常传送，累进惩罚作弊。支持控制台/聊天栏菜单双通道管理封禁、解封、白名单。"

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)

        self.config_dir = self.data_path.parent.parent / "插件配置文件"
        self.config_file = self.config_dir / f"{self.name}.json"
        self.last_positions: dict[str, tuple[float, float, float, int]] = {}
        self.offenses: dict[str, dict] = {}
        self.offenses_file = self.data_path / "offenses.json"
        self.punish_cooldown: dict[str, float] = {}
        self.getpos_failures: dict[str, int] = {}
        self.legal_tp_set: set[str] = set()
        self.death_grace: dict[str, float] = {}
        self.death_counts: dict[str, int] = {}
        self.chatbar = None

        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_chat)
        self.ListenPacket(PacketIDS.Text, self.on_pkt_text)

        self.frame.add_console_cmd_trigger(
            ["封禁", "ban"],
            "<玩家名> [时间]",
            "手动封禁玩家。时间格式: 30m|1h|1d|永久 (默认永久)",
            self._on_console_ban
        )
        self.frame.add_console_cmd_trigger(
            ["解封", "unban"],
            "<玩家名>",
            "解除玩家封禁",
            self._on_console_unban
        )
        self.frame.add_console_cmd_trigger(
            ["反传送白名单", "whitelist"],
            "<玩家名>",
            "添加互传白名单",
            self._on_console_whitelist
        )
        self.frame.add_console_cmd_trigger(
            ["去除传送白名单", "unwhitelist"],
            "<玩家名>",
            "移除互传白名单",
            self._on_console_unwhitelist
        )

    def on_preload(self):
        default_cfg = {"传送阈值_格": 20}
        try:
            if self.config_file.exists():
                try:
                    self.cfg = json.loads(
                        self.config_file.read_text(encoding="utf-8")
                    )
                    updated = False
                    for key, val in default_cfg.items():
                        if key not in self.cfg:
                            self.cfg[key] = val
                            updated = True
                    if updated:
                        self._save_config()
                    self.print_suc("配置文件加载成功")
                except Exception as e:
                    self.print_err(f"配置文件读取失败，回退到默认配置: {e}")
                    self.cfg = dict(default_cfg)
                    self._save_config()
            else:
                self.cfg = dict(default_cfg)
                self._save_config()
                self.print_inf("已生成默认配置文件")
        except Exception as e:
            self.print_err(f"on_preload 异常: {e}")
            self.cfg = dict(default_cfg)

        try:
            if self.offenses_file.exists():
                self.offenses = json.loads(
                    self.offenses_file.read_text(encoding="utf-8")
                )
                total = sum(
                    o.get("count", 0) for o in self.offenses.values()
                )
                self.print_inf(f"违规记录已加载 ({len(self.offenses)} 名玩家, 共 {total} 次)")
        except Exception as e:
            self.print_err(f"加载违规记录失败: {e}")
            self.offenses = {}

        try:
            self.chatbar = self.GetPluginAPI("聊天栏菜单", force=False)
            if self.chatbar is not None:
                self.print_suc("已接入聊天栏菜单")
        except Exception:
            self.chatbar = None

    def on_active(self):

        try:
            self.game_ctrl.sendcmd(
                "/scoreboard objectives add AntiTeleportDeathCount deathCount"
            )
            self.game_ctrl.sendcmd(
                "/scoreboard objectives setdisplay belowname AntiTeleportDeathCount"
            )
            self.print_suc("deathCount 计分板已就绪")
        except Exception as e:
            self.print_war(f"计分板创建（可能已存在）: {e}")

        try:
            threshold = self.cfg.get("传送阈值_格", 20)
            self.print_suc(
                f"AntiTeleport 已激活 | "
                f"阈值={threshold}格 | "
                f"累进惩罚：警告→封30分→封1时→永久"
            )
            self._tick_check()

            if self.chatbar is not None:
                self.chatbar.add_new_trigger(
                    ["封禁", "ban"],
                    [("玩家名", str, None), ("时间", str, "永久")],
                    "手动封禁玩家",
                    self._on_menu_ban,
                    op_only=True
                )
                self.chatbar.add_new_trigger(
                    ["解封", "unban"],
                    [("玩家名", str, None)],
                    "解除玩家封禁",
                    self._on_menu_unban,
                    op_only=True
                )
                self.chatbar.add_new_trigger(
                    ["反传送白名单", "whitelist"],
                    [("玩家名", str, None)],
                    "添加互传白名单",
                    self._on_menu_whitelist,
                    op_only=True
                )
                self.chatbar.add_new_trigger(
                    ["去除传送白名单", "unwhitelist"],
                    [("玩家名", str, None)],
                    "移除互传白名单",
                    self._on_menu_unwhitelist,
                    op_only=True
                )
                self.print_suc(
                    f"已注册 {4} 个聊天栏菜单触发词"
                )
        except Exception as e:
            self.print_err(f"on_active 异常: {e}")

    def on_player_join(self, player: Player):
        try:
            offense = self.offenses.get(player.name)
            if offense:
                ban_until = offense.get("ban_until")
                if ban_until is not None:
                    now = time.time()
                    if ban_until == -1:
                        self.game_ctrl.sendcmd(
                            f'/kick "{player.name}" '
                            f'§4[反传送] 您已被永久封禁'
                        )
                        self.print_inf(
                            f"拒绝永久封禁玩家 {player.name} 加入"
                        )
                        return
                    elif isinstance(ban_until, (int, float)) and ban_until > now:
                        remaining = int(ban_until - now)
                        mins = remaining // 60
                        secs = remaining % 60
                        self.game_ctrl.sendcmd(
                            f'/kick "{player.name}" '
                            f'§c[反传送] 封禁剩余 {mins}分{secs}秒'
                        )
                        self.print_inf(
                            f"拒绝封禁玩家 {player.name} 加入"
                            f" (剩余{mins}分{secs}秒)"
                        )
                        return

            pos_data = game_utils.getPos(player.name)
            pos = pos_data["position"]
            dim = pos_data["dimension"]
            self.last_positions[player.name] = (
                pos["x"], pos["y"], pos["z"], dim
            )
            self.print_inf(
                f"玩家 {player.name} 加入，"
                f"维度={dim}, 位置=({pos['x']:.1f},{pos['y']:.1f},{pos['z']:.1f})"
            )

            try:
                resp = self.game_ctrl.sendcmd_with_resp(
                    f'/tag "{player.name}" list',
                    timeout=3
                )
                haystack = self._flatten_response(resp)
                if LEGAL_TP_TAG in haystack:
                    self.legal_tp_set.add(player.name)
                    self.print_inf(f"玩家 {player.name} 拥有 legal_tp 标签，已标记")
            except Exception:
                pass

            self.death_counts.setdefault(player.name,
                self._get_death_count(player.name))

        except Exception as e:
            self.print_err(f"记录玩家 {player.name} 初始位置失败: {e}")

    def on_player_leave(self, player: Player):
        try:
            self.last_positions.pop(player.name, None)
            self.punish_cooldown.pop(player.name, None)
            self.getpos_failures.pop(player.name, None)
            self.death_grace.pop(player.name, None)
            self.death_counts.pop(player.name, None)
            self.legal_tp_set.discard(player.name)

        except Exception as e:
            self.print_err(f"清理玩家 {player.name} 数据失败: {e}")

    def on_chat(self, chat: Chat):
        try:
            msg_orig = chat.msg.strip()

            if msg_orig.startswith("/"):
                cmd = msg_orig[1:].strip()
            else:
                cmd = msg_orig

            msg_lower = msg_orig.lower()

            if self.chatbar is None:
                if chat.player and chat.player.is_op():
                    self._handle_admin_cmd(cmd, chat)
                else:
                    chat.player.reply("§c你没有权限使用此命令")

            if not (
                msg_lower.startswith("/tp ")
                or msg_lower.startswith("/teleport ")
            ):
                return

            player = chat.player
            parts = msg_orig.split()
            if len(parts) < 2:
                return

            try:
                float(parts[1])
                return
            except ValueError:
                pass

            targets: list[str] = []
            targets.append(parts[1])

            if len(parts) >= 3:
                try:
                    float(parts[2])
                except ValueError:
                    targets.append(parts[2])

            for target in targets:
                self.legal_tp_set.add(target)
                try:
                    self.game_ctrl.sendcmd(
                        f'/tag "{target}" add {LEGAL_TP_TAG}'
                    )
                except Exception as e:
                    self.print_err(
                        f"给玩家 {target} 添加 MC 标签失败: {e}"
                    )

            self.print_inf(
                f"玩家 {player.name} 使用了传送命令，"
                f"已为 {', '.join(targets)} 添加合法传送标记"
            )
        except Exception as e:
            self.print_err(f"on_chat 异常: {e}")

    def on_pkt_text(self, packet: dict):
        try:
            msg = packet.get("Message", "")
            if not msg:
                return

            clean = re.sub(r"§[0-9A-FK-ORa-fk-or]", "", msg).strip()

            space_idx = clean.find(" ")
            if space_idx == -1:
                return
            name_part = clean[:space_idx]
            rest = clean[space_idx + 1:]

            try:
                all_names = {p.name for p in self.game_ctrl.players.getAllPlayers()}
            except Exception:
                return
            if name_part not in all_names:
                return

            for pat in DEATH_PATTERNS:
                if rest.startswith(pat):
                    self.death_grace[name_part] = time.time() + 10
                    self.print_inf(
                        f"检测到玩家 {name_part} 死亡(\"{rest[:20]}\")，给予 10 秒重生宽限期"
                    )
                    return

            self.print_war(f"[死亡检测] 非死亡消息: {name_part} | {rest[:40]}")
        except Exception:
            pass
        return False

    def _get_death_count(self, player_name: str) -> int:
        try:
            resp = self.game_ctrl.sendcmd_with_resp(
                f"/scoreboard players test {player_name} "
                f"AntiTeleportDeathCount"
            )
            if resp is None or not resp.success:
                return -1
            text = resp.as_dict.get("OutputMessages", [])
            if not text:
                return -1
            out = str(text[0].get("Message", ""))

            out = re.sub(r"§[0-9A-FK-ORa-fk-or]", "", out)

            m = re.search(r"has (\d+)", out)
            return int(m.group(1)) if m else 0
        except Exception as e:
            self.print_war(f"_get_death_count({player_name}) 异常: {e}")
            return 0

    def _handle_admin_cmd(self, cmd: str, chat: Chat):
        parts = cmd.split(None, 2)
        if not parts:
            return

        action = parts[0].lower()

        if action in ("封禁", "ban"):
            if len(parts) < 2:
                self.print_err("用法: 封禁 <玩家名> [时间: 30m|1h|1d|永久]")
                return
            target = parts[1]
            duration_str = parts[2] if len(parts) >= 3 else "永久"
            self._ban_player(target, duration_str)

        elif action in ("解封", "unban"):
            if len(parts) < 2:
                self.print_err("用法: 解封 <玩家名>")
                return
            target = parts[1]
            self._unban_player(target)

        elif action in ("反传送白名单", "whitelist"):
            if len(parts) < 2:
                self.print_err("用法: 反传送白名单 <玩家名>")
                return
            target = parts[1]
            self._add_whitelist(target)

        elif action in ("去除传送白名单", "unwhitelist"):
            if len(parts) < 2:
                self.print_err("用法: 去除传送白名单 <玩家名>")
                return
            target = parts[1]
            self._remove_whitelist(target)

    def _parse_duration(self, duration_str: str) -> int:
        s = duration_str.strip().lower()

        s = re.sub(r"[^a-z\d]+$", "", s)
        if not s or s in ("永久", "perm", "permanent", "ban"):
            return -1

        m = re.match(r"^(\d+(?:\.\d+)?)\s*(m|min|h|hour|d|day|s|sec)?$", s)
        if not m:
            self.print_err(f"无法解析时间: {duration_str}，视为永久封禁")
            return -1
        value = float(m.group(1))
        unit = (m.group(2) or "h").lower()
        if unit in ("d", "day"):
            return int(value * 86400)
        elif unit in ("h", "hour"):
            return int(value * 3600)
        elif unit in ("s", "sec"):
            return int(value)
        else:
            return int(value * 60)

    def _ban_player(self, player_name: str, duration_str: str):
        duration_sec = self._parse_duration(duration_str)
        now = time.time()
        if duration_sec == -1:
            until_ts = -1
            self.print_inf(f"玩家 {player_name} 已被永久封禁")
        else:
            until_ts = int(now + duration_sec)
            remain = until_ts - int(now)
            h, rem = divmod(remain, 3600)
            m, _ = divmod(rem, 60)
            self.print_inf(
                f"玩家 {player_name} 已被封禁 {h}小时{m}分钟"
                f"（至 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(until_ts))}）"
            )

        self.offenses[player_name] = {
            "count": 1,
            "ban_until": until_ts,
            "banned_at": int(now),
            "reason": f"手动封禁（{duration_str}）",
        }
        self._save_offenses()

        for player in self.game_ctrl.players:
            if player.name == player_name:
                try:
                    if duration_sec == -1:
                        self.game_ctrl.sendcmd(f'/kick "{player_name}" §c你已被永久封禁')
                    else:
                        h, rem = divmod(duration_sec, 3600)
                        m, _ = divmod(rem, 60)
                        self.game_ctrl.sendcmd(
                            f'/kick "{player_name}" §c你已被封禁 {h}小时{m}分钟'
                        )
                except Exception as e:
                    self.print_err(f"踢出玩家 {player_name} 失败: {e}")
                break

    def _unban_player(self, player_name: str):
        if player_name in self.offenses:
            old = self.offenses.pop(player_name)
            self._save_offenses()
            banned_until = old.get("ban_until", -1)
            if banned_until == -1:
                self.print_inf(f"玩家 {player_name} 已解除永久封禁")
            else:
                self.print_inf(f"玩家 {player_name} 已解除封禁")
        else:
            self.print_inf(f"玩家 {player_name} 未被封禁，无需解封")

    def _add_whitelist(self, player_name: str):
        try:
            self.game_ctrl.sendcmd(
                f'/tag "{player_name}" add {PERMANENT_TP_TAG}'
            )
            self.print_inf(f"玩家 {player_name} 已加入反传送白名单")
        except Exception as e:
            self.print_err(f"添加白名单失败: {e}")

    def _remove_whitelist(self, player_name: str):
        try:
            self.game_ctrl.sendcmd(
                f'/tag "{player_name}" remove {PERMANENT_TP_TAG}'
            )
            self.print_inf(f"玩家 {player_name} 已从反传送白名单移除")
        except Exception as e:
            self.print_err(f"移除白名单失败: {e}")

    def _on_menu_ban(self, player: Player, args: tuple) -> bool:
        target = args[0]
        duration_str = args[1] if len(args) > 1 else "永久"
        self._ban_player(target, duration_str)
        self.game_ctrl.say_to(player.name, f"§a已执行封禁: {target} ({duration_str})")
        return True

    def _on_menu_unban(self, player: Player, args: tuple) -> bool:
        target = args[0]
        self._unban_player(target)
        self.game_ctrl.say_to(player.name, f"§a已解封: {target}")
        return True

    def _on_menu_whitelist(self, player: Player, args: tuple) -> bool:
        target = args[0]
        self._add_whitelist(target)
        self.game_ctrl.say_to(player.name, f"§a已添加互传白名单: {target}")
        return True

    def _on_menu_unwhitelist(self, player: Player, args: tuple) -> bool:
        target = args[0]
        self._remove_whitelist(target)
        self.game_ctrl.say_to(player.name, f"§a已移除互传白名单: {target}")
        return True

    def _on_console_ban(self, args: list[str]):
        if len(args) < 1:
            self.print_war("用法: 封禁 <玩家名> [时间: 30m|1h|1d|永久]")
            return
        target = args[0]
        duration_str = args[1] if len(args) > 1 else "永久"
        self._ban_player(target, duration_str)

    def _on_console_unban(self, args: list[str]):
        if len(args) < 1:
            self.print_war("用法: 解封 <玩家名>")
            return
        self._unban_player(args[0])

    def _on_console_whitelist(self, args: list[str]):
        if len(args) < 1:
            self.print_war("用法: 反传送白名单 <玩家名>")
            return
        self._add_whitelist(args[0])

    def _on_console_unwhitelist(self, args: list[str]):
        if len(args) < 1:
            self.print_war("用法: 去除传送白名单 <玩家名>")
            return
        self._remove_whitelist(args[0])

    @timer_event(1, "AntiTeleport 传送检测")
    def _tick_check(self):
        try:
            threshold = self.cfg.get("传送阈值_格", 20)

            now = time.time()
            expired = [
                name for name, until in self.death_grace.items()
                if now >= until
            ]
            for name in expired:
                del self.death_grace[name]

            for player in self.game_ctrl.players:
                try:
                    self._check_player(player, threshold)
                except Exception as e:
                    self.print_err(f"检测玩家 {player.name} 时异常: {e}")
                    continue
        except Exception as e:
            self.print_err(f"_tick_check 外层异常: {e}")

    def _check_player(
        self,
        player: Player,
        threshold: float
    ):
        player_name = player.name

        try:
            if player.is_op():
                return
        except Exception as e:
            self.print_err(f"检查玩家 {player_name} OP 状态失败: {e}")

        try:
            pos_data = game_utils.getPos(player_name, timeout=3)
            cur_x = pos_data["position"]["x"]
            cur_y = pos_data["position"]["y"]
            cur_z = pos_data["position"]["z"]
            cur_dim = pos_data["dimension"]
        except Exception as e:
            fails = self.getpos_failures.get(player_name, 0) + 1
            self.getpos_failures[player_name] = fails
            if fails <= 2:
                self.print_err(f"获取玩家 {player_name} 坐标失败 (第{fails}次): {e}")
            return

        prev_fails = self.getpos_failures.pop(player_name, 0)
        if prev_fails > 0:
            self.last_positions[player_name] = (cur_x, cur_y, cur_z, cur_dim)
            self.print_inf(
                f"玩家 {player_name} 恢复位置追踪 "
                f"(之前失去响应 {prev_fails} 个检测周期)"
            )
            return

        last = self.last_positions.get(player_name)
        if last is None:
            self.last_positions[player_name] = (cur_x, cur_y, cur_z, cur_dim)
            return

        last_x, last_y, last_z, last_dim = last

        if cur_dim != last_dim:
            self.last_positions[player_name] = (
                cur_x, cur_y, cur_z, cur_dim
            )
            self.print_inf(
                f"玩家 {player_name} 跨维度传送："
                f"维度{last_dim}→{cur_dim}，已放行"
            )
            return

        if cur_dim == DIM_END:
            return

        dx = cur_x - last_x
        dz = cur_z - last_z
        distance = math.sqrt(dx * dx + dz * dz)

        if distance < threshold:
            self.last_positions[player_name] = (cur_x, cur_y, cur_z, cur_dim)
            return

        if self._check_permanent_tag(player_name):
            self.last_positions[player_name] = (cur_x, cur_y, cur_z, cur_dim)
            return

        try:
            cur_deaths = self._get_death_count(player_name)
            last_deaths = self.death_counts.get(player_name, -1)

            if last_deaths == -1:
                self.death_counts[player_name] = cur_deaths
            elif cur_deaths > last_deaths:
                self.death_counts[player_name] = cur_deaths
                self.death_grace[player_name] = time.time() + 10
                self.last_positions[player_name] = (cur_x, cur_y, cur_z, cur_dim)
                self.print_inf(
                    f"检测到玩家 {player_name} 死亡 "
                    f"(deathCount {last_deaths}→{cur_deaths})，给予宽限期"
                )
                return
            elif cur_deaths == last_deaths:
                pass
        except Exception as e:
            self.print_war(f"deathCount 查询异常 {player_name}: {e}")

        grace_until = self.death_grace.get(player_name)
        if grace_until is not None:
            if time.time() < grace_until:
                self.last_positions[player_name] = (
                    cur_x, cur_y, cur_z, cur_dim
                )
                self.print_inf(
                    f"玩家 {player_name} 处于死亡重生宽限期，已放行"
                )
                return
            else:
                del self.death_grace[player_name]

        has_legal = player_name in self.legal_tp_set
        if not has_legal:
            has_legal = self._check_mc_tag(player_name)

        if has_legal:
            self._clear_legal_tp(player_name)
            self.last_positions[player_name] = (cur_x, cur_y, cur_z, cur_dim)
            self.print_inf(
                f"玩家 {player_name} 合法传送，距离={distance:.1f}格"
            )
            return

        self._pullback_player(
            player_name, last_x, last_y, last_z
        )

        self.last_positions[player_name] = (last_x, last_y, last_z, last_dim)

        now = time.time()

        last_punish = self.punish_cooldown.get(player_name, 0)
        if now - last_punish < 5:
            return
        self.punish_cooldown[player_name] = now

        offense = self.offenses.get(
            player_name, {"count": 0, "ban_until": None}
        )
        offense["count"] = offense.get("count", 0) + 1
        self.offenses[player_name] = offense
        self._save_offenses()

        count = offense["count"]
        pos_info = (
            f"位移={distance:.1f}格(阈值={threshold}格) | "
            f"({last_x:.1f},{last_z:.1f})→({cur_x:.1f},{cur_z:.1f})"
        )

        if count == 1:
            msg = (
                "§e[反传送] 警告：检测到异常传送，"
                "请勿使用作弊工具！"
            )
            self.game_ctrl.sendcmd(f'/kick "{player_name}" {msg}')
            self.print_war(
                f"警告 {player_name} (第1次) | {pos_info}"
            )
        elif count == 2:
            offense["ban_until"] = now + 30 * 60
            self.offenses[player_name] = offense
            self._save_offenses()
            self.game_ctrl.sendcmd(
                f'/kick "{player_name}" '
                f'§c[反传送] 封禁30分钟：多次异常传送'
            )
            self.print_war(
                f"封禁30分钟 {player_name} (第2次) | {pos_info}"
            )
        elif count == 3:

            offense["ban_until"] = now + 60 * 60
            self.offenses[player_name] = offense
            self._save_offenses()
            self.game_ctrl.sendcmd(
                f'/kick "{player_name}" '
                f'§c[反传送] 封禁1小时：多次异常传送'
            )
            self.print_war(
                f"封禁1小时 {player_name} (第3次) | {pos_info}"
            )
        else:
            offense["ban_until"] = -1
            self.offenses[player_name] = offense
            self._save_offenses()
            self.game_ctrl.sendcmd(
                f'/kick "{player_name}" '
                f'§4[反传送] 永久封禁：多次异常传送'
            )
            self.print_war(
                f"永久封禁 {player_name} (第{count}次) | {pos_info}"
            )

    def _pullback_player(
        self,
        player_name: str,
        x: float,
        y: float,
        z: float
    ) -> bool:

        try:
            self.game_ctrl.sendcmd(
                f'/tp "{player_name}" {x:.1f} {y:.1f} {z:.1f}'
            )
            return True
        except Exception as e:
            self.print_err(f"拉回玩家 {player_name} 失败: {e}")
            return False

    def _check_permanent_tag(self, player_name: str) -> bool:
        try:
            resp = self.game_ctrl.sendcmd_with_resp(
                f'/tag "{player_name}" list',
                timeout=3
            )
            haystack = self._flatten_response(resp)
            return PERMANENT_TP_TAG in haystack
        except Exception as e:
            self.print_err(f"查询玩家 {player_name} 互传标签异常: {e}")
            return False

    def _check_mc_tag(self, player_name: str) -> bool:
        try:
            resp = self.game_ctrl.sendcmd_with_resp(
                f'/tag "{player_name}" list',
                timeout=3
            )
            haystack = self._flatten_response(resp)
            return LEGAL_TP_TAG in haystack
        except Exception as e:
            self.print_err(f"查询玩家 {player_name} MC 标签异常: {e}")
            return False

    @staticmethod
    def _flatten_response(resp) -> str:
        parts: list[str] = []
        seen: set[int] = set()

        def _walk(obj):
            if obj is None:
                return
            oid = id(obj)
            if oid in seen:
                return
            seen.add(oid)
            if isinstance(obj, str):
                parts.append(obj)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    _walk(item)
            elif isinstance(obj, dict):
                for v in obj.values():
                    _walk(v)
            elif hasattr(obj, "__dict__"):
                _walk(obj.__dict__)
            else:
                parts.append(str(obj))

        _walk(resp)
        return " ".join(parts)

    def _clear_legal_tp(self, player_name: str):
        self.legal_tp_set.discard(player_name)
        try:
            self.game_ctrl.sendcmd(
                f'/tag "{player_name}" remove {LEGAL_TP_TAG}'
            )
        except Exception as e:
            self.print_err(f"移除玩家 {player_name} MC 标签失败: {e}")

    def grant_legal_tp(self, player_name: str):
        self.legal_tp_set.add(player_name)
        try:
            self.game_ctrl.sendcmd(
                f'/tag "{player_name}" add {LEGAL_TP_TAG}'
            )
        except Exception as e:
            self.print_err(f"grant_legal_tp 添加 MC 标签失败: {e}")
        self.print_inf(f"玩家 {player_name} 被授予一次合法传送权限")

    def reset_offense(self, player_name: str):

        self.offenses.pop(player_name, None)
        self._save_offenses()
        self.print_inf(f"已重置玩家 {player_name} 的违规记录")

    def _save_offenses(self):
        try:
            self.offenses_file.write_text(
                json.dumps(self.offenses, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            self.print_err(f"保存违规记录失败: {e}")

    def _save_config(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(
                json.dumps(self.cfg, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            self.print_err(f"保存配置文件失败: {e}")

entry = plugin_entry(AntiTeleport)
