from tooldelta import (
    Plugin,
    plugin_entry,
    Player,
    Chat,
    FrameExit,
    cfg,
    game_utils,
    utils,
    TYPE_CHECKING,
)


class NewPlugin(Plugin):
    name = "进服默认权限(必备)"
    author = "权威-马牛逼"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.game_ctrl = frame.game_ctrl
        self.ListenPreload(self.on_def)
        self.ListenPlayerJoin(self.on_player_join)

    # 注意，本权限系统需要玩家进入才能设置
    def on_def(self):
        pass

    def on_player_join(self, player: Player):
        self.game_ctrl.sendwocmd(
            f"/scoreboard players add @a qx 0"
        )  # 在这里可以修改分数，如果调用自定义，就把它设置为3
        score = player.getScore("qx")  # 计分板名称
        self.set_permission_based_on_score(player, score)

    def set_permission_based_on_score(self, player: Player, score):
        ab = player.abilities

        if score == 0:
            # 普通玩家权限（这里默认成员）
            ab.build = True
            ab.mine = True
            ab.doors_and_switches = True
            ab.open_containers = True
            ab.attack_players = True
            ab.attack_mobs = True
            ab.operator_commands = False
            ab.teleport = False
            print(f"玩家 {player.name}（分数 0）：已设置成员权限")

        elif score == 1:
            # 访客权限（啥也不能干）
            ab.build = False
            ab.doors_and_switches = False
            ab.open_containers = False
            ab.mine = False
            ab.attack_players = False
            ab.attack_mobs = False
            ab.operator_commands = False
            ab.teleport = False
            print(f"玩家 {player.name}（分数 1）：已设置访客权限")

        elif score == 2:
            # 操作员权限（全部开放）
            ab.build = True
            ab.mine = True
            ab.doors_and_switches = True
            ab.open_containers = True
            ab.attack_players = True
            ab.attack_mobs = True
            ab.operator_commands = True
            ab.teleport = True
            print(f"玩家 {player.name}（分数 2）：已设置操作员权限")

        elif score == 3:
            # 自定义权限 (有注语):应该怎么使用呢True代表允许,False代表禁止
            ab.build = False  # 放置方块
            ab.mine = False  # 破坏方块儿
            ab.doors_and_switches = False  # 打开门
            ab.open_containers = True  # 打开容器
            ab.attack_players = True  # 攻击玩家
            ab.attack_mobs = True  # 攻击生物
            ab.operator_commands = False  # 执行命令权限
            ab.teleport = False  # TP玩家权限
            print(f"玩家 {player.name}（分数 3）：已设置自定义权限")

        else:
            print(f"玩家 {player.name}（分数 {score}）：未匹配到权限规则")


entry = plugin_entry(NewPlugin)
