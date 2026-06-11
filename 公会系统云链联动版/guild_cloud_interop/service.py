from tooldelta import fmts

# FIRE 数据事务处理器 FIRE
class DataTransaction:
    """数据事务处理器 - 确保数据一致性"""

    def __init__(self, guild_manager):
        self.guild_manager = guild_manager
        self.backup_data = None
        self.operations = []
        self.success = True

    def __enter__(self):
        try:
            self.backup_data = self.guild_manager._load_guilds(force_reload=True)
            import copy
            self.backup_data = copy.deepcopy(self.backup_data)
        except Exception as e:
            fmts.print_err(f"事务备份失败：{e}")
            self.backup_data = {}
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None or not self.success:
            self.rollback()
            fmts.print_err(f"事务回滚：{exc_val if exc_val else '操作失败'}")
            return False
        return True

    def rollback(self):
        """回滚数据到事务开始前的状态"""
        if self.backup_data:
            try:
                self.guild_manager.save_guilds(self.backup_data)
                self.guild_manager._cache = None
                self.guild_manager._player_guild_cache = {}
                fmts.print_inf("数据已回滚到事务开始前的状态")
            except Exception as e:
                fmts.print_err(f"回滚失败：{e}")

    def mark_failed(self):
        """标记事务失败"""
        self.success = False