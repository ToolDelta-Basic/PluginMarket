from tooldelta import Player, game_utils, fmts
from guild.models import GuildRank,VaultItem
from guild.config import Config

def quick_create_guild(self, player: Player, args: tuple):
    """快捷创建公会"""
    player_xuid = self.xuidm.get_xuid_by_name(player.name, allow_offline=True)
    
    # 检查玩家是否已有公会
    guild = self.guild_manager.get_guild_by_player(player.name)
    if guild:
        player.show("§l§a公会 §d>> §r你已经有公会了")
        return True
    
    # 获取公会名称
    guild_name = args[0] if args and args[0] else None
    
    if not guild_name:
        player.show("§l§a公会 §d>> §r请输入公会名称，例如: 公会创建 我的公会")
        return True
        
    if len(guild_name) < 2 or len(guild_name) > 16:
        player.show("§l§a公会 §d>> §r公会名必须在2-16个字符之间")
        return True
    
    # 检查条件
    if player.getScore(Config.GUILD_SCOREBOARD) < Config.GUILD_CREATION_COST:
        player.show(f"§l§a公会 §d>> §r创建公会需要{Config.GUILD_CREATION_COST}个积分")
        return True
    
    # 扣除钻石并创建公会
    self.game_ctrl.sendwocmd(f"scoreboard players remove {player.name} {Config.GUILD_SCOREBOARD} {Config.GUILD_CREATION_COST}")
    
    if self.guild_manager.create_guild(player_xuid, player.name, guild_name):
        player.show(f"§l§a公会 §d>> §r已创建公会 §e{guild_name}")
        # 通知所有在线玩家
        self.game_ctrl.sendcmd(
            f'/tellraw @a {{"rawtext":[{{"text":"§l§a公会 §d>> §r§e{player.name}§r 创建了公会 §e{guild_name}§r！"}}]}}'
        )
    else:
        player.show("§l§a公会 §d>> §r该公会名已存在")
        self.game_ctrl.sendwocmd(f"scoreboard players add {player.name} {Config.GUILD_SCOREBOARD} {Config.GUILD_CREATION_COST}")
    
    return True

def quick_join_guild(self, player: Player, args: tuple):
    """快捷加入公会"""
    if self.guild_manager.get_guild_by_player(player.name):
        player.show("§l§a公会 §d>> §r你已经加入了一个公会")
        return True
    
    search_name = args[0] if args and args[0] else None
    
    if not search_name:
        player.show("§l§a公会 §d>> §r请输入公会名字，例如: 公会加入 某某公会")
        return True
    
    # 搜索匹配的公会
    guilds = self.guild_manager._load_guilds()
    matched_guilds = [g for g in guilds.values() if search_name.lower() in g.name.lower()]
    
    if not matched_guilds:
        player.show("§l§a公会 §d>> §r未找到匹配的公会")
        return True
    
    # 选择公会
    if len(matched_guilds) == 1:
        target_guild = matched_guilds[0]
    else:
        player.show(f"§l§a公会 §d>> §r找到多个匹配的公会，请选择:")
        for i, guild in enumerate(matched_guilds, 1):
            player.show(f"§e{i}. §f{guild.name} §7(会长: {guild.owner})")
        
        player.show("§7请输入序号选择公会:")
        choice = game_utils.waitMsg(player.name, timeout=30)
        
        if not choice or not choice.isdigit() or int(choice) < 1 or int(choice) > len(matched_guilds):
            player.show("§l§a公会 §d>> §r无效的选择")
            return True
            
        target_guild = matched_guilds[int(choice) - 1]
    
    # 检查人数上限
    if len(target_guild.members) >= Config.MAX_GUILD_MEMBERS:
        player.show("§l§a公会 §d>> §r该公会已满员")
        return True
    
    # 获取有邀请权限的在线成员
    online_inviters = []
    for member in target_guild.members:
        if member.name in self.game_ctrl.allplayers and target_guild.has_permission(member.name, "invite"):
            online_inviters.append(member.name)
    
    if not online_inviters:
        player.show("§l§a公会 §d>> §r没有可以处理申请的成员在线")
        return True
    
    # 选择一个在线的管理员发送申请
    inviter = online_inviters[0]  # 可以改进为选择职位最高的
    
    # 发送申请
    self.game_ctrl.sendcmd(
        f'/tellraw {inviter} {{"rawtext":[{{"text":"§l§a公会 §d>> §r§e{player.name} §f申请加入公会 §e{target_guild.name}\\n§f输入 §a同意 §f或 §c拒绝"}}]}}'
    )
    player.show(f"已向 {inviter} 发送加入申请")
    
    reply = game_utils.waitMsg(inviter, timeout=60)
    if reply == "同意":
        if self.guild_manager.add_member(target_guild.name, player.name, inviter):
            player.show(f"§l§a公会 §d>> §r你已加入公会 {target_guild.name}")
            self.game_ctrl.sendcmd(
                f'/tellraw {inviter} {{"rawtext":[{{"text":"§l§a公会 §d>> §r已同意申请"}}]}}'
            )
            # 通知其他在线成员
            for member in target_guild.members:
                if member.name in self.game_ctrl.allplayers and member.name != player.name:
                    self.game_ctrl.sendcmd(
                        f'/tellraw {member.name} {{"rawtext":[{{"text":"§l§a公会 §d>> §r§e{player.name}§r 加入了公会"}}]}}'
                    )
    elif reply == "拒绝":
        player.show("§l§a公会 §d>> §r你的申请被拒绝了")
    else:
        player.show("§l§a公会 §d>> §r申请超时")
    
    return True

