import os
import time
from typing import Dict, List, Optional, Tuple, Any, Set


from tooldelta import fmts
from tooldelta.utils import tempjson
from guild.config import Config
from guild.models import GuildData, GuildMember,GuildRank
from guild.service import DataTransaction

# FIRE 公会管理器 FIRE
class GuildManager:
    """公会管理器，负责公会数据的增删改查"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._cache: Optional[Dict[str, GuildData]] = None
        self._last_load_time = 0
        self.cache_duration = Config.CACHE_DURATION
        self._player_guild_cache: Dict[str, str] = {}
        self._dirty_guilds: Set[str] = set()  # 标记需要保存的公会
        self._last_save_time = 0
        self._batch_operations: List[callable] = []  # 批量操作队列

    def validate_guild_data(self, guild_data: GuildData) -> Tuple[bool, List[str]]:
        """验证公会数据的完整性"""
        errors = []

        # 检查基本字段
        if not guild_data.name:
            errors.append("公会名称为空")

        if not guild_data.guild_id:
            errors.append("公会ID为空")

        if not guild_data.members:
            errors.append("公会没有成员")

        # 检查会长
        owners = [m for m in guild_data.members if m.rank == GuildRank.OWNER]
        if len(owners) != 1:
            errors.append(f"公会应该有且仅有一个会长，当前有{len(owners)}个")

        # 检查成员数量
        if len(guild_data.members) > Config.MAX_GUILD_MEMBERS:
            errors.append(f"成员数量超过限制：{len(guild_data.members)}/{Config.MAX_GUILD_MEMBERS}")

        # 检查仓库物品
        if len(guild_data.vault_items) > Config.VAULT_INITIAL_SLOTS:
            errors.append(f"仓库物品超过容量：{len(guild_data.vault_items)}/{Config.VAULT_INITIAL_SLOTS}")

        # 检查数据类型
        if not isinstance(guild_data.exp, (int, float)) or guild_data.exp < 0:
            errors.append("公会经验值无效")

        if not isinstance(guild_data.level, int) or guild_data.level < 1:
            errors.append("公会等级无效")

        return len(errors) == 0, errors

    def create_transaction(self):
        """创建数据事务"""
        return DataTransaction(self)
    
    def _load_guilds(self, force_reload: bool = False) -> Dict[str, GuildData]:
        """加载公会数据，带缓存"""
        current_time = time.time()
        if (not force_reload and self._cache is not None and 
            current_time - self._last_load_time < self.cache_duration):
            return self._cache
        
        raw_data = tempjson.load_and_read(self.file_path, need_file_exists=False, default={})
        self._cache = {}
        self._player_guild_cache.clear()
        
        load_errors = []
        for guild_id, guild_dict in raw_data.items():
            try:
                guild = GuildData.from_dict(guild_dict, outer_key=guild_id)

                # 验证数据完整性
                is_valid, errors = self.validate_guild_data(guild)
                if not is_valid:
                    load_errors.extend([f"公会{guild_id}: {error}" for error in errors])
                    continue

                self._cache[guild_id] = guild
                # 更新玩家-公会缓存
                for member in guild.members:
                    self._player_guild_cache[member.name] = guild_id
            except Exception as e:
                load_errors.append(f"加载公会 {guild_id} 时出错: {e}")
                continue

        # 记录加载错误
        if load_errors:
            fmts.print_err(f"加载公会数据时发现 {len(load_errors)} 个错误")
            for error in load_errors[:3]:  # 只显示前3个错误
                fmts.print_err(f"  - {error}")
            if len(load_errors) > 3:
                fmts.print_err(f"  ... 还有 {len(load_errors) - 3} 个错误")

                
        self._last_load_time = current_time
        return self._cache
    
    def save_guilds(self, guilds: Dict[str, GuildData], force: bool = False) -> bool:
        """保存公会数据，支持批量保存优化"""
        try:
            current_time = time.time()

            # 如果不是强制保存且距离上次保存时间不足，则延迟保存
            if not force and current_time - self._last_save_time < Config.BATCH_SAVE_INTERVAL:
                self._dirty_guilds.update(guilds.keys())
                return True

            # 确保数据目录存在
            data_dir = os.path.dirname(self.file_path)
            if not os.path.exists(data_dir):
                try:
                    os.makedirs(data_dir)
                    fmts.print_inf(f"创建公会系统数据目录: {data_dir}")
                except Exception as e:
                    fmts.print_err(f"创建公会系统数据目录失败: {e}")
                    return False

            raw_data = {}
            for gid, guild in guilds.items():
                try:
                    guild_dict = guild.to_dict()
                    raw_data[gid] = guild_dict
                except Exception as e:
                    fmts.print_err(f"转换公会 {gid} 数据时出错: {e}")
                    continue

            # 写入文件
            tempjson.write(self.file_path, raw_data)

            # 更新缓存和状态
            self._cache = guilds.copy()
            self._last_load_time = current_time
            self._last_save_time = current_time
            self._dirty_guilds.clear()

            return True

        except Exception as e:
            fmts.print_err(f"保存公会数据时出错: {e}")
            import traceback
            fmts.print_err(traceback.format_exc())
            return False

    def mark_guild_dirty(self, guild_id: str) -> None:
        """标记公会数据已修改，需要保存"""
        self._dirty_guilds.add(guild_id)

    def flush_dirty_guilds(self) -> bool:
        """强制保存所有标记为脏的公会数据"""
        if not self._dirty_guilds or not self._cache:
            return True

        dirty_guilds = {gid: self._cache[gid] for gid in self._dirty_guilds if gid in self._cache}
        return self.save_guilds(dirty_guilds, force=True)
    
    def get_guild_by_player(self, player_name: str, force_reload: bool = False) -> Optional[GuildData]:
        """根据玩家名获取其所在公会"""
        guilds = self._load_guilds(force_reload=force_reload)
        guild_id = self._player_guild_cache.get(player_name)
        return guilds.get(guild_id) if guild_id else None
    
    def get_guild_by_name(self, guild_name: str) -> Optional[GuildData]:
        """根据公会名获取公会"""
        guilds = self._load_guilds()
        for guild in guilds.values():
            if guild.name == guild_name:
                return guild
        return None
    
    def create_guild(self, owner_xuid: str, owner_name: str, guild_name: str) -> bool:
        """创建公会"""
        guilds = self._load_guilds(force_reload=True)
        
        # 检查是否已有同名公会
        if any(g.name == guild_name for g in guilds.values()):
            return False
        
        owner_member = GuildMember(
            name=owner_name,
            rank=GuildRank.OWNER,
            join_time=time.time()
        )
        
        new_guild = GuildData(
            guild_id=owner_xuid,
            name=guild_name,
            owner=owner_name,
            members=[owner_member]
        )
        new_guild.add_log(f"公会 {guild_name} 成立")
        
        guilds[owner_xuid] = new_guild
        self.save_guilds(guilds)
        return True
    
    def add_member(self, guild_name: str, player_name: str, inviter: str = None) -> bool:
        """添加成员到公会"""
        guilds = self._load_guilds(force_reload=True)
        guild = self.get_guild_by_name(guild_name)
        
        if not guild or len(guild.members) >= Config.MAX_GUILD_MEMBERS:
            return False
        
        new_member = GuildMember(
            name=player_name,
            rank=GuildRank.MEMBER,
            join_time=time.time()
        )
        
        guild.members.append(new_member)
        guild.add_log(f"{player_name} 加入公会" + (f" (邀请人: {inviter})" if inviter else ""))
        
        # 更新缓存
        self._player_guild_cache[player_name] = guild.guild_id
        self.save_guilds(guilds)
        return True
    
    def remove_member(self, player_name: str) -> Optional[str]:
        """从公会移除成员，返回公会名"""
        guilds = self._load_guilds(force_reload=True)
        guild = self.get_guild_by_player(player_name)

        if not guild:
            return None

        # 检查是否是会长
        member = guild.get_member(player_name)
        if member and member.rank == GuildRank.OWNER:
            return None  # 会长不能退出公会，只能解散

        guild.members = [m for m in guild.members if m.name != player_name]
        guild.add_log(f"{player_name} 退出公会")

        # 更新缓存
        if player_name in self._player_guild_cache:
            del self._player_guild_cache[player_name]
        self.save_guilds(guilds)
        return guild.name
    
    def set_member_rank(self, guild: GuildData, player_name: str, new_rank: GuildRank) -> bool:
        """设置成员职位"""
        guilds = self._load_guilds(force_reload=True)
        member = guild.get_member(player_name)
        
        if not member or member.rank == GuildRank.OWNER:
            return False
        
        old_rank = member.rank
        member.rank = new_rank
        guild.add_log(f"{player_name} 职位变更: {old_rank.display_name} -> {new_rank.display_name}")
        
        self.save_guilds(guilds)
        return True
    
    def update_contribution(self, player_name: str, amount: int) -> bool:
        """更新成员贡献度"""
        guild = self.get_guild_by_player(player_name)

        if not guild:
            return False

        member = guild.get_member(player_name)
        if member:
            member.contribution += amount
            guild.stats.total_contribution += amount
            self.mark_guild_dirty(guild.guild_id)
            return True
        return False

    def batch_update_members(self, updates: List[Tuple[str, str, Any]]) -> int:
        """批量更新成员信息"""
        success_count = 0

        for player_name, field_name, value in updates:
            guild = self.get_guild_by_player(player_name)
            if not guild:
                continue

            member = guild.get_member(player_name)
            if not member:
                continue

            if hasattr(member, field_name):
                setattr(member, field_name, value)
                self.mark_guild_dirty(guild.guild_id)
                success_count += 1

        # 批量保存
        if success_count > 0:
            self.flush_dirty_guilds()

        return success_count
    
    def update_online_status(self, online_players: List[str]) -> None:
        """更新在线状态"""
        guilds = self._load_guilds(force_reload=True)
        current_time = time.time()
        
        for guild in guilds.values():
            for member in guild.members:
                if member.name in online_players:
                    member.last_online = current_time
        
        self.save_guilds(guilds)