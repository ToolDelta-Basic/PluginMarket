import websocket
import json
from tooldelta import cfg, fmts, utils, Chat, Player, plugin_entry

from tooldelta import Plugin

PLUGIN_CONFIG = {
    "核心功能配置": {
        "ws服务端地址": "ws://chat.wmzy.org:9999",
        "加入的聊天频道": ["MyServer", "public"],
        "互通显示服务器名称": "MyRentalServer",
        "接收消息的格式": "§b| §f[服务器] §a[玩家]§7: §f[消息]",
        # "是否开启插件指令": True,
        # "插件指令前缀": ".cl"
    },
    "没啥用的额外功能配置": {},
}


def replace_var(
    content: str = "",
    channel: str = "",
    server: str = "",
    player: str = "",
    message: str = "",
) -> str:
    for text, var in (
        ("[频道]", channel),
        ("[服务器]", server),
        ("[玩家]", player),
        ("[消息]", message),
    ):
        content = content.replace(text, var)
    return content


def server_resp(args):
    fmts.print_war("MCChatLinker - " + args.get("msg"))


def on_ws_error(_, T_T):
    fmts.print_err(f"ws客户端出现错误, {T_T}")


def on_ws_close(_, _1, _2):
    fmts.print_inf("坏掉了喵...,")


class MCChatLinker(Plugin):
    version = (0, 0, 1)
    name = "多服聊天互通"
    author = "WuMing"
    description = "简单，轻量的多服互通"

    def __init__(self, frame):
        super().__init__(frame)
        self.OoO = {2: self.chat_msg, 3: self.custom_msg, 10: server_resp}
        self.ws_client: websocket = None
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(PLUGIN_CONFIG), PLUGIN_CONFIG, self.version
        )
        self.cfg_ws_url: str = self.cfg["核心功能配置"]["ws服务端地址"]
        self.cfg_chat_channel: list = self.cfg["核心功能配置"]["加入的聊天频道"]
        self.cfg_server_display_name: str = self.cfg["核心功能配置"][
            "互通显示服务器名称"
        ]
        self.cfg_msg_format: str = self.cfg["核心功能配置"]["接收消息的格式"]
        # self.cfg_plugin_cmd_enable: bool = self.cfg["核心功能配置"]["是否开启插件指令"]
        # self.cfg_cmd_prefix: str = self.cfg["核心功能配置"]["插件指令前缀"]
        fmts.print_suc("加载配置完毕")
        self.run_ws_client()
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)

    @utils.thread_func("为播搜可特进程，很吊")
    def run_ws_client(self):
        self.ws_client = websocket.WebSocketApp(
            self.cfg_ws_url,
            on_message=self.on_ws_message,
            on_error=on_ws_error,
            on_close=on_ws_close,
            on_open=self.on_ws_open,
        )
        self.ws_client.run_forever()

    def chat_msg(self, args):
        self.game_ctrl.sendwocmd(
            '/tellraw @a {{"rawtext":[{{"text":"{}"}}]}}'.format(
                replace_var(
                    self.cfg_msg_format,
                    player=args.get("a"),
                    message=args.get("m"),
                    server=args.get("s"),
                )
            )
        )

    def custom_msg(self, args):
        self.game_ctrl.sendwocmd(
            '/tellraw @a {{"rawtext":[{{"text":"{}"}}]}}'.format(
                replace_var(
                    self.cfg_msg_format, message=args.get("m"), server=args.get("s")
                )
            )
        )

    def __set_chat(self):
        self.send2ws_server(1, c=self.cfg_chat_channel, n=self.cfg_server_display_name)

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg

        self.send2ws_server(2, a=player, m=msg)

    def on_player_join(self, playerf: Player):
        player = playerf.name
        self.send2ws_server(3, m=player + " 加入了游戏")

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        self.send2ws_server(3, m=player + " 退出了游戏")

    def on_ws_open(self, _):
        fmts.print_suc(f"成功连接到聊天互通ws服务端: {self.cfg_ws_url}")
        self.__set_chat()

    def on_ws_message(self, _, msg):
        try:
            msg_data = json.loads(msg)
            self.OoO[int(msg_data.get("o"))](msg_data.get("d", {}))
        except json.JSONDecodeError:
            fmts.print_war("互通消息解析失败，怎么可能出现这个错误呢喵？")
        except Exception as e:
            fmts.print_err(f"处理互通消息遇到如下错误 {e}")

    def send2ws_server(self, o, **d):
        """给ws服务端发送消息通知"""
        if self.ws_client:
            self.ws_client.send(json.dumps({"o": o, "d": {**d}}))


entry = plugin_entry(MCChatLinker)