def quick_view_guild(self, player: Player, args: tuple):
    """快捷查看公会信息"""
    self._handle_view_guild(player)
    return True

def quick_view_members(self, player: Player, args: tuple):
    """快捷查看成员列表"""
    self._handle_view_members(player)
    return True

def quick_base_action(self, player: Player, args: tuple):
    """快捷公会据点操作"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    
    action = args[0] if args and args[0] else None
    
    if action == "tp":
        if not guild.base:
            player.show("§l§a公会 §d>> §r公会尚未设置据点，请先设置")
            return True
        return self._handle_return_base(player)
    elif action == "set":
        # 检查权限 - 只有会长可以设置据点
        member = guild.get_member(player.name)
        if not member or member.rank != GuildRank.OWNER:
            player.show("§l§a公会 §d>> §r只有会长才能设置公会据点")
            player.show("§7当前权限: §f" + (member.rank.display_name if member else "无"))
            return True
        return self._handle_set_base(player)
    else:
        # 显示据点信息
        member = guild.get_member(player.name)
        is_owner = member and member.rank == GuildRank.OWNER

        if guild.base:
            base = guild.base
            dim_name = Config.DIMENSION_NAMES.get(base.dimension, f"维度{base.dimension}")
            player.show(f"§l§a公会据点§r\n§7位置: §f{dim_name} ({base.x:.1f}, {base.y:.1f}, {base.z:.1f})")
            player.show("§7使用 §f.公会据点 tp §7传送到据点")
            if is_owner:
                player.show("§7使用 §f.公会据点 set §7重新设置据点")
        else:
            player.show("§l§a公会 §d>> §r公会尚未设置据点")
            if is_owner:
                player.show("§7使用 §f公会据点 set §7设置据点")
            else:
                player.show("§7只有会长才能设置据点")
    
    return True

def quick_donate(self, player: Player, args: tuple):
    """快捷捐献物品"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True
    
    item_name = args[0] if args and args[0] else None
    amount = args[1] if args and args[1] else 1
    
    if not item_name:
        player.show("§l§a公会 §d>> §r请输入物品名称 (如: 钻石, 绿宝石, 金锭, 铁锭)")
        return True
    
    if amount <= 0:
        player.show("§l§a公会 §d>> §r数量必须大于0")
        return True
    
    item_map = {
        "钻石": ("minecraft:diamond", 10, 5),
        "绿宝石": ("minecraft:emerald", 5, 3),
        "金锭": ("minecraft:gold_ingot", 2, 1),
        "铁锭": ("minecraft:iron_ingot", 1, 0.5)
    }
    
    item_info = item_map.get(item_name.lower())
    if not item_info:
        player.show("§l§a公会 §d>> §r不支持的捐献物品")
        return True
    
    item_id, contrib_per_item, exp_per_item = item_info
    
    if player.getItemCount(item_id) < amount:
        player.show(f"§l§a公会 §d>> §r你只有 {player.getItemCount(item_id)} 个{item_name}")
        return True
    
    self.game_ctrl.sendwocmd(f"clear {player.name} {item_id} 0 {amount}")
    
    contribution = amount * contrib_per_item
    exp = int(amount * exp_per_item)
    
    # 更新贡献度
    self.guild_manager.update_contribution(player.name, contribution)
    
    # 重新加载公会数据并更新经验值
    guilds = self.guild_manager._load_guilds(force_reload=True)
    guild_id = guild.guild_id
    
    if guild_id in guilds:
        # 更新公会经验
        guild = guilds[guild_id]
        guild.exp += exp

        # 等级提升逻辑
        while True:
            next_level = guild.level + 1
            next_exp_needed = Config.GUILD_LEVEL_EXP.get(next_level)
            if not next_exp_needed:
                break  # 已到最大等级
            if guild.exp >= next_exp_needed:
                guild.level += 1
                guild.exp -= next_exp_needed
                guild.add_log(f"{guild.name} 公会升级到 Lv{guild.level}！")
            else:
                break
        
        # 保存公会数据
        self.guild_manager.save_guilds(guilds)
        
        player.show(f"§l§a公会 §d>> §r捐献成功！获得 {contribution} 贡献度，公会获得 {exp} 经验")
    else:
        player.show("§l§a公会 §d>> §r捐献失败，公会数据异常")
        fmts.print_err(f"捐献失败: 公会ID {guild_id} 不存在于加载的数据中")
    
    return True

