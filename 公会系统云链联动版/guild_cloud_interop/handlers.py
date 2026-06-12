"""Interactive guild menu handlers."""

# pylint: disable=protected-access

import json
import time
import uuid
from datetime import datetime

from tooldelta import Player, game_utils, fmts
from guild_cloud_interop.models import (
    GuildBase,
    GuildData,
    GuildMember,
    GuildRank,
    GuildTask,
    VaultItem,
)
from guild_cloud_interop.config import Config
from guild_cloud_interop.prompts import render_config_prompt, render_create_guild_prompt
from guild_cloud_interop.ui import ORION_BORDER, TITLE_PREFIX, format_page_footer
from guild_cloud_interop.validators import InputValidator


def _handle_effect(self, player: Player) -> bool:  # skipcq: PY-R1000
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    if self.guild_is_frozen(guild):
        self.show_guild_frozen(player, guild)
        return True
    if not guild.has_permission(player.name, "effect_buy"):
        player.show("§l§a公会 §d>> §r你没有购买公会效果权限")
        return True

    # 显示可选效果
    player.show("§l§a公会 §d>> §r可用效果列表:")

    for key, val in Config.EFFECTS_CONFIG.items():
        try:
            # 检查配置完整性
            if "name" not in val:
                fmts.print_err(f"效果配置错误: {key} 缺少 name 字段")
                continue

            if "costs" not in val:
                fmts.print_err(f"效果配置错误: {key} 缺少 costs 字段")
                continue

            purchased_lv = guild.purchased_effects.get(key)
            costs_str_list = []

            for lv, cost in val["costs"].items():
                if purchased_lv == lv:
                    color = "§b"
                else:
                    color = "§7"
                costs_str_list.append(f"{color}Lv{lv}:{cost}钻§r")

            costs_str = " ".join(costs_str_list)
            player.show(f"§r§f>> {val['name']} §r({costs_str})")

        except Exception as e:
            fmts.print_err(f"处理效果 {key} 时出错: {e}")
            continue

    player.show("§r§7>> 输入效果选择升级")
    choice = game_utils.waitMsg(player.name)

    effect_key = None
    for k, v in Config.EFFECTS_CONFIG.items():
        if v['name'] == choice:
            effect_key = k
            break

    if not effect_key:
        player.show("§c无效效果")
        return True

    selected = Config.EFFECTS_CONFIG[effect_key]

    # 判断钻石数量
    diamond_count = player.getItemCount("minecraft:diamond")
    player.show(f"§7当前钻石数量: {diamond_count}")

    player.show("§7请输入等级 (1/2/3)")
    lv_choice = game_utils.waitMsg(player.name)
    if not lv_choice.isdigit() or int(lv_choice) not in selected["costs"]:
        player.show("§c无效等级")
        return True

    lv_choice = int(lv_choice)
    cost = selected["costs"][lv_choice]

    if diamond_count < cost:
        player.show(f"§c钻石不足，{cost}钻石才能购买")
        return True

    # 扣除钻石
    self.game_ctrl.sendwocmd(
        f"clear {player.safe_name} minecraft:diamond 0 {cost}")

    # 保存公会已购买效果
    guilds = self.guild_manager.load_guilds(force_reload=True)
    guild_id = guild.guild_id
    if guild_id in guilds:
        guild = guilds[guild_id]
        guild.purchased_effects[effect_key] = lv_choice
        guild.add_log(
            f"{player.name} 为公会购买了 {selected['name']} 等级{lv_choice} 效果")
        self.guild_manager.save_guilds(guilds)
    else:
        player.show("§c保存失败，公会不存在")
        return True

    # 购买后立即给在线成员补发效果，后续由低频兜底刷新，避免周期性全量刷命令。
    for member in guild.members:
        if member.name in self.game_ctrl.allplayers:
            self._apply_guild_effects_to_player(
                member.name,
                guild=guild,
                force=True,
                effect_names={effect_key},
            )

    player.show(f"§a已激活效果: {selected['name']} 等级{lv_choice}")

    return True


def _handle_rankings(self, player: Player) -> bool:
    """处理公会排行榜"""
    player.show("§r========== §a公会排行榜§r ==========")
    player.show("§e1. §f等级排行")
    player.show("§e2. §f成员数量排行")
    player.show("§e3. §f贡献度排行")
    player.show("§e4. §f活跃度排行")
    player.show("§7输入选项序号:")

    choice = game_utils.waitMsg(player.name, timeout=30)

    if choice == "1":
        rankings = self.get_guild_rankings("level")
        title = "公会等级排行榜"

        def formatter(i, data):
            """Format one menu item for display."""
            return (
            f"§e{i}. §r{data[0].name} §7Lv.{data[1]}\n"
            f"   §7会长: §f{data[0].owner} §7| 成员: §a{len(data[0].members)}\n"
        )
    elif choice == "2":
        rankings = self.get_guild_rankings("members")
        title = "公会成员数排行榜"

        def formatter(i, data):
            """Format one menu item for display."""
            return (
            f"§e{i}. §r{data[0].name} §7成员: §a{data[1]}\n"
            f"   §7会长: §f{data[0].owner} §7| 等级: §e{data[0].level}\n"
        )
    elif choice == "3":
        rankings = self.get_guild_rankings("contribution")
        title = "公会贡献度排行榜"

        def formatter(i, data):
            """Format one menu item for display."""
            return (
            f"§e{i}. §r{data[0].name} §7贡献: §b{data[1]}\n"
            f"   §7会长: §f{data[0].owner} §7| 等级: §e{data[0].level}\n"
        )
    elif choice == "4":
        rankings = self.get_guild_rankings("activity")
        title = "公会活跃度排行榜"

        def formatter(i, data):
            """Format one menu item for display."""
            return (
            f"§e{i}. §r{
                data[0].name}\n" f"   §7会长: §f{
                data[0].owner} §7| 最近活跃: §a{
                    self._format_time_ago(
                        data[1])}\n")
    else:
        player.show("§c无效选项")
        return True

    if not rankings:
        player.show("§l§a公会 §d>> §r暂无公会数据")
        return True

    self._paginate_display(player, rankings, title, formatter)
    return True


def _format_time_ago(self, timestamp: float) -> str:
    """格式化时间差显示"""
    if timestamp == 0:
        return "从未"

    current_time = time.time()
    diff = current_time - timestamp

    if diff < 60:
        return "刚刚"
    elif diff < 3600:
        return f"{int(diff // 60)}分钟前"
    elif diff < 86400:
        return f"{int(diff // 3600)}小时前"
    else:
        return f"{int(diff // 86400)}天前"


def _handle_view_guild(self, player: Player) -> bool:
    """查看公会详细信息"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    level = guild.level
    exp = guild.exp
    required_exp = Config.GUILD_LEVEL_EXP.get(level + 1, "MAX")

    msg = f"§l§a{guild.name}§r §7(ID: {guild.guild_id[:8]}...)\n"
    msg += f"§7创建时间: §f{
        datetime.fromtimestamp(
            guild.create_time).strftime('%Y-%m-%d')}\n"
    msg += f"§7会长: §e{guild.owner}\n"
    msg += f"§7等级: §e{level} §7经验: §b{exp}/{required_exp}\n"
    msg += f"§7成员: §a{len(guild.members)}/{Config.MAX_GUILD_MEMBERS}\n"
    msg += f"§7仓库容量: §a{Config.VAULT_INITIAL_SLOTS} 格\n"

    if guild.announcement:
        msg += f"\n§e公告: §f{guild.announcement}\n"

    if guild.base:
        base = guild.base
        dim_name = Config.DIMENSION_NAMES.get(
            base.dimension, f"维度{base.dimension}")
        msg += f"\n§7据点: §f{dim_name} ({
            base.x:.1f}, {
            base.y:.1f}, {
            base.z:.1f})"

    player.show(msg)
    return True


def _handle_view_members(self, player: Player) -> bool:
    """查看成员列表"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    # 按职位和贡献度排序
    sorted_members = sorted(
        guild.members,
        key=lambda m: (
            ["owner", "deputy", "elder", "member"].index(m.rank.value),
            -m.contribution
        )
    )

    def formatter(i, member: GuildMember):
        """Format one menu item for display."""
        online = member.name in self.game_ctrl.allplayers
        online_status = "§a在线" if online else "§7离线"
        days_since_join = (time.time() - member.join_time) / 86400

        return (f"§e{i}. {member.rank.display_name} §f{member.name} "
                f"[{online_status}§f]\n"
                f"   §7贡献: §b{member.contribution} §7| "
                f"加入: §f{int(days_since_join)}天前\n")

    self._paginate_display(
        player, sorted_members, f"{
            guild.name} 成员列表", formatter)
    return True


def _handle_view_logs(self, player: Player) -> bool:
    """查看公会日志"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    msg = f"§r========== §a{guild.name} 日志§r ==========\n"
    if guild.logs:
        for log in guild.logs[-20:]:
            msg += f"§7{log}\n"
    else:
        msg += "§7暂无普通日志记录\n"

    if guild.has_permission(player.name, "audit_log"):
        msg += f"\n§r========== §a{guild.name} 审计日志§r ==========\n"
        if guild.audit_logs:
            for log in guild.audit_logs[-20:]:
                time_str = datetime.fromtimestamp(
                    log.timestamp).strftime("%m-%d %H:%M")
                target = f" §7| 目标: §f{log.target}" if log.target else ""
                detail = f" §7| 详情: §f{log.detail}" if log.detail else ""
                msg += (
                    f"§7[{time_str}] §f{log.action} §7| 操作者: §e{log.actor}"
                    f"{target}{detail} §7| 结果: §f{log.result}\n"
                )
        else:
            msg += "§7暂无审计日志记录\n"

    player.show(msg)
    return True


def _handle_announcement(self, player: Player) -> bool:
    """处理公会公告"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    # 显示当前公告
    if guild.announcement:
        player.show(f"§l§a公会公告§r\n§f{guild.announcement}")
    else:
        player.show("§l§a公会 §d>> §r当前没有公告")

    # 检查权限
    if not guild.has_permission(player.name, "announce"):
        return True

    player.show("§7输入 '设置' 来修改公告，其他任意键返回")
    choice = game_utils.waitMsg(player.name, timeout=20)

    if choice == "设置":
        player.show("§l§a公会 §d>> §r请输入新的公告内容:")
        player.show("§7要求: 不超过200个字符，不能为空")
        new_announcement = game_utils.waitMsg(player.name, timeout=60)

        # 使用新的输入验证
        is_valid, error_msg = InputValidator.validate_announcement(
            new_announcement)
        if not is_valid:
            player.show(f"§l§a公会 §d>> §r{error_msg}")
            return True

        try:
            guilds = self.guild_manager.load_guilds(force_reload=True)
            guild_data = guilds.get(guild.guild_id)
            if not guild_data:
                player.show("§l§a公会 §d>> §r公会数据异常")
                return True

            guild_data.announcement = new_announcement
            guild_data.add_log(f"{player.name} 更新了公告")
            self.guild_manager.save_guilds(guilds)
            player.show("§l§a公会 §d>> §r公告已更新")

            # 通知在线成员
            message = "§l§a公会 §d>> §r公告已更新，输入 .公会 公告 查看"
            for member in guild_data.members:
                if member.name in self.game_ctrl.allplayers:
                    self.game_ctrl.sendcmd(
                        f'/tellraw {member.name} {{"rawtext":[{{"text":"{message}"}}]}}'
                    )
        except Exception as e:
            player.show("§l§a公会 §d>> §r更新公告失败")
            fmts.print_err(f"更新公告时出错：{e}")

    return True


