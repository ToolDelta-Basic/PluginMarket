import os
import time
from typing import List, Optional, Tuple, Any


from tooldelta import Player, game_utils, fmts
from tooldelta.utils import tempjson

from guild.config import Config
from guild.models import GuildData, GuildMember,GuildRank ,VaultItem



def _show_menu(self, player: Player, guild: Optional[GuildData], member: Optional[GuildMember]) -> Optional[str]:
    """显示公会菜单并返回用户选择 - 增强版本"""

    # 数据完整性检查
    if guild and not member:
        # 公会存在但成员不存在，尝试重新获取
        fmts.print_err(f"数据不一致：玩家 {player.name} 在公会 {guild.name} 中但成员信息缺失")
        member = guild.get_member(player.name)
        if not member:
            player.show("§c错误：公会数据不一致，请尝试重新加入公会或联系管理员")
            fmts.print_err(f"严重错误：无法找到玩家 {player.name} 的成员信息")
            return None

    is_member = guild is not None
    is_owner = member and member.rank == GuildRank.OWNER

    # 调试日志
    if guild:
        fmts.print_inf(f"菜单显示 - 玩家: {player.name}, 公会: {guild.name}, 成员职位: {member.rank.value if member else 'None'}, 是否会长: {is_owner}")
    
    menu_items = [
        ("创建", "创建自己的公会", not is_member),
        ("列表", "查看所有公会", True),
        ("排行", "查看公会排行榜", True),
        ("查看", "查看公会详情", is_member),
        ("成员", "查看成员列表", is_member),
        ("日志", "查看公会日志", is_member),
        ("公告", "查看/设置公告", is_member),
        ("仓库", "公会仓库", is_member),
        ("加入", "加入一个公会", not is_member),
        ("退出", "退出当前公会", is_member and not is_owner),
        ("管理", "管理公会成员", member and member.rank in [GuildRank.OWNER, GuildRank.DEPUTY]),
        ("解散", "解散公会", is_owner),
        ("据点", "据点相关操作", is_member),
        ("捐献", "捐献物品到公会", is_member),
        ("任务", "公会任务系统", is_member),
        ("效果", "通过钻石获得效果增益",is_member)
    ]
    
    available_items = [(cmd, desc) for cmd, desc, cond in menu_items if cond]
    
    player.show("§r========== §a公会系统§r ==========§r§d")
    if member:
        player.show(f"§r§7>> §f[{member.rank.display_name}§f] §e{guild.name}")
    else:
        player.show(f"§r§7>> §f[§7游客§f]")
    
    for cmd, desc in available_items:
        player.show(f"§e§l● §r§a{cmd} §7>>> §f§o{desc}§r")
    
    player.show("§r§7>> 输入选项内容，q 退出")
    
    return game_utils.waitMsg(player.name, timeout=30)

def guild_update_data(self, args: list[str]):
    """更新过去的数据，确保所有公会都有 guild_id，且与外层 id 一致"""
    updated = False

    # 使用统一接口加载所有公会数据
    guilds = self.guild_manager._load_guilds(force_reload=True)

    for outer_id, guild in guilds.items():
        inner_id = getattr(guild, "guild_id", None)
        if inner_id != outer_id:
            guild.guild_id = outer_id
            fmts.print_inf(f"已更新 guild_id: {outer_id}（原: {inner_id}）")
            updated = True
    if updated:
        try:
            self.guild_manager.save_guilds(guilds)
            fmts.print_inf("公会数据文件已更新完成")
        except Exception as e:
            fmts.print_err(f"保存公会数据时出错: {e}")
    else:
        fmts.print_inf("无需更新，所有 guild_id 已正确")

