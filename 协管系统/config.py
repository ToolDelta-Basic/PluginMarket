from tooldelta import cfg


CONFIG_DEFAULT = {
    "协管名单": [
        "player1",
        "player2",
        "bot_name"
    ],
    "Info": {
        "若不是协管": "§c§l您当前不是协管",
        "选择玩家列表": "§e§l请选择一个玩家:",
        "命令转发": "命令转发 *转发协管输入命令内容",
        "DeepSeek": "DeepSeek *DeepSeek",
    },
    "SetDeepOSeek": {
        "APIkey": "此处换成你的DeepSeekAPIkey",
        "DeepSeek提示词": "你现在要为我的世界基岩版服务器玩家提供服务,当玩家询问你指令相关问题,请你做出对应指令并仅仅只返回不带/前缀的指令信息,你需要依据玩家名做出对应的选择器替代,除此之外不要返回任何除命令以外信息,这是绝对的,尽量将玩家的请求转化为命令可实现形式,当有玩家询问了无法理解的内容请返回:非指令问题 不予处理",
        "max_history_length": 10,
        "DeepSeekModel": "deepseek-chat"
    },
    "SetDeepSeek": {
        "APIkey": "此处换成你的DeepSeekAPIkey",
        "DeepSeek提示词": "你是一只猫娘，回答字数限制八十字以内,不要带有任何emoji符号",
        "max_history_length": 15,
        "DeepSeekModel": "deepseek-chat",
        "stream": False
    },
    "随机插话": {
        "检测频率": 4,
        "插话概率": 0.5
    },
    "命令转发禁用关键词": [
        "clear",
        "kick",
        "op",
        "deop",
        "gamemode",
        "replaceitem",
        "setblock",
        "fill",
        "setworldspawn",
        "spawnpoint",
        "structure",
        "execute",
        "tag",
        "tickingarea",
        "clone",
        "difficulty",
        "event",
        "gamerule",
        "scoreboard"
    ],
    "快捷功能": {
        "视角投射": True,
        "玩家查询": True,
        "清理掉落物": True,
        "查询背包物品": True,
        "权限设置": True
    },
    "命令转发是否启用": True,
    "伪魔法指令DeepSeek是否启用": False,
    "协管名单是否启用": False,
    "随机插话是否启用": False,
    "DeepSeek": True,
    "在线时间计分板": "zxsj",
}

CONFIG_STD = {
    "协管名单": cfg.JsonList((int, str)),
    "Info": dict,
    "SetDeepOSeek": dict,
    "SetDeepSeek": dict,
    "随机插话": dict,
    "命令转发禁用关键词": cfg.JsonList(str),
    "快捷功能": {
        "视角投射": bool,
        "玩家查询": bool,
        "清理掉落物": bool,
        "查询背包物品": bool,
        "权限设置": bool
    },
    "命令转发是否启用": bool,
    "伪魔法指令DeepSeek是否启用": bool,
    "协管名单是否启用": bool,
    "随机插话是否启用": bool,
    "在线时间计分板": str,
}