def _handle_tasks(self, player: Player) -> bool:  # skipcq: PY-R1000
    """处理公会任务系统"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    if self.guild_is_frozen(guild):
        self.show_guild_frozen(player, guild)
        return True

    while True:
        latest_guild = self.guild_manager.get_guild_by_player(
            player.name, force_reload=True)
        if latest_guild:
            guild = latest_guild

        player.show("§r========== §a公会任务§r ==========")

        # 显示活跃任务统计
        active_tasks = [t for t in guild.tasks if not t.completed]
        completed_tasks = [t for t in guild.tasks if t.completed]

        player.show(
            f"§7活跃任务: §e{
                len(active_tasks)} §7| 已完成: §a{
                len(completed_tasks)}")
        can_manage_legacy = guild.has_permission(player.name, "task_manage")
        can_create = guild.has_permission(
            player.name, "task_create") or can_manage_legacy
        can_delete = guild.has_permission(
            player.name, "task_delete") or can_manage_legacy
        can_complete = guild.has_permission(
            player.name, "task_complete") or can_manage_legacy
        can_manage = can_delete or can_complete
        can_auto = (
            can_create
            and getattr(Config, "GUILD_TASK_CONFIG", {}).get("启用自动任务模板", True)
        )

        menu_options = [
            ("查看", "查看所有任务", True),
            ("参与", "参与任务", len(active_tasks) > 0),
            ("创建", "创建新任务", can_create),
            ("自动", "生成自动任务模板", can_auto),
            ("管理", "管理任务", can_manage),
            ("退出", "退出任务系统", True)
        ]

        available_options = [(cmd, desc)
                             for cmd, desc, cond in menu_options if cond]

        for cmd, desc in available_options:
            player.show(f"§e● {cmd} §7- {desc}")

        player.show("§7输入选项:")
        choice = game_utils.waitMsg(player.name, timeout=30)

        if choice == "查看":
            self._handle_view_tasks(player, guild)
        elif choice == "参与" and len(active_tasks) > 0:
            self._handle_join_task(player, guild)
        elif choice == "创建" and can_create:
            self._handle_create_task(player, guild)
        elif choice == "自动" and can_auto:
            self._handle_generate_auto_tasks(player, guild)
        elif choice == "管理" and can_manage:
            self._handle_manage_tasks(player, guild)
        elif choice == "退出" or choice is None:
            break
        else:
            player.show("§c无效选项")

    return True


def _handle_view_tasks(self, player: Player, guild: GuildData) -> bool:
    """查看任务列表"""
    if not guild.tasks:
        player.show("§l§a公会任务 §d>> §r暂无任务")
        return True

    def formatter(i, task: GuildTask):
        """Format one menu item for display."""
        status = "§a已完成" if task.completed else f"§e进行中 ({
            task.current_count}/{
            task.target_count})"
        progress_bar = self._create_progress_bar(
            task.current_count, task.target_count)

        deadline_str = ""
        if task.deadline > 0:
            remaining = task.deadline - time.time()
            if remaining > 0:
                deadline_str = f" §7| 剩余: §f{
                    self._format_time_duration(remaining)}"
            else:
                deadline_str = " §7| §c已过期"

        return (
            f"§e{i}. §f{task.name} [{status}§f]\n"
            f"   §7{task.description}\n"
            f"   {progress_bar}{deadline_str}\n"
            f"   §7奖励: §b{task.reward_contribution}贡献点 "
            f"§7+ §e{task.reward_exp}经验\n"
        )

    self._paginate_display(player, guild.tasks, "公会任务列表", formatter)
    return True


def _handle_join_task(self, player: Player, guild: GuildData) -> bool:
    """参与任务"""
    active_tasks = [t for t in guild.tasks if not t.completed]

    if not active_tasks:
        player.show("§l§a公会任务 §d>> §r暂无可参与的任务")
        return True

    def formatter(i, task: GuildTask):
        """Format one menu item for display."""
        status = f"§e进行中 ({task.current_count}/{task.target_count})"
        is_participant = player.name in task.participants
        participant_status = " §a[已参与]" if is_participant else " §7[未参与]"

        return (
            f"§e{i}. §f{
                task.name} [{status}§f]{participant_status}\n" f"   §7{
                task.description}\n" f"   §7奖励: §b{
                task.reward_contribution}贡献点 §7+ §e{
                    task.reward_exp}经验\n")

    idx = self._paginate_display(
        player, active_tasks, "选择参与任务", formatter, True)
    if idx is None:
        return True

    task = active_tasks[idx]

    if player.name in task.participants:
        player.show("§l§a公会任务 §d>> §r你已经参与了这个任务")
        return True

    # 加入任务
    guilds = self.guild_manager.load_guilds(force_reload=True)
    guild = guilds.get(guild.guild_id)
    if guild:
        for t in guild.tasks:
            if t.task_id == task.task_id:
                t.participants.append(player.name)
                guild.add_log(f"{player.name} 参与了任务: {t.name}")
                break

        self.guild_manager.save_guilds(guilds)
        player.show(f"§l§a公会任务 §d>> §r已参与任务: {task.name}")

    return True


def _handle_create_task(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """创建新任务"""
    if not (
        guild.has_permission(
            player.name,
            "task_create") or guild.has_permission(
            player.name,
            "task_manage")):
        player.show("§l§a公会任务 §d>> §r你没有创建任务权限")
        return True

    task_config = getattr(Config, "GUILD_TASK_CONFIG", {})
    max_name_len = int(task_config.get("创建任务名称最大长度", 20))
    max_desc_len = int(task_config.get("创建任务描述最大长度", 100))
    max_target_count = int(task_config.get("创建任务目标数量上限", 10000))
    max_contribution_reward = int(task_config.get("创建任务贡献奖励上限", 1000))
    max_exp_reward = int(task_config.get("创建任务经验奖励上限", 1000))

    player.show("§r========== §a创建任务§r ==========")
    player.show("§7任务类型:")
    player.show("§e1. §f收集任务 (收集指定物品)")
    player.show("§e2. §f建造任务 (放置指定方块)")
    player.show("§e3. §f贸易任务 (进行仓库交易)")
    player.show("§7输入任务类型序号:")

    task_type_choice = game_utils.waitMsg(player.name, timeout=30)

    if task_type_choice == "1":
        task_type = "collect"
        type_name = "收集任务"
    elif task_type_choice == "2":
        task_type = "build"
        type_name = "建造任务"
    elif task_type_choice == "3":
        task_type = "trade"
        type_name = "贸易任务"
    else:
        player.show("§c无效的任务类型")
        return True

    # 获取任务名称
    player.show(f"§l§a创建{type_name} §d>> §r请输入任务名称:")
    task_name = game_utils.waitMsg(player.name, timeout=30)
    if not task_name or len(task_name) > max_name_len:
        player.show("§c任务名称无效或过长")
        return True

    # 获取任务描述
    player.show("§l§a创建任务 §d>> §r请输入任务描述:")
    description = game_utils.waitMsg(player.name, timeout=60)
    if not description or len(description) > max_desc_len:
        player.show("§c任务描述无效或过长")
        return True

    # 获取目标
    if task_type == "collect":
        player.show("§l§a创建任务 §d>> §r请输入目标物品名称:")
        player.show("§7支持中文名称，如: 钻石、铁锭、金块等")
        player.show("§7也支持英文ID，如: minecraft:diamond")

        user_input = game_utils.waitMsg(player.name, timeout=30)
        if not user_input:
            player.show("§c输入为空")
            return True

        # 使用智能匹配查找物品ID
        item_id, suggestions = self.item_matcher.validate_and_suggest(
            user_input)

        if not item_id:
            player.show("§c未找到匹配的物品")
            if suggestions:
                player.show("§7您是否想要:")
                for i, suggestion in enumerate(suggestions[:3], 1):
                    player.show(f"§e{i}. §f{suggestion}")
            return True

        target = item_id
        chinese_name = self.item_matcher.get_chinese_name(item_id)
        player.show(f"§l§a创建任务 §d>> §r目标物品: §f{chinese_name}")

    elif task_type == "build":
        player.show("§l§a创建任务 §d>> §r请输入目标方块名称:")
        player.show("§7支持中文名称，如: 石头、圆石、橡木等")
        player.show("§7也支持英文ID，如: minecraft:stone")

        user_input = game_utils.waitMsg(player.name, timeout=30)
        if not user_input:
            player.show("§c输入为空")
            return True

        # 使用智能匹配查找方块ID
        block_id, suggestions = self.item_matcher.validate_and_suggest(
            user_input)

        if not block_id:
            player.show("§c未找到匹配的方块")
            if suggestions:
                player.show("§7您是否想要:")
                for i, suggestion in enumerate(suggestions[:3], 1):
                    player.show(f"§e{i}. §f{suggestion}")
            return True

        target = block_id
        chinese_name = self.item_matcher.get_chinese_name(block_id)
        player.show(f"§l§a创建任务 §d>> §r目标方块: §f{chinese_name}")

    else:  # trade
        target = "trade_count"

    # 获取目标数量
    player.show("§l§a创建任务 §d>> §r请输入目标数量:")
    count_str = game_utils.waitMsg(player.name, timeout=30)
    if not count_str or not count_str.isdigit():
        player.show("§c无效的数量")
        return True

    target_count = int(count_str)
    if target_count <= 0 or target_count > max_target_count:
        player.show(f"§c数量必须在1-{max_target_count}之间")
        return True

    # 获取奖励
    player.show("§l§a创建任务 §d>> §r请输入贡献点奖励:")
    contrib_str = game_utils.waitMsg(player.name, timeout=30)
    if not contrib_str or not contrib_str.isdigit():
        player.show("§c无效的贡献点数量")
        return True

    reward_contribution = int(contrib_str)
    if reward_contribution < 0 or reward_contribution > max_contribution_reward:
        player.show(f"§c贡献点奖励必须在0-{max_contribution_reward}之间")
        return True

    player.show("§l§a创建任务 §d>> §r请输入经验奖励:")
    exp_str = game_utils.waitMsg(player.name, timeout=30)
    if not exp_str or not exp_str.isdigit():
        player.show("§c无效的经验数量")
        return True

    reward_exp = int(exp_str)
    if reward_exp < 0 or reward_exp > max_exp_reward:
        player.show(f"§c经验奖励必须在0-{max_exp_reward}之间")
        return True

    task_id = uuid.uuid4().hex[:8]
    new_task = GuildTask(
        task_id=task_id,
        name=task_name,
        description=description,
        task_type=task_type,
        target=target,
        target_count=target_count,
        reward_contribution=reward_contribution,
        reward_exp=reward_exp
    )

    # 保存任务
    guilds = self.guild_manager.load_guilds(force_reload=True)
    guild = guilds.get(guild.guild_id)
    if guild:
        guild.tasks.append(new_task)
        guild.add_log(f"{player.name} 创建了任务: {task_name}")
        self.guild_manager.save_guilds(guilds)
        player.show(f"§l§a公会任务 §d>> §r任务 '{task_name}' 创建成功！")

    return True


def _handle_generate_auto_tasks(
        self,
        player: Player,
        guild: GuildData) -> bool:
    """按配置模板生成自动任务"""
    if not (
        guild.has_permission(
            player.name,
            "task_create") or guild.has_permission(
            player.name,
            "task_manage")):
        player.show("§l§a公会任务 §d>> §r你没有生成任务权限")
        return True

    task_config = getattr(Config, "GUILD_TASK_CONFIG", {})
    if not task_config.get("启用自动任务模板", True):
        player.show("§l§a公会任务 §d>> §r自动任务模板未启用")
        return True

    templates = task_config.get("自动任务模板列表", [])
    if not templates:
        player.show("§l§a公会任务 §d>> §r暂无自动任务模板")
        return True

    guilds = self.guild_manager.load_guilds(force_reload=True)
    latest_guild = guilds.get(guild.guild_id)
    if not latest_guild:
        player.show("§l§a公会任务 §d>> §r公会数据异常")
        return True

    active_auto_tasks = [
        task for task in latest_guild.tasks
        if not task.completed and task.task_id.startswith("auto-")
    ]
    max_active = int(task_config.get("自动任务最大同时存在数量", 6))
    if len(active_auto_tasks) >= max_active > 0:
        player.show(f"§l§a公会任务 §d>> §r自动任务数量已达上限 {max_active}")
        return True

    generate_count = int(task_config.get("每次生成自动任务数量", 3))
    if max_active > 0:
        generate_count = min(
            generate_count,
            max_active -
            len(active_auto_tasks))
    if generate_count <= 0:
        player.show("§l§a公会任务 §d>> §r无需生成新的自动任务")
        return True

    active_keys = {
        (task.name, task.task_type, task.target)
        for task in latest_guild.tasks
        if not task.completed
    }
    candidates = [
        template for template in templates
        if (
            template.get("name"),
            template.get("task_type"),
            template.get("target"),
        ) not in active_keys
    ]
    if not candidates:
        player.show("§l§a公会任务 §d>> §r所有自动任务模板都已存在")
        return True

    now = time.time()
    deadline_seconds = int(task_config.get("自动任务默认有效期秒", 172800))
    deadline = now + deadline_seconds if deadline_seconds > 0 else 0
    created_tasks = []
    for template in candidates[:generate_count]:
        task = GuildTask(
            task_id=f"auto-{uuid.uuid4().hex[: 8]} ",
            name=str(template.get("name", "自动任务"))[: 20],
            description=str(template.get("description", ""))[: 100],
            task_type=str(template.get("task_type", "trade")),
            target=str(template.get("target", "trade_count")),
            target_count=max(1, int(template.get("target_count", 1))),
            reward_exp=max(0, int(template.get("reward_exp", 0))),
            reward_contribution=max(
                0, int(template.get("reward_contribution", 0))),
            create_time=now, deadline=deadline,)
        latest_guild.tasks.append(task)
        created_tasks.append(task)

    latest_guild.add_log(f"{player.name} 生成了 {len(created_tasks)} 个自动任务")
    latest_guild.add_audit_log(
        "task_auto_generate",
        player.name,
        detail=",".join(task.name for task in created_tasks),
    )
    self.guild_manager.save_guilds(guilds)
    player.show(f"§l§a公会任务 §d>> §r已生成 {len(created_tasks)} 个自动任务")
    return True


def _handle_manage_tasks(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """管理任务"""
    can_manage_legacy = guild.has_permission(player.name, "task_manage")
    can_delete = guild.has_permission(
        player.name, "task_delete") or can_manage_legacy
    can_complete = guild.has_permission(
        player.name, "task_complete") or can_manage_legacy

    if not can_delete and not can_complete:
        player.show("§l§a公会任务 §d>> §r你没有管理任务权限")
        return True

    player.show("§r========== §a任务管理§r ==========")
    if can_delete:
        player.show("§e1. §f删除任务")
    if can_complete:
        player.show("§e2. §f完成任务")
    player.show("§7输入选项序号:")

    choice = game_utils.waitMsg(player.name, timeout=30)

    if choice == "1" and can_delete:
        if not guild.tasks:
            player.show("§l§a公会任务 §d>> §r暂无任务")
            return True
        # 删除任务

        def formatter(i, task: GuildTask):
            """Format one menu item for display."""
            status = "§a已完成" if task.completed else "§e进行中"
            return f"§e{i}. §f{
                task.name} [{status}§f]\n   §7{
                task.description}\n"

        idx = self._paginate_display(
            player, guild.tasks, "选择删除任务", formatter, True)
        if idx is not None:
            task = guild.tasks[idx]
            player.show(f"§l§a任务管理 §d>> §r确认删除任务 '{task.name}'？输入 '确认' 继续")
            confirm = game_utils.waitMsg(player.name, timeout=20)

            if confirm == "确认":
                guilds = self.guild_manager.load_guilds(force_reload=True)
                guild = guilds.get(guild.guild_id)
                if guild and idx < len(guild.tasks):
                    removed_task = guild.tasks.pop(idx)
                    guild.add_log(f"{player.name} 删除了任务: {removed_task.name}")
                    guild.add_audit_log("task_delete", player.name,
                                        detail=removed_task.name)
                    self.guild_manager.save_guilds(guilds)
                    player.show(
                        f"§l§a任务管理 §d>> §r任务 '{
                            removed_task.name}' 已删除")

    elif choice == "2" and can_complete:
        # 强制完成任务
        active_tasks = [t for t in guild.tasks if not t.completed]
        if not active_tasks:
            player.show("§l§a任务管理 §d>> §r暂无进行中的任务")
            return True

        def formatter(i, task: GuildTask):
            """Format one menu item for display."""
            return f"§e{i}. §f{
                task.name} §7({
                task.current_count}/{
                task.target_count})\n   §7{
                task.description}\n"

        idx = self._paginate_display(
            player, active_tasks, "选择完成任务", formatter, True)
        if idx is not None:
            task = active_tasks[idx]
            player.show(f"§l§a任务管理 §d>> §r确认强制完成任务 '{task.name}'？输入 '确认' 继续")
            confirm = game_utils.waitMsg(player.name, timeout=20)

            if confirm == "确认":
                guilds = self.guild_manager.load_guilds(force_reload=True)
                guild = guilds.get(guild.guild_id)
                if guild:
                    for t in guild.tasks:
                        if t.task_id == task.task_id:
                            t.completed = True
                            t.current_count = t.target_count
                            guild.add_log(f"{player.name} 强制完成了任务: {t.name}")
                            guild.add_audit_log("task_force_complete",
                                                player.name, detail=t.name)
                            break

                    self.guild_manager.save_guilds(guilds)
                    player.show(f"§l§a任务管理 §d>> §r任务 '{task.name}' 已完成")
    else:
        player.show("§c无效选项")

    return True


def _handle_manage_members(self, player: Player) -> bool:
    """管理公会成员"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    member = guild.get_member(player.name) if guild else None

    if not guild or not member or not any(
        guild.has_permission(player.name, permission)
        for permission in ("kick", "set_rank", "transfer_owner", "join_queue")
    ):
        player.show("§l§a公会 §d>> §r你没有管理权限")
        return True

    player.show("§r========== §a成员管理§r ==========")
    options = [
        ("1", "踢出成员", guild.has_permission(player.name, "kick")),
        ("2", "设置职位", guild.has_permission(player.name, "set_rank")),
        ("3", "转让会长", guild.has_permission(player.name, "transfer_owner")),
        ("4", "申请队列", guild.has_permission(player.name, "join_queue")),
    ]
    for key, label, enabled in options:
        if enabled:
            player.show(f"§e{key}. §f{label}")
    player.show("§7输入选项序号，q 返回")

    choice = game_utils.waitMsg(player.name, timeout=30)

    if choice == "1" and guild.has_permission(player.name, "kick"):
        return self._handle_kick_member(player)
    elif choice == "2" and guild.has_permission(player.name, "set_rank"):
        return self._handle_set_rank(player)
    elif choice == "3" and guild.has_permission(player.name, "transfer_owner"):
        return self._handle_transfer_ownership(player)
    elif choice == "4" and guild.has_permission(player.name, "join_queue"):
        return self._handle_join_request_queue(player, guild)

    return True


