"""配置定义 for the player inventory polling pre-plugin."""

from tooldelta import cfg


STANDARD_CONFIG = {
    "发送命令间隔时长(单位：秒)": cfg.PNumber,
    "单次查询超时时间(秒)": cfg.PNumber,
}

DEFAULT_CONFIG = {
    "发送命令间隔时长(单位：秒)": 3,
    "单次查询超时时间(秒)": 1,
}