def guild_menu_cb(self, player: Player, args: tuple):
    """公会菜单回调函数 - 增强版本"""
    player_xuid = self.xuidm.get_xuid_by_name(player.name, allow_offline=True)

    # 强制刷新缓存以确保数据最新
    guild = self.guild_manager.get_guild_by_player(player.name, force_reload=True)
    member = guild.get_member(player.name) if guild else None

    # 额外的数据验证
    if guild and not member:
        fmts.print_err(f"数据不一致警告：玩家 {player.name} 在公会 {guild.name} 中但找不到成员记录")
        # 尝试重新加载数据
        guild = self.guild_manager.get_guild_by_player(player.name, force_reload=True)
        member = guild.get_member(player.name) if guild else None
        
    subcommand = self._show_menu(player, guild, member)
        
    if subcommand is None or subcommand == "q":
        return True
        
    # 路由到对应的处理函数
    handlers = {
        "创建": lambda: self._handle_create_guild(player, player_xuid),
        "列表": lambda: self._handle_list_guilds(player),
        "排行": lambda: self._handle_rankings(player),
        "查看": lambda: self._handle_view_guild(player),
        "成员": lambda: self._handle_view_members(player),
        "日志": lambda: self._handle_view_logs(player),
        "公告": lambda: self._handle_announcement(player),
        "仓库": lambda: self._handle_vault(player),
        "加入": lambda: self._handle_join_guild(player),
        "退出": lambda: self._handle_leave_guild(player),
        "管理": lambda: self._handle_manage_members(player),
        "解散": lambda: self._handle_dissolve_guild(player, player_xuid),
        "据点": lambda: self._handle_base_menu(player),
        "捐献": lambda: self._handle_donation(player),
        "任务": lambda: self._handle_tasks(player),
        "效果": lambda: self._handle_effect(player),
    }
        
    handler = handlers.get(subcommand)
    if handler:
        return handler()
    else:
        player.show("§l§a公会 §d>> §r无效的指令")

    return True

def _create_progress_bar(self, current: int, total: int, length: int = 10) -> str:
    """创建进度条"""
    if total == 0:
        return "§7[§c无效§7]"

    progress = min(current / total, 1.0)
    filled = int(progress * length)
    empty = length - filled

    bar = "§a" + "█" * filled + "§7" + "░" * empty
    percentage = int(progress * 100)

    return f"§7[{bar}§7] §f{percentage}%"

def _format_time_duration(self, seconds: float) -> str:
    """格式化时间长度"""
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        return f"{int(seconds // 60)}分钟"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}小时"
    else:
        return f"{int(seconds // 86400)}天"

def _get_item_display_name(self, item_id: str) -> str:
    """获取物品显示名称"""
    return self.item_matcher.get_chinese_name(item_id)

def _has_inventory_space(self, player: Player, item_id: str, count: int) -> bool:
    """检查玩家背包是否有足够空间"""
    return True

def _handle_base_menu(self, player: Player) -> bool:
    """据点菜单"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        return True
    
    player.show("§r========== §a据点菜单§r ==========")
    
    if guild.base:
        base = guild.base
        dim_name = Config.DIMENSION_NAMES.get(base.dimension, f"维度{base.dimension}")
        player.show(f"§7当前据点: §f{dim_name} ({base.x:.1f}, {base.y:.1f}, {base.z:.1f})")
        player.show("§e1. §f传送到据点")
    else:
        player.show("§7当前据点: §c未设置")
    
    # 检查是否为会长 - 只有会长可以设置据点
    member = guild.get_member(player.name)
    if member and member.rank == GuildRank.OWNER:
        player.show("§e2. §f设置据点")
    
    player.show("§7输入选项序号，q 返回")
    
    choice = game_utils.waitMsg(player.name, timeout=30)
    
    if choice == "1" and guild.base:
        return self._handle_return_base(player)
    elif choice == "2" and member and member.rank == GuildRank.OWNER:
        return self._handle_set_base(player)
    
    return True

def guild_chat_cb(self, player: Player, args: tuple):
    """公会聊天回调"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    
    message = args[0] if args and args[0] else None
    
    if not message:
        # 切换聊天模式
        current_mode = self.guild_chat_mode.get(player.name, False)
        self.guild_chat_mode[player.name] = not current_mode
        
        if self.guild_chat_mode[player.name]:
            player.show("§l§a公会 §d>> §r已切换到公会聊天模式")
        else:
            player.show("§l§a公会 §d>> §r已切换到公共聊天模式")
    else:
        # 发送公会消息
        self._send_guild_message(guild, player.name, message)
    
    return True

def _send_guild_message(self, guild: GuildData, sender: str, message: str):
    """发送公会聊天消息"""
    member = guild.get_member(sender)
    if not member:
        return
    
    # 构建消息
    chat_msg = f"§7[§a公会§7] {member.rank.display_name} §f{sender}§7: §f{message}"
    
    # 发送给所有在线的公会成员
    for member in guild.members:
        if member.name in self.game_ctrl.allplayers:
            self.game_ctrl.sendcmd(
                f'/tellraw {member.name} {{"rawtext":[{{"text":"{chat_msg}"}}]}}'
            )