def _notify_join_request_admins(
        self,
        guild: GuildData,
        applicant_name: str) -> None:
    """通知在线的申请队列处理人。"""
    if not getattr(
        Config,
        "GUILD_JOIN_REQUEST_CONFIG",
        {}).get(
        "申请提交后通知在线管理员",
            True):
        return

    for member in guild.members:
        if (
            member.name in self.game_ctrl.allplayers
            and guild.has_permission(member.name, "join_queue")
        ):
            message = (
                f"§l§a公会 §d>> §r§e{applicant_name} "
                f"§f申请加入公会 §e{guild.name}\\n"
                "§f请在成员管理的 §a申请队列 §f中处理"
            )
            self.game_ctrl.sendcmd(
                f'/tellraw {member.name} {{"rawtext":[{{"text":"{message}"}}]}}'
            )


def _handle_join_request_queue(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """处理加入申请队列"""
    if not guild.has_permission(player.name, "join_queue"):
        player.show("§l§a公会 §d>> §r你没有处理申请队列权限")
        return True

    pending_requests = guild.pending_join_requests()
    if not pending_requests:
        player.show("§l§a公会 §d>> §r暂无待处理加入申请")
        return True

    def formatter(i, request):
        """Format one menu item for display."""
        age = self._format_time_duration(time.time() - request.create_time)
        reason = request.reason or "无"
        return (
            f"§e{i}. §f{request.player_name}\n"
            f"   §7理由: §f{reason} §7| 提交: §f{age}前\n"
        )

    idx = self._paginate_display(
        player,
        pending_requests,
        "加入申请队列",
        formatter,
        True)
    if idx is None:
        return True

    selected = pending_requests[idx]
    player.show(f"§l§a公会 §d>> §r处理 §e{selected.player_name} §r的加入申请")
    player.show("§e1. §f同意")
    player.show("§e2. §f拒绝")
    player.show("§7输入选项序号:")
    choice = game_utils.waitMsg(player.name, timeout=30)
    approved = choice in ("1", "同意", "批准")
    rejected = choice in ("2", "拒绝")
    if not approved and not rejected:
        player.show("§l§a公会 §d>> §r操作已取消")
        return True

    guilds = self.guild_manager.load_guilds(force_reload=True)
    latest_guild = guilds.get(guild.guild_id)
    if not latest_guild:
        player.show("§l§a公会 §d>> §r公会数据异常")
        return True

    if approved and len(latest_guild.members) >= Config.MAX_GUILD_MEMBERS:
        latest_guild.resolve_join_request(
            selected.player_name,
            player.name,
            False,
            result_reason="公会已满员",
        )
        self.guild_manager.save_guilds(guilds)
        player.show("§l§a公会 §d>> §r公会已满员，已拒绝该申请")
        return True

    if not latest_guild.resolve_join_request(
        selected.player_name,
        player.name,
        approved,
        result_reason="管理员处理",
    ):
        player.show("§l§a公会 §d>> §r申请已不存在或已过期")
        return True

    if approved:
        new_member = GuildMember(
            name=selected.player_name,
            rank=GuildRank.MEMBER,
            join_time=time.time(),
        )
        latest_guild.members.append(new_member)
        latest_guild.add_log(
            f"{selected.player_name} 加入公会 (审核人: {player.name})")
        self.guild_manager.cache_player_guild(
            selected.player_name, latest_guild.guild_id)

    self.guild_manager.save_guilds(guilds)
    result_text = "已同意" if approved else "已拒绝"
    player.show(f"§l§a公会 §d>> §r{result_text} {selected.player_name} 的加入申请")

    if selected.player_name in self.game_ctrl.allplayers:
        message = (
            f"§l§a公会 §d>> §r你的公会申请已通过，已加入 §e{latest_guild.name}"
            if approved
            else f"§l§a公会 §d>> §r你加入 §e{latest_guild.name} §r的申请被拒绝"
        )
        self.game_ctrl.sendcmd(
            f'/tellraw {selected.player_name} {{"rawtext":[{{"text":"{message}"}}]}}'
        )

    if approved and getattr(
        Config,
        "GUILD_JOIN_REQUEST_CONFIG",
        {}).get(
        "批准后通知全体在线成员",
            True):
        for member in latest_guild.members:
            if (
                member.name in self.game_ctrl.allplayers
                and member.name != selected.player_name
            ):
                message = f"§l§a公会 §d>> §r§e{selected.player_name}§r 加入了公会"
                self.game_ctrl.sendcmd(
                    f'/tellraw {member.name} {{"rawtext":[{{"text":"{message}"}}]}}'
                )

    return True


def _handle_set_rank(self, player: Player) -> bool:
    """设置成员职位"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        return True
    if not guild.has_permission(player.name, "set_rank"):
        player.show("§l§a公会 §d>> §r你没有设置成员职位权限")
        return True

    # 过滤可管理的成员
    manageable_members = [
        m for m in guild.members
        if guild.can_manage_member(player.name, m.name)
    ]

    if not manageable_members:
        player.show("§l§a公会 §d>> §r没有可管理的成员")
        return True

    def formatter(i, m):
        """Format one menu item for display."""
        return f"§e{i}. {m.rank.display_name} §f{m.name}\n"
    idx = self._paginate_display(
        player,
        manageable_members,
        "选择成员",
        formatter,
        True)

    if idx is None:
        return True

    target_member = manageable_members[idx]

    # 选择新职位
    player.show("§r========== §a设置职位§r ==========")
    player.show("§e1. §6副会长")
    player.show("§e2. §e长老")
    player.show("§e3. §a成员")
    player.show("§7输入选项序号")

    rank_choice = game_utils.waitMsg(player.name, timeout=30)
    rank_map = {
        "1": GuildRank.DEPUTY,
        "2": GuildRank.ELDER,
        "3": GuildRank.MEMBER}

    new_rank = rank_map.get(rank_choice)
    if new_rank and self.guild_manager.set_member_rank(
            guild, target_member.name, new_rank):
        player.show(
            f"§l§a公会 §d>> §r已将 {
                target_member.name} 的职位设置为 {
                new_rank.display_name}")

    return True


def _handle_donation(self, player: Player) -> bool:
    """处理物品捐献"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    if self.guild_is_frozen(guild):
        self.show_guild_frozen(player, guild)
        return True

    player.show("§l§a公会捐献§r")
    player.show("§7支持捐献的物品类型:")
    player.show("§e钻石 §7- 50贡献/个")
    player.show("§e绿宝石 §7- 25贡献/个")
    player.show("§e金锭 §7- 10贡献/个")
    player.show("§e铁锭 §7- 5贡献/个")
    player.show("§e下界合金锭 §7- 200贡献/个")
    player.show("§e远古残骸 §7- 150贡献/个")
    player.show("§7以及其他有价值的物品...")
    player.show("§7请输入要捐献的物品名称 (支持中文名称):")

    user_input = game_utils.waitMsg(player.name, timeout=30)

    if not user_input or user_input.lower() == 'q':
        return True

    # 使用智能匹配查找物品ID
    item_id, suggestions = self.item_matcher.validate_and_suggest(user_input)

    if not item_id:
        player.show("§l§a公会捐献 §d>> §r未找到匹配的物品")
        if suggestions:
            player.show("§7您是否想要:")
            for i, suggestion in enumerate(suggestions[:3], 1):
                player.show(f"§e{i}. §f{suggestion}")
        return True

    # 获取物品的贡献点价值
    contrib_per_item = guild.get_item_value(item_id)
    exp_per_item = contrib_per_item * 0.5  # 经验为贡献点的一半

    chinese_name = self.item_matcher.get_chinese_name(item_id)
    player.show(f"§l§a公会捐献 §d>> §r选择物品: §f{chinese_name}")
    player.show(f"§7价值: §e{contrib_per_item}贡献点/个 §7+ §b{exp_per_item}经验/个")

    player.show(f"§7你有 {player.getItemCount(item_id)} 个{chinese_name}")
    player.show("§7输入要捐献的数量:")

    amount_str = game_utils.waitMsg(player.name, timeout=30)
    if not amount_str or not amount_str.isdigit():
        return True

    amount = int(amount_str)
    if amount <= 0 or amount > player.getItemCount(item_id):
        player.show("§l§a公会 §d>> §r数量无效")
        return True

    self.game_ctrl.sendwocmd(f"clear {player.name} {item_id} 0 {amount}")
    exp, contribution = self.guild_apply_reward_multipliers(
        int(amount * exp_per_item),
        amount * contrib_per_item,
    )

    # 重新加载公会数据并更新经验值
    guilds = self.guild_manager.load_guilds(force_reload=True)
    guild_id = guild.guild_id

    if guild_id in guilds:
        # 更新贡献与公会经验
        latest_guild = guilds[guild_id]
        member = latest_guild.get_member(player.name)
        if member:
            member.contribution += contribution
            latest_guild.stats.total_contribution += contribution
        latest_guild.exp += exp
        latest_guild.add_log(f"{player.name} 捐献了 {amount} 个{chinese_name}")

        self.guild_manager.save_guilds(guilds)
        player.show(f"§l§a公会 §d>> §r捐献成功！获得 {contribution} 贡献度，公会获得 {exp} 经验")
    else:
        player.show("§l§a公会 §d>> §r捐献失败，公会数据异常")
        fmts.print_err(f"捐献失败: 公会ID {guild_id} 不存在于加载的数据中")

    return True


def _handle_vault(self, player: Player) -> bool:  # skipcq: PY-R1000
    """处理公会仓库"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    if self.guild_is_frozen(guild):
        self.show_guild_frozen(player, guild)
        return True

    if not guild.has_permission(player.name, "vault"):
        player.show("§l§a公会仓库 §d>> §r你没有使用仓库权限")
        return True

    while True:
        latest_guild = self.guild_manager.get_guild_by_player(
            player.name, force_reload=True)
        if latest_guild:
            guild = latest_guild

        player.show("§r========== §a公会仓库§r ==========")
        max_slots = Config.VAULT_INITIAL_SLOTS  # 固定10000格
        player.show(f"§7容量: §a{len(guild.vault_items)}/{max_slots}")

        member = guild.get_member(player.name)
        if member:
            player.show(f"§7你的贡献点: §e{member.contribution}")

        can_buy = guild.has_permission(player.name, "vault_buy")
        can_sell = guild.has_permission(player.name, "vault_sell")
        can_cancel = (
            getattr(Config, "GUILD_VAULT_CONFIG", {}).get("启用撤回出售", True)
            and (
                guild.has_permission(player.name, "vault_cancel_own")
                or guild.has_permission(player.name, "vault_cancel_any")
            )
        )
        can_view_logs = getattr(
            Config, "GUILD_VAULT_CONFIG", {}).get(
            "启用交易日志", True)
        can_settings = guild.has_permission(player.name, "vault_settings")

        menu_options = [
            ("查看", "查看仓库物品", True),
            ("购买", "购买仓库物品", can_buy),
            ("出售", "出售物品到仓库", can_sell),
            ("撤回", "撤回已上架物品", can_cancel),
            ("日志", "查看仓库交易日志", can_view_logs),
            ("设置", "设置仓库物品价值", can_settings),
            ("退出", "退出仓库", True)
        ]

        available_options = [(cmd, desc)
                             for cmd, desc, cond in menu_options if cond]

        for cmd, desc in available_options:
            player.show(f"§e● {cmd} §7- {desc}")

        player.show("§7输入选项:")
        choice = game_utils.waitMsg(player.name, timeout=30)

        if choice == "查看":
            self._handle_vault_view(player, guild)
        elif choice == "购买" and can_buy:
            self._handle_vault_buy(player, guild)
        elif choice == "出售" and can_sell:
            self._handle_vault_sell(player, guild)
        elif choice == "撤回" and can_cancel:
            self._handle_vault_cancel(player, guild)
        elif choice == "日志" and can_view_logs:
            self._handle_vault_logs(player, guild)
        elif choice == "设置" and can_settings:
            self._handle_vault_settings(player, guild)
        elif choice == "退出" or choice is None:
            break
        else:
            player.show("§c无效选项")

    return True


def _handle_vault_view(self, player: Player, guild: GuildData) -> bool:
    """查看仓库物品"""
    if not guild.vault_items:
        player.show("§l§a公会仓库 §d>> §r仓库为空")
        return True

    def formatter(i, item: VaultItem):
        # 获取物品显示名称
        """Format one menu item for display."""
        item_name = self._get_item_display_name(item.item_id)
        time_str = datetime.fromtimestamp(
            item.timestamp).strftime("%m-%d %H:%M")
        return (f"§e{i}. §f{item_name} §7x{item.count}\n"
                f"   §7价格: §e{item.price}贡献点 §7| 卖家: §a{item.seller}\n"
                f"   §7时间: §f{time_str}\n")

    self._paginate_display(player, guild.vault_items, "仓库物品", formatter)
    return True


def _handle_vault_buy(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """购买仓库物品"""
    if not guild.has_permission(player.name, "vault_buy"):
        player.show("§l§a公会仓库 §d>> §r你没有购买仓库物品权限")
        return True

    if not guild.vault_items:
        player.show("§l§a公会仓库 §d>> §r仓库为空")
        return True

    member = guild.get_member(player.name)
    if not member:
        return True

    def formatter(i, item: VaultItem):
        """Format one menu item for display."""
        item_name = self._get_item_display_name(item.item_id)
        time_str = datetime.fromtimestamp(
            item.timestamp).strftime("%m-%d %H:%M")
        affordable = "§a可购买" if member.contribution >= item.price else "§c贡献点不足"
        return (f"§e{i}. §f{item_name} §7x{item.count}\n"
                f"   §7价格: §e{item.price}贡献点 §7| {affordable}\n"
                f"   §7卖家: §a{item.seller} §7| 时间: §f{time_str}\n")

    idx = self._paginate_display(
        player,
        guild.vault_items,
        "选择购买物品",
        formatter,
        True)
    if idx is None:
        return True

    item = guild.vault_items[idx]
    if (item.seller == player.name and not getattr(
            Config, "GUILD_VAULT_CONFIG", {}).get("允许购买自己出售的物品", False)):
        player.show("§l§a公会仓库 §d>> §r不能购买自己出售的物品")
        return True

    # 检查贡献点
    if member.contribution < item.price:
        player.show("§l§a公会仓库 §d>> §r贡献点不足")
        return True

    # 检查背包空间
    if not self._has_inventory_space(player, item.item_id, item.count):
        player.show("§l§a公会仓库 §d>> §r背包空间不足")
        return True

    # 确认购买
    item_name = self._get_item_display_name(item.item_id)
    player.show(
        f"§l§a公会仓库 §d>> §r确认购买 §f{item_name} §7x{
            item.count} §r花费 §e{
            item.price}贡献点§r？")
    player.show("§7输入 '确认' 继续购买")

    confirm = game_utils.waitMsg(player.name, timeout=20)
    if confirm != "确认":
        player.show("§l§a公会仓库 §d>> §r购买已取消")
        return True

    # 执行购买
    guilds = self.guild_manager.load_guilds(force_reload=True)
    guild = guilds.get(guild.guild_id)
    if not guild:
        player.show("§l§a公会仓库 §d>> §r公会数据异常")
        return True

    # 重新检查物品是否还存在
    if idx >= len(
            guild.vault_items) or guild.vault_items[idx].item_id != item.item_id:
        player.show("§l§a公会仓库 §d>> §r物品已被其他人购买")
        return True
    item = guild.vault_items[idx]
    if (item.seller == player.name and not getattr(
            Config, "GUILD_VAULT_CONFIG", {}).get("允许购买自己出售的物品", False)):
        player.show("§l§a公会仓库 §d>> §r不能购买自己出售的物品")
        return True

    # 扣除贡献点
    buyer_member = guild.get_member(player.name)
    if not buyer_member or buyer_member.contribution < item.price:
        player.show("§l§a公会仓库 §d>> §r贡献点不足")
        return True

    buyer_member.contribution -= item.price

    # 给卖家贡献点（扣除税费）
    tax = int(item.price * Config.VAULT_TRADE_TAX)
    seller_income = item.price - tax
    seller_member = guild.get_member(item.seller)
    if seller_member:
        seller_member.contribution += seller_income

    # 给玩家物品
    self.game_ctrl.sendwocmd(f"give {player.name} {item.item_id} {item.count}")

    guild.vault_items.pop(idx)

    guild.add_log(
        f"{player.name} 购买了 {item_name} x{item.count} (花费{item.price}贡献点)")
    if getattr(Config, "GUILD_VAULT_CONFIG", {}).get("启用交易日志", True):
        guild.add_vault_trade_log(
            "buy",
            item,
            player.name,
            buyer=player.name,
            detail=f"税费{tax}，卖家收入{seller_income}",
        )
    suggested_value = guild.get_item_value(item.item_id) * item.count
    audit_ratio = float(
        getattr(
            Config,
            "GUILD_VAULT_CONFIG",
            {}).get(
            "高价交易审计倍率",
            3.0))
    if suggested_value > 0 and item.price >= suggested_value * audit_ratio:
        guild.add_audit_log(
            "vault_high_price_buy",
            player.name,
            target=item.seller,
            detail=f"{item.item_id} x{item.count} price={item.price}",
        )

    self.guild_manager.save_guilds(guilds)

    player.show(f"§l§a公会仓库 §d>> §r购买成功！花费 §e{item.price}贡献点")

    # 更新贸易任务进度
    self.check_and_complete_trade_tasks(player.name)

    # 通知卖家
    if seller_member and item.seller in self.game_ctrl.allplayers:
        message = (
            f"§l§a公会仓库 §d>> §r你的 {item_name} x{item.count} "
            f"被 {player.name} 购买了，获 {seller_income} 贡献点"
        )
        self.game_ctrl.sendcmd(
            f'/tellraw {item.seller} {{"rawtext":[{{"text":"{message}"}}]}}'
        )

    return True


def _handle_vault_sell(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """出售物品到仓库"""
    if not guild.has_permission(player.name, "vault_sell"):
        player.show("§l§a公会仓库 §d>> §r你没有出售仓库物品权限")
        return True

    # 检查仓库容量
    max_slots = Config.VAULT_INITIAL_SLOTS  # 固定10000格
    if len(guild.vault_items) >= max_slots:
        player.show("§l§a公会仓库 §d>> §r仓库已满")
        return True

    player.show("§l§a公会仓库 §d>> §r请输入要出售的物品名称")
    player.show("§7支持中文名称，如: 钻石、铁锭、金块等")
    player.show("§7也支持英文ID，如: minecraft:diamond")

    user_input = game_utils.waitMsg(player.name, timeout=30)

    if not user_input:
        player.show("§l§a公会仓库 §d>> §r输入为空")
        return True

    # 使用智能匹配查找物品ID
    item_id, suggestions = self.item_matcher.validate_and_suggest(user_input)

    if not item_id:
        player.show("§l§a公会仓库 §d>> §r未找到匹配的物品")
        if suggestions:
            player.show("§7您是否想要:")
            for i, suggestion in enumerate(suggestions[:3], 1):
                player.show(f"§e{i}. §f{suggestion}")
            player.show("§7请重新输入准确的物品名称")
        return True

    # 显示找到的物品
    chinese_name = self.item_matcher.get_chinese_name(item_id)
    player.show(f"§l§a公会仓库 §d>> §r找到物品: §f{chinese_name} §7({item_id})")

    # 检查玩家是否有该物品
    item_count = player.getItemCount(item_id)
    if item_count <= 0:
        player.show("§l§a公会仓库 §d>> §r你没有这个物品")
        return True

    player.show(f"§l§a公会仓库 §d>> §r你有 {item_count} 个该物品")
    player.show("§7请输入要出售的数量:")

    count_str = game_utils.waitMsg(player.name, timeout=30)
    if not count_str or not count_str.isdigit():
        player.show("§l§a公会仓库 §d>> §r无效的数量")
        return True

    count = int(count_str)
    if count <= 0 or count > item_count:
        player.show("§l§a公会仓库 §d>> §r数量无效")
        return True
    max_sell_count = int(
        getattr(
            Config,
            "GUILD_VAULT_CONFIG",
            {}).get(
            "单次出售最大数量",
            64))
    if count > max_sell_count > 0:
        player.show(f"§l§a公会仓库 §d>> §r单次最多出售 {max_sell_count} 个")
        return True

    # 获取建议价格
    suggested_price = guild.get_item_value(item_id) * count
    player.show(f"§l§a公会仓库 §d>> §r建议价格: §e{suggested_price}贡献点")
    player.show("§7请输入出售价格 (贡献点，你可以自定义任意价格):")

    price_str = game_utils.waitMsg(player.name, timeout=30)
    if not price_str or not price_str.isdigit():
        player.show("§l§a公会仓库 §d>> §r无效的价格")
        return True

    price = int(price_str)
    if price <= 0:
        player.show("§l§a公会仓库 §d>> §r价格必须大于0")
        return True
    vault_config = getattr(Config, "GUILD_VAULT_CONFIG", {})
    min_price = int(vault_config.get("单笔价格下限", 1))
    max_price = int(vault_config.get("单笔价格上限", 100000))
    if price < min_price or price > max_price:
        player.show(f"§l§a公会仓库 §d>> §r价格必须在 {min_price}-{max_price} 之间")
        return True

    # 确认出售
    item_name = self._get_item_display_name(item_id)
    player.show(
        f"§l§a公会仓库 §d>> §r确认出售 §f{item_name} §7x{count} §r价格 §e{price}贡献点§r？")
    player.show("§7输入 '确认' 继续出售")

    confirm = game_utils.waitMsg(player.name, timeout=20)
    if confirm != "确认":
        player.show("§l§a公会仓库 §d>> §r出售已取消")
        return True

    # 执行出售
    guilds = self.guild_manager.load_guilds(force_reload=True)
    guild = guilds.get(guild.guild_id)
    if not guild:
        player.show("§l§a公会仓库 §d>> §r公会数据异常")
        return True

    # 再次检查仓库容量
    if len(guild.vault_items) >= max_slots:
        player.show("§l§a公会仓库 §d>> §r仓库已满")
        return True
    max_listing = int(vault_config.get("单个成员最大上架数量", 18))
    if max_listing > 0:
        own_listing_count = sum(
            1 for item in guild.vault_items if item.seller == player.name)
        if own_listing_count >= max_listing:
            player.show(f"§l§a公会仓库 §d>> §r你最多同时上架 {max_listing} 件物品")
            return True

    # 扣除物品
    self.game_ctrl.sendwocmd(f"clear {player.name} {item_id} 0 {count}")

    # 添加到仓库
    vault_item = VaultItem(
        item_id=item_id,
        count=count,
        price=price,
        seller=player.name
    )

    guild.vault_items.append(vault_item)
    guild.add_log(f"{player.name} 出售了 {item_name} x{count} (价格{price}贡献点)")
    if vault_config.get("启用交易日志", True):
        guild.add_vault_trade_log(
            "sell", vault_item, player.name, detail="上架出售")

    audit_ratio = float(vault_config.get("高价交易审计倍率", 3.0))
    if suggested_price > 0 and price >= suggested_price * audit_ratio:
        guild.add_audit_log(
            "vault_high_price_sell",
            player.name,
            detail=f"{item_id} x{count} price={price}",
        )

    # 保存数据
    self.guild_manager.save_guilds(guilds)

    player.show(f"§l§a公会仓库 §d>> §r出售成功！{item_name} x{count} 已上架")

    # 更新贸易任务进度
    self.check_and_complete_trade_tasks(player.name)

    return True


def _handle_vault_logs(self, player: Player, guild: GuildData) -> bool:
    """查看仓库交易日志"""
    if not getattr(Config, "GUILD_VAULT_CONFIG", {}).get("启用交易日志", True):
        player.show("§l§a公会仓库 §d>> §r交易日志未启用")
        return True

    if not guild.vault_trade_logs:
        player.show("§l§a公会仓库 §d>> §r暂无仓库交易日志")
        return True

    action_names = {
        "sell": "上架",
        "buy": "购买",
        "cancel": "撤回",
    }

    def formatter(i, log):
        """Format one menu item for display."""
        item_name = self._get_item_display_name(log.item_id)
        time_str = datetime.fromtimestamp(
            log.timestamp).strftime("%m-%d %H:%M")
        action_name = action_names.get(log.action, log.action)
        participants = []
        if log.seller:
            participants.append(f"卖家:{log.seller}")
        if log.buyer:
            participants.append(f"买家:{log.buyer}")
        participant_text = " §7| ".join(
            participants) if participants else f"操作者:{log.actor}"
        detail = f"\n   §7说明: §f{log.detail}" if log.detail else ""
        return (
            f"§e{i}. §f{action_name} §f{item_name} §7x{log.count}\n"
            f"   §7价格: §e{log.price}贡献点 §7| {participant_text} §7| 时间: §f{time_str}"
            f"{detail}\n"
        )

    logs = list(reversed(guild.vault_trade_logs[-50:]))
    self._paginate_display(player, logs, "仓库交易日志", formatter)
    return True


def _handle_vault_cancel(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """撤回仓库上架物品"""
    vault_config = getattr(Config, "GUILD_VAULT_CONFIG", {})
    if not vault_config.get("启用撤回出售", True):
        player.show("§l§a公会仓库 §d>> §r撤回出售未启用")
        return True

    can_cancel_own = guild.has_permission(player.name, "vault_cancel_own")
    can_cancel_any = guild.has_permission(player.name, "vault_cancel_any")
    only_own = vault_config.get("只允许撤回自己的物品", False)

    cancelable_items = []
    for index, item in enumerate(guild.vault_items):
        is_own = item.seller == player.name
        if is_own and can_cancel_own:
            cancelable_items.append((index, item))
        elif not only_own and can_cancel_any:
            cancelable_items.append((index, item))

    if not cancelable_items:
        player.show("§l§a公会仓库 §d>> §r没有可撤回的上架物品")
        return True

    def formatter(i, data):
        """Format one menu item for display."""
        _index, item = data
        item_name = self._get_item_display_name(item.item_id)
        time_str = datetime.fromtimestamp(
            item.timestamp).strftime("%m-%d %H:%M")
        return (
            f"§e{i}. §f{item_name} §7x{
                item.count}\n" f"   §7价格: §e{
                item.price}贡献点 §7| 卖家: §a{
                item.seller} §7| 时间: §f{time_str}\n")

    idx = self._paginate_display(
        player,
        cancelable_items,
        "选择撤回物品",
        formatter,
        True)
    if idx is None:
        return True

    original_index, selected_item = cancelable_items[idx]
    selected_name = self._get_item_display_name(selected_item.item_id)
    player.show(
        f"§l§a公会仓库 §d>> §r确认撤回 §f{selected_name} §7x{
            selected_item.count}§r？")
    player.show("§7输入 '确认' 继续撤回")

    confirm = game_utils.waitMsg(player.name, timeout=20)
    if confirm != "确认":
        player.show("§l§a公会仓库 §d>> §r撤回已取消")
        return True

    guilds = self.guild_manager.load_guilds(force_reload=True)
    latest_guild = guilds.get(guild.guild_id)
    if not latest_guild:
        player.show("§l§a公会仓库 §d>> §r公会数据异常")
        return True

    if original_index >= len(latest_guild.vault_items):
        player.show("§l§a公会仓库 §d>> §r物品已不存在")
        return True

    latest_item = latest_guild.vault_items[original_index]
    if (
        latest_item.item_id != selected_item.item_id
        or latest_item.count != selected_item.count
        or latest_item.price != selected_item.price
        or latest_item.seller != selected_item.seller
    ):
        player.show("§l§a公会仓库 §d>> §r物品状态已变化，请重新打开仓库")
        return True

    is_own = latest_item.seller == player.name
    if not ((is_own and can_cancel_own) or (not only_own and can_cancel_any)):
        player.show("§l§a公会仓库 §d>> §r你没有撤回该物品的权限")
        return True

    removed_item = latest_guild.cancel_vault_item(player.name, original_index)
    if not removed_item:
        player.show("§l§a公会仓库 §d>> §r撤回失败")
        return True

    if vault_config.get("撤回后返还物品", True):
        self.game_ctrl.sendwocmd(
            f"give {
                removed_item.seller} {
                removed_item.item_id} {
                removed_item.count}")

    self.guild_manager.save_guilds(guilds)
    player.show(
        f"§l§a公会仓库 §d>> §r已撤回 §f{selected_name} §7x{
            removed_item.count}")
    if (
        removed_item.seller != player.name
        and removed_item.seller in self.game_ctrl.allplayers
    ):
        message = (
            f"§l§a公会仓库 §d>> §r你上架的 {selected_name} "
            f"x{removed_item.count} 已被 {player.name} 撤回"
        )
        self.game_ctrl.sendcmd(
            f'/tellraw {removed_item.seller} {{"rawtext":[{{"text":"{message}"}}]}}'
        )

    return True


def _handle_vault_settings(  # skipcq: PY-R1000
    self,
    player: Player,
    guild: GuildData,
) -> bool:
    """设置物品价值"""
    if not guild.has_permission(player.name, "vault_settings"):
        player.show("§l§a公会仓库 §d>> §r你没有设置仓库物品价值权限")
        return True

    player.show("§r========== §a物品价值设置§r ==========")
    player.show("§e1. §f查看当前设置")
    player.show("§e2. §f设置物品价值")
    player.show("§e3. §f删除自定义价值")
    player.show("§7输入选项序号:")

    choice = game_utils.waitMsg(player.name, timeout=30)

    if choice == "1":
        # 显示当前设置
        if guild.custom_item_values:
            player.show("§l§a自定义物品价值§r")
            for item_id, value in guild.custom_item_values.items():
                item_name = self._get_item_display_name(item_id)
                player.show(f"§f{item_name}: §e{value}贡献点")
        else:
            player.show("§l§a公会仓库 §d>> §r暂无自定义物品价值")

        player.show("\n§l§a默认物品价值§r")
        for item_id, value in Config.DEFAULT_ITEM_VALUES.items():
            item_name = self._get_item_display_name(item_id)
            player.show(f"§f{item_name}: §e{value}贡献点")

    elif choice == "2":
        # 设置物品价值
        player.show("§l§a公会仓库 §d>> §r请输入物品ID (如: minecraft:diamond):")
        item_id = game_utils.waitMsg(player.name, timeout=30)

        if not item_id or not item_id.startswith("minecraft:"):
            player.show("§l§a公会仓库 §d>> §r无效的物品ID")
            return True

        player.show("§l§a公会仓库 §d>> §r请输入贡献点价值:")
        value_str = game_utils.waitMsg(player.name, timeout=30)

        if not value_str or not value_str.isdigit():
            player.show("§l§a公会仓库 §d>> §r无效的价值")
            return True

        value = int(value_str)
        if value <= 0:
            player.show("§l§a公会仓库 §d>> §r价值必须大于0")
            return True

        # 保存设置
        guilds = self.guild_manager.load_guilds(force_reload=True)
        guild = guilds.get(guild.guild_id)
        if guild:
            guild.custom_item_values[item_id] = value
            item_name = self._get_item_display_name(item_id)
            guild.add_log(f"{player.name} 设置了 {item_name} 的价值为 {value} 贡献点")
            self.guild_manager.save_guilds(guilds)
            player.show(f"§l§a公会仓库 §d>> §r已设置 {item_name} 的价值为 {value} 贡献点")

    elif choice == "3":
        # 删除自定义价值
        if not guild.custom_item_values:
            player.show("§l§a公会仓库 §d>> §r暂无自定义物品价值")
            return True

        player.show("§l§a当前自定义价值§r")
        items = list(guild.custom_item_values.items())
        for i, (item_id, value) in enumerate(items, 1):
            item_name = self._get_item_display_name(item_id)
            player.show(f"§e{i}. §f{item_name}: §e{value}贡献点")

        player.show("§7输入序号删除:")
        idx_str = game_utils.waitMsg(player.name, timeout=30)

        if idx_str and idx_str.isdigit():
            idx = int(idx_str) - 1
            if 0 <= idx < len(items):
                item_id, _ = items[idx]
                guilds = self.guild_manager.load_guilds(force_reload=True)
                guild = guilds.get(guild.guild_id)
                if guild and item_id in guild.custom_item_values:
                    del guild.custom_item_values[item_id]
                    item_name = self._get_item_display_name(item_id)
                    guild.add_log(f"{player.name} 删除了 {item_name} 的自定义价值")
                    self.guild_manager.save_guilds(guilds)
                    player.show(f"§l§a公会仓库 §d>> §r已删除 {item_name} 的自定义价值")

    return True


def _handle_create_guild(self, player: Player, player_xuid: str) -> bool:
    """处理创建公会"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if guild:
        player.show(render_create_guild_prompt("已有公会提示词"))
        return True

    score = player.getScore(Config.GUILD_SCOREBOARD)
    if score < Config.GUILD_CREATION_COST:
        player.show(render_create_guild_prompt("创建公会余额不足提示词", balance=score))
        return True

    player.show(render_create_guild_prompt("创建公会提示词", balance=score))
    confirm = game_utils.waitMsg(player.name, timeout=30)
    if confirm is None:
        player.show(render_create_guild_prompt("创建公会回复超时提示词"))
        return True
    if confirm.strip().lower() not in ("确认", "继续", "是", "y", "yes"):
        player.show(render_create_guild_prompt("创建公会取消提示词"))
        return True

    player.show(render_create_guild_prompt("创建公会输入名称提示词"))
    guild_name = game_utils.waitMsg(player.name, timeout=30)

    # 使用新的输入验证
    is_valid, error_msg = InputValidator.validate_guild_name(guild_name)
    if not is_valid:
        player.show(render_create_guild_prompt("创建公会名称无效提示词", error=error_msg))
        return True

    score = player.getScore(Config.GUILD_SCOREBOARD)
    if score < Config.GUILD_CREATION_COST:
        player.show(render_create_guild_prompt("创建公会二次余额不足提示词", balance=score))
        return True

    # 扣除配置的计分板积分并创建公会
    self.game_ctrl.sendwocmd(
        f"scoreboard players remove {
            player.name} {
            Config.GUILD_SCOREBOARD} {
                Config.GUILD_CREATION_COST}")

    if self.guild_manager.create_guild(player_xuid, player.name, guild_name):
        player.show(render_create_guild_prompt(
            "创建公会成功提示词", guild=guild_name, player=player.name))
        # 通知所有在线玩家
        announcement = render_create_guild_prompt(
            "创建公会全服公告提示词",
            guild=guild_name,
            player=player.name,
        )
        payload = json.dumps(
            {"rawtext": [{"text": announcement}]}, ensure_ascii=False)
        self.game_ctrl.sendcmd(f"/tellraw @a {payload}")
    else:
        player.show(render_create_guild_prompt(
            "创建公会名称已存在提示词", guild=guild_name, player=player.name))
        self.game_ctrl.sendwocmd(
            f"scoreboard players add {
                player.name} {
                Config.GUILD_SCOREBOARD} {
                Config.GUILD_CREATION_COST}")

    return True


def _handle_list_guilds(self, player: Player) -> bool:
    """处理查看公会列表"""
    guilds = list(self.guild_manager.load_guilds().values())
    if not guilds:
        player.show(render_config_prompt("公会列表为空提示词"))
        return True

    # 按等级和成员数排序
    guilds.sort(key=lambda g: (g.level, len(g.members)), reverse=True)

    def formatter(i, g):
        """Format one menu item for display."""
        return (
        f"§e{i}. §r{g.name} §7Lv.{g.level}\n"
        f"   §7会长: §f{g.owner} §7| 成员: §a{len(g.members)}/{Config.MAX_GUILD_MEMBERS}\n"
    )

    page = 1
    max_page = (len(guilds) + Config.ITEMS_PER_PAGE -
                1) // Config.ITEMS_PER_PAGE
    while True:
        page = max(1, min(page, max_page))
        start = (page - 1) * Config.ITEMS_PER_PAGE
        end = start + Config.ITEMS_PER_PAGE

        msg = (
            f"{TITLE_PREFIX} 『§6公会系统 §d云链联动版§f』 §b公会列表§d"
            f"\n{ORION_BORDER}"
        )
        for i, guild in enumerate(guilds[start:end], start=1):
            msg += "\n" + formatter(start + i, guild).rstrip()
        msg += "\n" + format_page_footer(page, max_page, start + 1, end, False)

        player.show(msg)

        choice = game_utils.waitMsg(player.name, timeout=20)
        if choice is None:
            player.show(render_config_prompt("公会列表分页超时提示词"))
            return True
        if choice == "+":
            page = min(page + 1, max_page)
        elif choice == "-":
            page = max(page - 1, 1)
        elif choice == "q":
            player.show(render_config_prompt("公会列表分页退出提示词"))
            return True

    return True


def _handle_join_guild(self, player: Player) -> bool:
    """处理加入公会申请"""
    if self.guild_manager.get_guild_by_player(player.name):
        player.show("§l§a公会 §d>> §r你已经加入了一个公会")
        return True

    player.show("§l§a公会 §d>> §r请输入公会名字（支持模糊搜索）")
    search_name = game_utils.waitMsg(player.name, timeout=30)

    if not search_name:
        player.show("§l§a公会 §d>> §r公会名字不能为空")
        return True

    # 搜索匹配的公会
    guilds = self.guild_manager.load_guilds()
    matched_guilds = [g for g in guilds.values() if search_name.lower()
                      in g.name.lower()]

    if not matched_guilds:
        player.show("§l§a公会 §d>> §r未找到匹配的公会")
        return True

    # 选择公会
    if len(matched_guilds) == 1:
        target_guild = matched_guilds[0]
    else:
        def formatter(i, g):
            """Format one menu item for display."""
            return f"{i}. {g.name} (会长:{g.owner})\n"
        idx = self._paginate_display(
            player, matched_guilds, "选择公会", formatter, True)
        if idx is None:
            return True
        target_guild = matched_guilds[idx]

    # 检查人数上限
    if len(target_guild.members) >= Config.MAX_GUILD_MEMBERS:
        player.show("§l§a公会 §d>> §r该公会已满员")
        return True

    reason = ""
    join_config = getattr(Config, "GUILD_JOIN_REQUEST_CONFIG", {})
    if join_config.get("启用离线申请队列", True):
        player.show("§l§a公会 §d>> §r请输入申请理由，可直接发送空白跳过")
        reason_input = game_utils.waitMsg(player.name, timeout=60)
        reason = reason_input or ""

    guilds = self.guild_manager.load_guilds(force_reload=True)
    latest_guild = guilds.get(target_guild.guild_id)
    if not latest_guild:
        player.show("§l§a公会 §d>> §r公会数据异常")
        return True

    if not latest_guild.add_join_request(player.name, reason):
        player.show("§l§a公会 §d>> §r申请提交失败，可能已有待处理申请或队列已满")
        return True

    self.guild_manager.save_guilds(guilds)
    self._notify_join_request_admins(latest_guild, player.name)
    player.show(f"§l§a公会 §d>> §r申请已提交至 §e{latest_guild.name} §r的申请队列")

    return True


def _handle_leave_guild(self, player: Player) -> bool:
    """处理退出公会"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你未加入任何公会")
        return True

    member = guild.get_member(player.name)
    if member and member.rank == GuildRank.OWNER:
        player.show("§l§a公会 §d>> §r会长不能退出公会，只能解散公会")
        player.show("§7请使用 '解散' 选项来解散公会")
        return True

    guild_name = self.guild_manager.remove_member(player.name)
    if guild_name:
        player.show(f"§l§a公会 §d>> §r已退出公会 {guild_name}")
    else:
        player.show("§l§a公会 §d>> §r退出失败")
    return True


def _handle_dissolve_guild(self, player: Player, player_xuid: str) -> bool:
    """处理解散公会"""
    _ = player_xuid
    guild = self.guild_manager.get_guild_by_player(player.name)
    member = guild.get_member(player.name) if guild else None

    if not guild or not member or member.rank != GuildRank.OWNER:
        player.show("§l§a公会 §d>> §r你不是任何公会的会长")
        return True

    player.show(f"§l§a公会 §d>> §r确定要解散公会 §e{guild.name} §r吗？")
    player.show("§c此操作不可撤销！输入'确认解散'继续")
    confirm = game_utils.waitMsg(player.name, timeout=30)

    if confirm != "确认解散":
        player.show("§l§a公会 §d>> §r操作已取消")
        return True

    # 通知所有在线成员
    message = f"§l§a公会 §d>> §r公会 §e{guild.name}§r 已被解散"
    for member in guild.members:
        if member.name in self.game_ctrl.allplayers:
            self.game_ctrl.sendcmd(
                f'/tellraw {member.name} {{"rawtext":[{{"text":"{message}"}}]}}'
            )

    guilds = self.guild_manager.load_guilds(force_reload=True)
    if guild.guild_id in guilds:
        del guilds[guild.guild_id]
        self.guild_manager.save_guilds(guilds)
        player.show(f"§l§a公会 §d>> §r已解散公会 §e{guild.name}")

    return True


def _handle_kick_member(self, player: Player) -> bool:
    """处理踢出成员"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild or not guild.has_permission(player.name, "kick"):
        player.show("§l§a公会 §d>> §r你没有踢人权限")
        return True

    # 使用新的权限检查逻辑过滤可踢出的成员
    kickable_members = []
    for member in guild.members:
        if guild.can_manage_member(player.name, member.name):
            kickable_members.append(member)

    if not kickable_members:
        player.show("§l§a公会 §d>> §r没有可踢出的成员")
        return True

    def formatter(i, m):
        """Format one menu item for display."""
        return f"§e{i}. {m.rank.display_name} §f{m.name}\n"
    idx = self._paginate_display(
        player,
        kickable_members,
        "踢出成员",
        formatter,
        True)

    if idx is not None:
        target = kickable_members[idx]
        self.guild_manager.remove_member(target.name)
        player.show(f"§l§a公会 §d>> §r已将 {target.name} 踢出公会")

        # 通知被踢玩家
        if target.name in self.game_ctrl.allplayers:
            self.game_ctrl.sendcmd(
                f'/tellraw {target.name} '
                '{"rawtext":[{"text":"§l§a公会 §d>> §r你已被踢出公会"}]}'
            )

    return True


def _handle_set_base(self, player: Player) -> bool:
    """处理设置据点 - 增强版本"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    if self.guild_is_frozen(guild):
        self.show_guild_frozen(player, guild)
        return True

    if not guild.has_permission(player.name, "setbase"):
        player.show("§l§a公会 §d>> §r你没有设置公会据点权限")
        return True

    try:
        fmts.print_inf(f"开始为公会 {guild.name} 设置据点")
        pos = game_utils.getPos(player.name)

        if not pos:
            player.show("§l§a公会 §d>> §r获取位置失败，请稍后重试")
            fmts.print_err("获取位置失败: pos为空")
            return True

        dimension = pos.get("dimension", -1)
        if dimension != 0:
            player.show("§l§a公会 §d>> §r据点只能设置在主世界")
            fmts.print_err(f"设置据点失败: 维度不是主世界 (维度={dimension})")
            return True

        # 确保position字段存在
        if "position" not in pos:
            player.show("§l§a公会 §d>> §r获取位置信息不完整，请稍后重试")
            fmts.print_err(f"设置据点错误: 位置信息不完整 {pos}")
            return True

        position = pos["position"]
        x = position.get("x", 0)
        y = position.get("y", 0)
        z = position.get("z", 0)

        base = GuildBase(
            dimension=dimension,
            x=x,
            y=y,
            z=z
        )

        # 打印调试信息
        fmts.print_inf(f"正在设置据点: 维度={dimension}, 坐标=({x}, {y}, {z})")

        # 直接保存到当前公会对象
        guild.base = base
        guild.add_log(f"{player.name} 设置了据点")

        # 重新加载公会数据以确保使用最新数据
        guilds = self.guild_manager.load_guilds(force_reload=True)
        guild_id = guild.guild_id

        # 确保公会ID存在于加载的数据中
        if guild_id not in guilds:
            player.show("§l§a公会 §d>> §r公会数据加载失败，请稍后重试")
            fmts.print_err(f"设置据点错误: 公会ID {guild_id} 不存在于加载的数据中")
            return True

        # 更新公会数据
        guilds[guild_id].base = base
        guilds[guild_id].add_log(f"{player.name} 设置了据点")

        # 保存数据
        self.guild_manager.save_guilds(guilds)

        # 再次检查是否保存成功
        check_guilds = self.guild_manager.load_guilds(force_reload=True)
        if guild_id in check_guilds and check_guilds[guild_id].base:
            check_base = check_guilds[guild_id].base
            fmts.print_inf(
                f"据点设置成功: 公会={
                    guild.name}, 维度={
                    check_base.dimension}, 坐标=({
                    check_base.x}, {
                    check_base.y}, {
                        check_base.z})")
            player.show(f"§l§a公会 §d>> §r据点已设置为 ({x:.1f}, {y:.1f}, {z:.1f})")
        else:
            player.show("§l§a公会 §d>> §r据点设置可能失败，请重试")
            fmts.print_err(f"据点设置后验证失败: 公会={guild.name}")

    except Exception as e:
        player.show("§l§a公会 §d>> §r获取位置失败，请稍后重试")
        fmts.print_err(f"设置据点错误: {e}")
        import traceback
        fmts.print_err(traceback.format_exc())

    return True


def _handle_return_base(self, player: Player) -> bool:
    """处理返回据点 - 增强版本"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你没有加入任何公会")
        return True
    if not guild.has_permission(player.name, "return_base"):
        player.show("§l§a公会 §d>> §r你没有返回公会据点权限")
        return True

    # 重新加载公会数据以确保使用最新数据
    try:
        guilds = self.guild_manager.load_guilds(force_reload=True)
        guild_id = guild.guild_id

        # 确保公会ID存在于加载的数据中
        if guild_id not in guilds:
            player.show("§l§a公会 §d>> §r公会数据加载失败，请稍后重试")
            fmts.print_err(f"传送失败: 公会ID {guild_id} 不存在于加载的数据中")
            return True

        # 使用最新的公会数据
        guild = guilds[guild_id]
        if self.guild_is_frozen(guild):
            self.show_guild_frozen(player, guild)
            return True
        if isinstance(
            getattr(
                guild,
                "settings",
                None),
            dict) and guild.settings.get(
            "base_locked",
                False):
            player.show("§l§a公会 §d>> §r公会据点已被锁定")
            return True

        base = guild.base
        if not base:
            player.show("§l§a公会 §d>> §r公会尚未设置据点")
            fmts.print_err(f"传送失败: 公会 {guild.name} 没有设置据点")
            return True

        # 验证据点数据完整性
        if not all(hasattr(base, attr)
                   for attr in ['dimension', 'x', 'y', 'z']):
            player.show("§l§a公会 §d>> §r据点数据损坏，请重新设置")
            fmts.print_err(f"传送失败: 据点数据不完整 {base}")
            return True

        # 输出详细的据点信息用于调试
        fmts.print_inf(f"开始传送: 玩家={player.name}, 公会={guild.name}")
        fmts.print_inf(
            f"据点信息: 维度={
                base.dimension}, 坐标=({
                base.x}, {
                base.y}, {
                    base.z})")

        # 检查维度是否有效
        if base.dimension not in [0, -1, 1]:  # 主世界、下界、末地
            player.show("§l§a公会 §d>> §r据点维度无效，请重新设置")
            fmts.print_err(f"传送失败: 无效维度 {base.dimension}")
            return True

        # 准备传送
        player.show("§l§a公会 §d>> §r准备传送到据点...")
        player.show("§7请保持静止3秒...")

        # 延迟传送
        time.sleep(3)

        # 获取坐标并确保为数值类型
        x = float(base.x)
        y = float(base.y)
        z = float(base.z)
        fmts.print_inf(f"传送玩家 {player.name} 到据点: ({x}, {y}, {z})")

        # 尝试多种传送方法，按成功率排序
        success = False

        try:
            cmd = f"tp {player.name} {x} {y} {z}"
            fmts.print_inf(f"方法1 - 使用sendwocmd执行: {cmd}")
            self.game_ctrl.sendwocmd(cmd)
            success = True
            fmts.print_inf("方法1 - sendwocmd传送成功")
        except Exception as e:
            fmts.print_err(f"方法1 - sendwocmd失败: {e}")

        if success:
            player.show(f"§l§a公会 §d>> §r已传送到公会据点 ({x:.1f}, {y:.1f}, {z:.1f})")
            fmts.print_inf(f"传送成功: {player.name} -> ({x}, {y}, {z})")
        else:
            player.show("§l§a公会 §d>> §r传送失败，所有传送方式都无效")
            fmts.print_err("所有传送指令都失败了")

    except Exception as e:
        player.show("§l§a公会 §d>> §r传送过程中发生错误，请稍后重试")
        fmts.print_err(f"传送到据点时发生异常: {e}")
        import traceback
        fmts.print_err(traceback.format_exc())

    return True


