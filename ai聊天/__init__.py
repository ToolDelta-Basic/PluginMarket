from tooldelta import plugin_entry, Plugin, ToolDelta, Player, Chat, FrameExit, Config, Utils
import requests
import json

class NewPlugin(Plugin):
    name = "ai聊天"
    author = "机入"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        data = {
            "apikey": "114514",
            "url": "https://api.deepseek.com/chat/completions"
        }
        du = {
            "apikey": str,
            "url": str
        }
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name,
            du,
            data,
            self.version
        )
        self.apikey = cfg["apikey"]
        self.url = cfg["url"]
        # 注册函数
        self.ListenPreload(self.service)
        self.players = self.frame.get_players()

    @Utils.thread_func("ai聊天")
    def transfer(self, play: str, list) -> bool:
        try:
            player = self.players.getPlayerByName(play)
            data = ""
            if len(list) == 0:  # 未输入
                player.show("§c参数不合法")
                return
            else:
                for sites in list:
                    data = data + sites #参数拼接
                het = {
                "Authorization": f"Bearer {self.apikey}",
                "Content-Type": "application/json"
                }
                data = {
                "model": "deepseek-chat",
                "messages": [{
                    "role": "user",
                    "content": f"{data}"
                }],
                "stream": False
                }
            player.show("§l[§a租聘服§aAI§f] §e等待接口响应。")
            msg = requests.post(self.url, headers=het, data=json.dumps(data))
            xx = json.loads(msg.text)
            if msg.status_code == 200:
                player.show("§l[§a租聘服§aAI§f] §f" + xx["choices"][0]["message"]["content"])
            elif msg.status_code == 400:
                player.show("§l[§a租聘服§aAI§f] 请求格式错误")
            elif msg.status_code == 401:
                player.show("§l[§a租聘服§aAI§f] apikey错误 请更改后再试")
            else:
                player.show(f"§l[§a租聘服§aAI§f] 请求失败状态码 §e{msg.status_code}")
                return
        except Exception:
          print("未知原因")

    def service(self):
        memu = self.GetPluginAPI("聊天栏菜单")
        memu.add_trigger(
            ["ai"], 
            None, 
            "在租聘服和deepseek进行聊天对话", 
            self.transfer
        )

entry = plugin_entry(NewPlugin)