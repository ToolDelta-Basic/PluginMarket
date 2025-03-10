from tooldelta import (
    Plugin,
    utils,
    Player,
    plugin_entry,
)

import time
import requests


class NewPlugin(Plugin):
    name = "进服一言"
    author = "机入"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenPlayerJoin(self.on_player_join)

    def on_def(self):
        pass

    @utils.thread_func("一言")
    def on_player_join(self, player: Player):
        playername = player.name
        try:
            time.sleep(10)  # 等待玩家完全进入
            data = requests.get("https://v1.xqapi.com/v1.php?y =默认&type=text")
            if data.status_code == 200:
                self.game_ctrl.say_to(playername, f"一言: {data.text}")
            else:
                return
        except requests.RequestException as e:  # 异常
            print(f"一言异常 {e}")


entry = plugin_entry(NewPlugin)
