from tooldelta import plugin_entry, Plugin, Chat
import requests


class NewPlugin(Plugin):
    name = "检查人数"
    author = "虫子为"
    version = (0, 0, 1)  # 插件版本号, 可选, 是一个三元整数元组

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenChat(self.on_chat)
        self.frame.add_console_cmd_trigger(
            ["getip"], "[租赁服号] [密码(可选)]", "查询租赁服 IP", self.on_console_cmd
        )

    # def on_preload(self):
    #     chatbar = self.GetPluginAPI("聊天栏菜单")
    #     if TYPE_CHECKING:
    #         from 前置_聊天栏菜单 import ChatbarMenu
    #         chatbar: ChatbarMenu

    def on_chat(self, chat: Chat):
        # 在玩家发言后执行
        player = chat.player
        msg = chat.msg
        if msg[:3] == "*查询":
            List = msg.split(" ")
            player.show("正在查询中")
            if len(List) == 2:
                url = "http://198.44.179.197:5000/api/server_id"
                data = {"server_name": f"{List[1]}", "pwd": ""}
                r = requests.post(url, data=data)
                player.show(r.text)
            elif len(List) == 3:
                url = "http://198.44.179.197:5000/api/server_id"
                data = {"server_name": f"{List[1]}", "pwd": f"{List[2]}"}
                r = requests.post(url, data=data)
                player.show(r.text)

    def on_console_cmd(self, List: list[str]):
        self.print("正在查询中")
        if len(List) == 1:
            url = "http://198.44.179.197:5000/api/server_id"
            data = {"server_name": f"{List[0]}", "pwd": ""}
            r = requests.post(url, data=data)
            self.print(r.text)
        elif len(List) == 2:
            url = "http://198.44.179.197:5000/api/server_id"
            data = {"server_name": f"{List[0]}", "pwd": f"{List[1]}"}
            r = requests.post(url, data=data)
            self.print(r.text)
        else:
            self.print("参数错误")


entry = plugin_entry(NewPlugin)
