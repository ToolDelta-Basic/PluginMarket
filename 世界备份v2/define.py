import threading
from tooldelta import Plugin
from tooldelta import cfg as config


class WorldBackupBase:
    plugin: Plugin

    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin
        self.game_ctrl = plugin.game_ctrl

        CFG_DEFAULT = {
            "数据库名称": "world_timeline.db",
            "数据库跳过截断调用": False,
            "数据库跳过 fsync 调用": False,
            "启用调试": False,
            "每多少秒保存一次存档": 86400,
            "单个区块允许的最多时间点数量": 7,
            "如果区块未更改则不新增时间点": True,
            "存档恢复触发词": ".存档恢复",
            "管理员列表(这些人可以请求将数据库恢复为存档)": ["Happy2018new"],
        }
        cfg, _ = config.get_plugin_config_and_version(
            "世界备份第二世代",
            config.auto_to_std(CFG_DEFAULT),
            CFG_DEFAULT,
            self.plugin.version,
        )

        self.db_name = str(cfg["数据库名称"])
        self.no_grow_sync = bool(cfg["数据库跳过截断调用"])
        self.no_sync = bool(cfg["数据库跳过 fsync 调用"])
        self.enable_debug = bool(cfg["启用调试"])
        self.sync_delta_time = int(cfg["每多少秒保存一次存档"])
        self.max_time_point_count = int(cfg["单个区块允许的最多时间点数量"])
        self.no_change_when_no_change = bool(cfg["如果区块未更改则不新增时间点"])
        self.recover_trigger_str = str(cfg["存档恢复触发词"])
        self.ops_list = set(cfg["管理员列表(这些人可以请求将数据库恢复为存档)"])

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.plugin.make_data_path()