def on_chat_packet(self, packet):
    """处理聊天数据包"""
    try:
        # 检查是否是玩家聊天
        if packet.get("type") != 1:  # 1 表示玩家聊天
            return False
        
        sender = packet.get("source_name", "")
        message = packet.get("message", "")
        
        # 检查是否在公会聊天模式
        if self.guild_chat_mode.get(sender, False):
            guild = self.guild_manager.get_guild_by_player(sender)
            if guild:
                self._send_guild_message(guild, sender, message)
                return True  # 阻止原始消息
    except:
        pass
    
    return False

def guild_exp_task(self):
    """公会经验更新任务"""
    while True:
        time.sleep(Config.EXP_UPDATE_INTERVAL)
        fmts.print_inf("正在更新公会经验...")
        
        online_players = list(self.game_ctrl.allplayers)
        guilds = self.guild_manager._load_guilds(force_reload=True)
        guild_online_count = {}
        level_ups = []
        
        # 统计每个公会在线人数
        for player_name in online_players:
            guild = self.guild_manager.get_guild_by_player(player_name)
            if guild:
                guild_online_count[guild.guild_id] = guild_online_count.get(guild.guild_id, 0) + 1
        
        # 更新经验和等级
        for gid, count in guild_online_count.items():
            if count == 0:
                continue
            
            guild = guilds[gid]
            exp_add = count * Config.EXP_PER_ONLINE_MEMBER
            guild.exp += exp_add
            
            # 处理升级
            level = guild.level
            while level < len(Config.GUILD_LEVELS) and guild.exp >= Config.GUILD_LEVELS[level-1]:
                guild.exp -= Config.GUILD_LEVELS[level-1]
                level += 1
                level_ups.append((guild.name, level))
                guild.add_log(f"公会升级到 {level} 级")
            
            guild.level = level
        
        self.guild_manager.save_guilds(guilds)
        
        for guild_name, new_level in level_ups:
            self.game_ctrl.sendcmd(
                f'/tellraw @a {{"rawtext":[{{"text":"§l§a公会 §d>> §r公会 §e{guild_name}§r 升级到了 §e{new_level}§r 级！"}}]}}'
            )
            
def update_online_task(self):
    """更新在线状态任务"""
    while True:
        try:
            time.sleep(60)
            online_players = list(self.game_ctrl.allplayers)
            self.guild_manager.update_online_status(online_players)
        except Exception as e:
            fmts.print_err(f"更新在线状态出错: {e}")

def on_player_action(self, packet):
    """监听玩家行为，用于任务进度跟踪"""
    try:
        #TODO 等待具体的数据包格式
        pass
    except Exception as e:
        fmts.print_err(f"处理玩家行为事件出错: {e}")

def update_task_progress(self, player_name: str, task_type: str, target: str, amount: int = 1):
    """更新任务进度"""
    try:
        guild = self.guild_manager.get_guild_by_player(player_name)
        if not guild:
            return

        updated = False
        for task in guild.tasks:
            if (task.completed or
                task.task_type != task_type or
                task.target != target or
                player_name not in task.participants):
                continue

            task.current_count += amount
            if task.current_count >= task.target_count:
                # 任务完成
                task.completed = True
                task.current_count = task.target_count

                # 发放奖励
                member = guild.get_member(player_name)
                if member:
                    member.contribution += task.reward_contribution
                    guild.exp += task.reward_exp
                    guild.stats.total_contribution += task.reward_contribution

                # 通知玩家
                if player_name in self.game_ctrl.allplayers:
                    self.game_ctrl.sendcmd(
                        f'/tellraw {player_name} {{"rawtext":[{{"text":"§l§a公会任务 §d>> §r任务 \'{task.name}\' 已完成！获得 {task.reward_contribution} 贡献点和 {task.reward_exp} 公会经验"}}]}}'
                    )

                guild.add_log(f"{player_name} 完成了任务: {task.name}")
                updated = True
            else:
                updated = True

        if updated:
            self.guild_manager.mark_guild_dirty(guild.guild_id)

    except Exception as e:
        fmts.print_err(f"更新任务进度出错: {e}")

def check_and_complete_trade_tasks(self, player_name: str):
    """检查并完成贸易任务"""
    self.update_task_progress(player_name, "trade", "trade_count", 1)

