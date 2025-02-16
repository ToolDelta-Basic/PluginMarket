from tooldelta import Plugin, plugins, Config, Print, Utils, game_utils
from tooldelta.launch_cli import FrameNeOmgAccessPoint
import time


@plugins.add_plugin
class xunluo(Plugin):
    name = "巡逻"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._default_cfg = {
            "间隔时间（秒）": 0.1,
        }

        self._std_cfg = {"间隔时间（秒）": float}

        try:
            self._cfg, _ = Config.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )

        except Exception as e:
            Print.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()

    def get_neomega(self):
        if isinstance(self.frame.launcher, FrameNeOmgAccessPoint):
            return self.frame.launcher.omega
        else:
            raise ValueError("此启动框架无法使用 NeOmega API")

    def _patrol_loop(self):
        neomega = self.get_neomega()
        bot_info = neomega.get_bot_basic_info()
        bot_name = bot_info.BotName
        while True:
            try:
                players = self.game_ctrl.allplayers
                for player in players:
                    if player == bot_name:
                        continue

                    pos = game_utils.getPosXYZ(Utils.to_player_selector(player))
                    self.game_ctrl.sendwocmd(f"tp {pos[0]} 320 {pos[2]}")
                    time.sleep(self._cfg["间隔时间（秒）"])

            except Exception as e:
                Print.print_err(f"巡逻出错: {e}")

    def on_inject(self):
        Utils.createThread(self._patrol_loop, (), "巡逻")
