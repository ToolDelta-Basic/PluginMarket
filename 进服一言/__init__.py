from tooldelta import Plugin, plugins, Config, game_utils, Utils, Print, TYPE_CHECKING
import time
import requests

@plugins.add_plugin
class NewPlugin(Plugin):
    name = "进服一言"
    author = "机入"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)


    def on_def(self):
        pass


    @Utils.thread_func("一言")
    def on_player_join(self, playername: str):
        try:
            time.sleep(10) #等待玩家完全进入
            data = requests.get('https://v1.xqapi.com/v1.php?y =默认&type=text')
            if data.status_code == 200:
                self.game_ctrl.say_to(playername, f"一言: {data.text}")
            else:
                return
        except requests.RequestException as e:  # 异常
            print(f"一言异常 {e}")