def _handle_transfer_ownership(self, player: Player) -> bool:
    """转让会长"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        return True
    if not guild.has_permission(player.name, "transfer_owner"):
        player.show("§l§a公会 §d>> §r你没有转让会长权限")
        return True

    # 选择新会长
    other_members = [m for m in guild.members if m.name != player.name]
    if not other_members:
        player.show("§l§a公会 §d>> §r没有其他成员")
        return True

    def formatter(i, m):
        """Format one menu item for display."""
        return f"§e{i}. {m.rank.display_name} §f{m.name}\n"
    idx = self._paginate_display(
        player, other_members, "选择新会长", formatter, True)

    if idx is None:
        return True

    new_owner = other_members[idx]

    player.show(f"§l§a公会 §d>> §r确定要将会长转让给 §e{new_owner.name}§r 吗？")
    player.show("§c此操作不可撤销！输入'确认'继续")

    confirm = game_utils.waitMsg(player.name, timeout=30)
    if confirm != "确认":
        player.show("§l§a公会 §d>> §r操作已取消")
        return True

    guilds = self.guild_manager.load_guilds(force_reload=True)
    latest_guild = guilds.get(guild.guild_id)
    if not latest_guild:
        player.show("§l§a公会 §d>> §r公会数据异常")
        return True

    old_owner = latest_guild.get_member(player.name)
    latest_new_owner = latest_guild.get_member(new_owner.name)
    if not old_owner or not latest_new_owner:
        player.show("§l§a公会 §d>> §r成员数据异常")
        return True

    latest_guild.owner = latest_new_owner.name
    latest_new_owner.rank = GuildRank.OWNER
    old_owner.rank = GuildRank.DEPUTY

    latest_guild.add_log(f"{player.name} 将会长转让给了 {latest_new_owner.name}")
    latest_guild.add_audit_log("transfer_owner", player.name,
                               target=latest_new_owner.name)
    self.guild_manager.save_guilds(guilds)

    player.show(f"§l§a公会 §d>> §r已将会长转让给 {latest_new_owner.name}")

    # 通知新会长
    if latest_new_owner.name in self.game_ctrl.allplayers:
        self.game_ctrl.sendcmd(
            f'/tellraw {latest_new_owner.name} '
            '{"rawtext":[{"text":"§l§a公会 §d>> §r你已成为公会会长！"}]}'
        )

    return True


handlers = {
    '_handle_effect': _handle_effect,
    '_handle_rankings': _handle_rankings,
    '_format_time_ago': _format_time_ago,
    '_handle_view_guild': _handle_view_guild,
    '_handle_view_members': _handle_view_members,
    '_handle_view_logs': _handle_view_logs,
    '_handle_announcement': _handle_announcement,
    '_handle_tasks': _handle_tasks,
    '_handle_view_tasks': _handle_view_tasks,
    '_handle_join_task': _handle_join_task,
    '_handle_create_task': _handle_create_task,
    '_handle_generate_auto_tasks': _handle_generate_auto_tasks,
    '_handle_manage_tasks': _handle_manage_tasks,
    '_handle_manage_members': _handle_manage_members,
    '_notify_join_request_admins': _notify_join_request_admins,
    '_handle_join_request_queue': _handle_join_request_queue,
    '_handle_set_rank': _handle_set_rank,
    '_handle_donation': _handle_donation,
    '_handle_vault': _handle_vault,
    '_handle_vault_view': _handle_vault_view,
    '_handle_vault_buy': _handle_vault_buy,
    '_handle_vault_sell': _handle_vault_sell,
    '_handle_vault_logs': _handle_vault_logs,
    '_handle_vault_cancel': _handle_vault_cancel,
    '_handle_vault_settings': _handle_vault_settings,
    '_handle_create_guild': _handle_create_guild,
    '_handle_list_guilds': _handle_list_guilds,
    '_handle_join_guild': _handle_join_guild,
    '_handle_leave_guild': _handle_leave_guild,
    '_handle_dissolve_guild': _handle_dissolve_guild,
    '_handle_kick_member': _handle_kick_member,
    '_handle_set_base': _handle_set_base,
    '_handle_return_base': _handle_return_base,
    '_handle_transfer_ownership': _handle_transfer_ownership,
}