def get_guild_rankings(self, sort_by: str = "level") -> List[Tuple[GuildData, Any]]:
    """获取公会排行榜"""
    guilds = self._load_guilds()
    guild_list = list(guilds.values())

    if sort_by == "level":
        guild_list.sort(key=lambda g: (g.level, g.exp), reverse=True)
        return [(g, g.level) for g in guild_list]
    elif sort_by == "members":
        guild_list.sort(key=lambda g: len(g.members), reverse=True)
        return [(g, len(g.members)) for g in guild_list]
    elif sort_by == "contribution":
        guild_list.sort(key=lambda g: g.stats.total_contribution, reverse=True)
        return [(g, g.stats.total_contribution) for g in guild_list]
    elif sort_by == "activity":
        # 基于最近活跃度排序
        current_time = time.time()
        guild_list.sort(key=lambda g: max([m.last_online for m in g.members] + [0]), reverse=True)
        return [(g, max([m.last_online for m in g.members] + [0])) for g in guild_list]
    else:
        return [(g, 0) for g in guild_list]

def get_member_rankings(self, guild_id: str, sort_by: str = "contribution") -> List[Tuple[GuildMember, Any]]:
    """获取公会成员排行榜"""
    guilds = self._load_guilds()
    guild = guilds.get(guild_id)

    if not guild:
        return []

    members = guild.members.copy()

    if sort_by == "contribution":
        members.sort(key=lambda m: m.contribution, reverse=True)
        return [(m, m.contribution) for m in members]
    elif sort_by == "online_time":
        current_time = time.time()
        members.sort(key=lambda m: current_time - m.last_online)
        return [(m, current_time - m.last_online) for m in members]
    elif sort_by == "join_time":
        members.sort(key=lambda m: m.join_time)
        return [(m, m.join_time) for m in members]
    else:
        return [(m, 0) for m in members]

def _paginate_display(self, player: Player, items: List[Any], 
                     title: str, formatter, allow_selection: bool = False) -> Optional[int]:
    """分页显示通用函数"""
    if not items:
        player.show(f"§l§a公会 §d>> §r{title}为空")
        return None
    
    page = 1
    max_page = (len(items) + Config.ITEMS_PER_PAGE - 1) // Config.ITEMS_PER_PAGE
    
    while True:
        page = max(1, min(page, max_page))
        start = (page - 1) * Config.ITEMS_PER_PAGE
        end = start + Config.ITEMS_PER_PAGE
        
        msg = f"§r========== §a{title}§r ==========§r§d\n§r第{page}/{max_page}页\n"
        
        for i, item in enumerate(items[start:end], start=1):
            msg += formatter(start + i, item)
        
        if allow_selection:
            msg += "§r§7>> 输入序号选择，"
        msg += "+ 下一页，- 上一页，q 退出"
        
        player.show(msg)
        
        choice = game_utils.waitMsg(player.name, timeout=20)
        if choice is None:
            player.show("§r§c操作超时")
            return None
        elif choice == "+":
            page = min(page + 1, max_page)
        elif choice == "-":
            page = max(page - 1, 1)
        elif choice == "q":
            player.show("§r§a已退出")
            return None
        elif allow_selection and choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(items):
                return idx - 1
            else:
                player.show("§r§c无效的选择")

