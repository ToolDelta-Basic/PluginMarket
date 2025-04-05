from tooldelta import Plugin, cfg, fmts, utils, game_utils, plugin_entry, constants
import time


class xunluo(Plugin):
    name = "巡逻"
    author = "猫七街"
    version = (0, 0, 7)

    def __init__(self, frame):
        super().__init__(frame)
        self._default_cfg = {
            "间隔时间（秒）": 0.1,
        }
        self._std_cfg = {"间隔时间（秒）": float}
        try:
            self._cfg, _ = cfg.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )
        except Exception as e:
            fmts.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()

        # 屏蔽 TextType:10 的刷屏。
        def on_filter(packet) -> bool:
            return packet["TextType"] == 10

        self.ListenActive(self.on_inject)
        self.ListenPacket(constants.PacketIDS.Text, on_filter)

    def _patrol_loop(self):
        bot_name = self.frame.launcher.get_bot_name()
        while True:
            try:
                players = game_utils.getTarget("@e[type=player]")
                for player in players:
                    if player == bot_name:
                        continue
                    if player not in self.game_ctrl.allplayers:
                        # 由 空白 (1279170334) 赞助 fix
                        fmts.print_war(f"巡逻插件: 玩家已下线: {player}, 跳过")
                        continue
                    # 由 空白 (1279170334) 赞助 fix
                    self.game_ctrl.sendwocmd(
                        f'execute as @a[name="{player}"] at @s run tp @a[name="{self.game_ctrl.bot_name}"] ~ 325 ~'
                    )
                    time.sleep(self._cfg["间隔时间（秒）"])
            except Exception as e:
                fmts.print_err(f"巡逻出错: {e}")

    def on_inject(self):
        utils.createThread(self._patrol_loop, (), "巡逻")


entry = plugin_entry(xunluo, "巡逻")