def quick_announcement(self, player: Player, args: tuple):
    """快捷查看/设置公告"""
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
        player.show("§l§a公会 §d>> §r你没有设置公告的权限")
        return True
    
    player.show("§7输入 '设置' 来修改公告，其他任意键返回")
    choice = game_utils.waitMsg(player.name, timeout=20)
    
    if choice == "设置":
        player.show("§l§a公会 §d>> §r请输入新的公告内容 (最多100字):")
        new_announcement = game_utils.waitMsg(player.name, timeout=60)
        
        if new_announcement and len(new_announcement) <= 100:
            guilds = self.guild_manager._load_guilds(force_reload=True)
            guild.announcement = new_announcement
            guild.add_log(f"{player.name} 更新了公告")
            self.guild_manager.save_guilds(guilds)
            player.show("§l§a公会 §d>> §r公告已更新")
            
            # 通知在线成员
            for member in guild.members:
                if member.name in self.game_ctrl.allplayers:
                    self.game_ctrl.sendcmd(
                        f'/tellraw {member.name} {{"rawtext":[{{"text":"§l§a公会 §d>> §r公告已更新，输入 公会 公告 查看"}}]}}'
                    )
        else:
            player.show("§l§a公会 §d>> §r公告内容无效或过长")
    
    return True

def quick_vault_menu(self, player: Player, args: tuple):
    """快捷仓库菜单"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    return self._handle_vault(player)

def quick_vault_sell(self, player: Player, args: tuple):
    """快速出售物品到仓库"""
    guild = self.guild_manager.get_guild_by_player(player.name)
    if not guild:
        player.show("§l§a公会 §d>> §r你尚未加入任何公会")
        return True

    # 所有成员都可以使用仓库

    user_input = args[0] if args and args[0] else None
    count = args[1] if len(args) > 1 and args[1] else 1
    price = args[2] if len(args) > 2 and args[2] else 0

    if not user_input:
        player.show("§l§a公会仓库 §d>> §r请输入物品名称，例如: 出售 钻石 10 500")
        player.show("§7支持中文名称: 出售 钻石 10 500")
        player.show("§7也支持英文ID: 出售 minecraft:diamond 10 500")
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

    # 显示找到的物品
    chinese_name = self.item_matcher.get_chinese_name(item_id)
    player.show(f"§l§a公会仓库 §d>> §r找到物品: §f{chinese_name}")

    # 检查仓库容量
    max_slots = Config.VAULT_INITIAL_SLOTS  # 固定10000格
    if len(guild.vault_items) >= max_slots:
        player.show("§l§a公会仓库 §d>> §r仓库已满")
        return True

    # 检查玩家是否有该物品
    item_count = player.getItemCount(item_id)
    if item_count < count:
        player.show(f"§l§a公会仓库 §d>> §r你只有 {item_count} 个该物品，无法出售 {count} 个")
        return True

    # 如果没有指定价格，使用建议价格
    if price <= 0:
        price = guild.get_item_value(item_id) * count
        player.show(f"§l§a公会仓库 §d>> §r使用建议价格: {price} 贡献点")

    # 确认出售
    item_name = self._get_item_display_name(item_id)
    player.show(f"§l§a公会仓库 §d>> §r确认出售 §f{item_name} §7x{count} §r价格 §e{price}贡献点§r？")
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
        price=price,
        seller=player.name
    )

    guild.vault_items.append(vault_item)
    guild.add_log(f"{player.name} 出售了 {item_name} x{count} (价格{price}贡献点)")

    # 保存数据
    self.guild_manager.save_guilds(guilds)

    player.show(f"§l§a公会仓库 §d>> §r出售成功！{item_name} x{count} 已上架，价格 {price} 贡献点")
    return True


handlers_quick = {
    "quick_create_guild":quick_create_guild,
    "quick_join_guild":quick_join_guild,
    "quick_view_guild":quick_view_guild,
    "quick_view_members":quick_view_members,
    "quick_base_action":quick_base_action,
    "quick_donate":quick_donate,
    "quick_announcement":quick_announcement,
    "quick_vault_menu":quick_vault_menu,
    "quick_vault_sell":quick_vault_sell,
}