def custom_vault_sell(self, player: Player, args: tuple):
    """自定义价格出售物品到仓库"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    user_input = args[0] if args and args[0] else None
    count = args[1] if len(args) > 1 and args[1] else 1
    custom_price = args[2] if len(args) > 2 and args[2] else 0

    if not user_input:
        player.show("§l§a公会仓库 §d>> §r请输入物品名称，例如: .自定义出售 钻石 10 800")
        player.show("§7格式: 自定义出售 [物品名称] [数量] [自定义价格]")
        player.show("§7支持中文: 自定义出售 钻石 10 800")
        player.show("§7支持英文: 自定义出售 minecraft:diamond 10 800")
        return True

    # 使用智能匹配查找物品ID
    item_id, suggestions = self.item_matcher.validate_and_suggest(user_input)

    if not item_id:
        player.show("§l§a公会仓库 §d>> §r未找到匹配的物品")
        if suggestions:
            player.show("§7您是否想要:")
            for i, suggestion in enumerate(suggestions[:3], 1):
                player.show(f"§e{i}. §f{suggestion}")
        return True

    # 检查仓库容量
    max_slots = Config.VAULT_INITIAL_SLOTS
    if len(guild.vault_items) >= max_slots:
        player.show("§l§a公会仓库 §d>> §r仓库已满")
        return True

    # 检查玩家是否有该物品
    item_count = player.getItemCount(item_id)
    if item_count < count:
        player.show(f"§l§a公会仓库 §d>> §r你只有 {item_count} 个该物品，无法出售 {count} 个")
        return True

    # 如果没有指定价格，询问自定义价格
    if custom_price <= 0:
        suggested_price = guild.get_item_value(item_id) * count
        player.show(f"§l§a公会仓库 §d>> §r建议价格: {suggested_price} 贡献点")
        player.show("§7请输入你的自定义价格 (贡献点):")

        price_input = game_utils.waitMsg(player.name, timeout=30)
        if not price_input or not price_input.isdigit():
            player.show("§l§a公会仓库 §d>> §r无效的价格")
            return True

        custom_price = int(price_input)
        if custom_price <= 0:
            player.show("§l§a公会仓库 §d>> §r价格必须大于0")
            return True

    # 确认出售
    item_name = self._get_item_display_name(item_id)
    player.show(f"§l§a公会仓库 §d>> §r确认以自定义价格出售？")
    player.show(f"§7物品: §f{item_name} x{count}")
    player.show(f"§7自定义价格: §e{custom_price}贡献点")
    player.show("§7输入 '确认' 继续出售，其他任意键取消")

    confirm = game_utils.waitMsg(player.name, timeout=20)
    if confirm != "确认":
        player.show("§l§a公会仓库 §d>> §r出售已取消")
        return True

    # 执行出售
    guilds = self.guild_manager._load_guilds(force_reload=True)
    guild = guilds.get(guild.guild_id)
    if not guild:
        player.show("§l§a公会仓库 §d>> §r公会数据异常")
        return True

    # 再次检查仓库容量
    if len(guild.vault_items) >= max_slots:
        player.show("§l§a公会仓库 §d>> §r仓库已满")
        return True

    # 扣除物品
    self.game_ctrl.sendwocmd(f"clear {player.name} {item_id} 0 {count}")

    # 添加到仓库
    vault_item = VaultItem(
        item_id=item_id,
        count=count,
        price=custom_price,
        seller=player.name
    )

    guild.vault_items.append(vault_item)
    guild.add_log(f"{player.name} 自定义价格出售了 {item_name} x{count} (价格{custom_price}贡献点)")

    # 保存数据
    self.guild_manager.save_guilds(guilds)

    player.show(f"§l§a公会仓库 §d>> §r自定义价格出售成功！{item_name} x{count} 已上架，价格 {custom_price} 贡献点")

    # 更新贸易任务进度
    self.check_and_complete_trade_tasks(player.name)

    return True

def show_item_list(self, player: Player, args: tuple):
    """显示支持的物品名称列表"""
    player.show("§r========== §a支持的物品名称§r ==========")
    player.show("§7以下是系统支持的物品名称，您可以在各种功能中使用:")
    player.show("")

    # 按类别显示物品
    categories = {
        "§e基础材料": ["钻石", "绿宝石", "金锭", "铁锭", "铜锭", "煤炭", "红石", "青金石", "石英"],
        "§a稀有材料": ["下界合金锭", "远古残骸", "末影珍珠", "烈焰棒", "恶魂之泪"],
        "§b方块材料": ["石头", "圆石", "泥土", "沙子", "砂砾", "黑曜石", "下界岩"],
        "§6木材": ["橡木原木", "白桦原木", "云杉原木", "丛林原木", "金合欢原木"],
        "§c食物": ["苹果", "金苹果", "面包", "牛肉", "熟牛肉", "胡萝卜", "土豆"],
        "§d染料": ["墨囊", "玫瑰红", "橙色染料", "黄色染料", "绿色染料", "蓝色染料"]
    }

    for category, items in categories.items():
        player.show(f"{category}:")
        item_line = "  "
        for i, item in enumerate(items):
            if i > 0 and i % 4 == 0:  # 每行显示4个物品
                player.show(item_line)
                item_line = "  "
            item_line += f"§f{item}§7, "
        if item_line.strip() != "":
            player.show(item_line.rstrip(", "))
        player.show("")

    player.show("§7提示:")
    player.show("§7- 支持中文名称输入，如: §f钻石§7、§f铁锭§7、§f金块")
    player.show("§7- 支持模糊匹配，如: 输入 §f铁§7 可匹配 §f铁锭§7、§f铁块")
    player.show("§7- 支持别名，如: §f钻§7 可匹配 §f钻石")
    player.show("§7- 也支持英文ID，如: §fminecraft:diamond")
    player.show("§7- 使用 §e.物品列表§7 随时查看此列表")

    return True

def admin_clear_guild_data(self, player: Player, args: tuple):
    """管理员清理公会数据功能"""
    confirm = args[0] if args and args[0] else ""

    # 简单的管理员验证 (可以根据需要修改)
    if player.name not in ["Admin", "管理员", "op"]:  # 根据实际情况修改管理员名单
        player.show("§c权限不足：此功能仅限管理员使用")
        return True

    if confirm != "确认清理":
        player.show("§l§c公会数据清理工具§r")
        player.show("§c警告：此操作将删除所有公会数据，包括：")
        player.show("§7- 所有公会记录")
        player.show("§7- 成员信息")
        player.show("§7- 仓库物品")
        player.show("§7- 任务记录")
        player.show("§7- 公会日志")
        player.show("§c此操作不可撤销！")
        player.show("§e如果确认要清理，请使用：§f.清理公会数据 确认清理")
        return True

    try:
        # 备份当前数据
        import shutil
        import time

        backup_file = f"{self.guilds_file}.backup_{int(time.time())}"
        if os.path.exists(self.guilds_file):
            shutil.copy2(self.guilds_file, backup_file)
            player.show(f"§a已创建数据备份：{backup_file}")

        # 清理内存中的数据
        self.guild_manager._guilds_cache = {}
        self.guild_manager._player_guild_cache = {}
        self.guild_manager._last_cache_time = 0

        # 清理数据文件
        empty_data = {}
        tempjson.save_and_write(self.guilds_file, empty_data)

        player.show("§l§a公会数据清理完成§r")
        player.show("§a✅ 已清空所有公会记录")
        player.show("§a✅ 已重置缓存数据")
        player.show("§a✅ 已清空数据文件")
        player.show(f"§7备份文件：{backup_file}")
        player.show("§7系统已回到初始状态，可以重新创建公会")

        # 记录操作日志
        fmts.print_inf(f"管理员 {player.name} 清理了所有公会数据")

    except Exception as e:
        player.show(f"§c清理失败：{str(e)}")
        fmts.print_err(f"清理公会数据时出错：{e}")

    return True

def debug_guild_menu(self, player: Player, args: tuple):
    """调试公会菜单显示问题"""
    player.show("§l§c公会菜单调试信息§r")
    player.show("=" * 40)

    # 获取公会和成员信息
    guild = self.guild_manager.get_guild_by_player(player.name)
    member = guild.get_member(player.name) if guild else None

    player.show(f"§7玩家名称: §f{player.name}")
    player.show(f"§7公会存在: §f{guild is not None}")

    if guild:
        player.show(f"§7公会名称: §f{guild.name}")
        player.show(f"§7公会ID: §f{guild.guild_id}")
        player.show(f"§7成员数量: §f{len(guild.members)}")

        if member:
            player.show(f"§7成员存在: §f{member is not None}")
            player.show(f"§7成员名称: §f{member.name}")
            player.show(f"§7成员职位: §f{member.rank}")
            player.show(f"§7职位值: §f{member.rank.value}")
            player.show(f"§7是否会长: §f{member.rank == GuildRank.OWNER}")
            player.show(f"§7是否副会长: §f{member.rank == GuildRank.DEPUTY}")

            # 测试菜单条件
            is_member = guild is not None
            is_owner = member and member.rank == GuildRank.OWNER
            is_deputy_or_above = member and member.rank in [GuildRank.OWNER, GuildRank.DEPUTY]

            player.show("§7菜单条件测试:")
            player.show(f"  is_member: §f{is_member}")
            player.show(f"  is_owner: §f{is_owner}")
            player.show(f"  is_deputy_or_above: §f{is_deputy_or_above}")

            # 测试具体菜单项
            menu_tests = [
                ("查看", is_member),
                ("成员", is_member),
                ("日志", is_member),
                ("公告", is_member),
                ("仓库", is_member),
                ("管理", is_deputy_or_above),
                ("解散", is_owner),
                ("据点", is_member),
                ("捐献", is_member),
                ("任务", is_member),
                ("效果", is_member),
            ]

            player.show("§7菜单项显示测试:")
            for menu_name, condition in menu_tests:
                status = "✅显示" if condition else "❌隐藏"
                player.show(f"  {menu_name}: §f{status}")
        else:
            player.show("§c成员信息不存在！")
    else:
        player.show("§c公会信息不存在！")

    player.show("=" * 40)
    return True

def debug_base_function(self, player: Player, args: tuple):
    """调试据点功能问题"""
    player.show("§l§c据点功能调试信息§r")
    player.show("=" * 50)

    # 获取公会和成员信息
    guild = self.guild_manager.get_guild_by_player(player.name)
    member = guild.get_member(player.name) if guild else None

    player.show(f"§7玩家名称: §f{player.name}")
    player.show(f"§7公会存在: §f{guild is not None}")

    if guild:
        player.show(f"§7公会名称: §f{guild.name}")
        player.show(f"§7公会ID: §f{guild.guild_id}")

        if member:
            player.show(f"§7成员职位: §f{member.rank.value}")
            player.show(f"§7是否会长: §f{member.rank == GuildRank.OWNER}")

            # 权限检查测试
            has_setbase_old = guild.has_permission(player.name, "setbase")
            is_owner_new = member.rank == GuildRank.OWNER

            player.show("§7权限检查结果:")
            player.show(f"  旧方式(has_permission): §f{has_setbase_old}")
            player.show(f"  新方式(直接检查会长): §f{is_owner_new}")

            if has_setbase_old != is_owner_new:
                player.show("§c⚠️ 权限检查结果不一致！")
            else:
                player.show("§a✅ 权限检查一致")

        # 据点信息检查
        player.show("§7据点信息:")
        if guild.base:
            base = guild.base
            player.show(f"  据点存在: §a是")
            player.show(f"  维度: §f{base.dimension}")
            player.show(f"  坐标: §f({base.x}, {base.y}, {base.z})")
            player.show(f"  坐标类型: §f{type(base.x).__name__}, {type(base.y).__name__}, {type(base.z).__name__}")

            # 验证坐标有效性
            try:
                x, y, z = float(base.x), float(base.y), float(base.z)
                player.show(f"  坐标转换: §a成功 ({x}, {y}, {z})")
            except Exception as e:
                player.show(f"  坐标转换: §c失败 - {e}")

            # 验证维度有效性
            valid_dimensions = [0, -1, 1]
            if base.dimension in valid_dimensions:
                player.show(f"  维度有效性: §a有效")
            else:
                player.show(f"  维度有效性: §c无效 (应为 {valid_dimensions})")

            # 测试传送指令格式和方法
            player.show("§7传送方法测试:")
            tp_methods = [
                ("sendwocmd", f"tp {player.name} {base.x} {base.y} {base.z}"),
            ]
            for i, (method, cmd) in enumerate(tp_methods):
                player.show(f"  方法{i+1}({method}): §f{cmd}")

        else:
            player.show(f"  据点存在: §c否")
            player.show(f"  原因: 公会未设置据点")
    else:
        player.show("§c公会信息不存在！")

    player.show("=" * 50)
    return True


logic_functions = {
    "_show_menu":_show_menu,
    "guild_update_data":guild_update_data,
    "guild_menu_cb":guild_menu_cb,
    "_create_progress_bar":_create_progress_bar,
    "_format_time_duration":_format_time_duration,
    "_get_item_display_name":_get_item_display_name,
    "_has_inventory_space":_has_inventory_space,
    "_handle_base_menu":_handle_base_menu,
    "_send_guild_message":_send_guild_message,
    "on_chat_packet":on_chat_packet,
    "guild_exp_task":guild_exp_task,
    "update_online_task":update_online_task,
    "on_player_action":on_player_action,
    "update_task_progress":update_task_progress,
    "check_and_complete_trade_tasks":check_and_complete_trade_tasks,
    "get_member_rankings":get_member_rankings,
    "_paginate_display":_paginate_display,
    "custom_vault_sell":custom_vault_sell,
    "show_item_list":show_item_list,
    "admin_clear_guild_data":admin_clear_guild_data,
    "guild_chat_cb":guild_chat_cb,
    "debug_guild_menu":debug_guild_menu,
    "debug_base_function":debug_base_function,
}