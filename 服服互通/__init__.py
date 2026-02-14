import asyncio
from tooldelta import (
    Plugin,
    cfg,
    fmts,
    utils,
    Chat,
    InternalBroadcast,
    plugin_entry,
)
from .protocol.interface.define import Data, format_data
from .protocol.interface.basic import BasicProtocol
from .protocol.SuperLink.basic import SuperLinkProtocol


class SuperLink(Plugin):
    name = "服服互通v4"
    author = "SuperScript/2401PT"
    version = (0, 0, 10)

    def __init__(self, frame):
        super().__init__(frame)
        self.read_cfgs()
        self.init_funcs()
        self.ListenActive(self.on_inject)
        self.ListenChat(self.on_player_message)

    def read_cfgs(self):
        CFG_DEFAULT = {
            "中心服务器IP": "自动选择线路",
            "服服互通协议": "SuperLink-v4@SuperScript",
            "协议附加配置": {
                "此租赁服的公开显示名": "???",
                "登入后自动连接到的频道大区名": "公共大区",
                "频道密码": "",
            },
            "基本互通配置": {
                "是否转发玩家发言": True,
                "转发聊天到本服格式": "<[服名]:[玩家名]> [消息]",
                "屏蔽以下前缀的信息上传": [".", "omg", "。"],
            },
        }
        CFG_STD = {
            "中心服务器IP": str,
            "服服互通协议": str,
            "协议附加配置": {
                "此租赁服的公开显示名": str,
                "登入后自动连接到的频道大区名": str,
                "频道密码": str,
            },
            "基本互通配置": {
                "是否转发玩家发言": bool,
                "转发聊天到本服格式": str,
                "屏蔽以下前缀的信息上传": cfg.JsonList(str),
            },
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )
        use_protocol: type[BasicProtocol] | None = {
            "SuperLink-v4@SuperScript": SuperLinkProtocol
        }.get(self.cfg["服服互通协议"])
        if use_protocol is None:
            fmts.print_err(f"协议不受支持: {self.cfg['服服互通协议']}")
            raise SystemExit
        self.active_protocol = use_protocol(
            self, self.cfg["中心服务器IP"], self.cfg["协议附加配置"]
        )
        basic_link_cfg = self.cfg["基本互通配置"]
        self.enable_trans_chat = basic_link_cfg["是否转发玩家发言"]
        self.trans_fmt = basic_link_cfg["转发聊天到本服格式"]

    def init_funcs(self):
        # --------------- API -------------------
        self.send = self.active_protocol.send
        self.send_and_wait_req = self.active_protocol.send_and_wait_req
        self.listen_for_data = self.active_protocol.listen_for_data
        self.ListenInternalBroadcast("superlink.event", self.listen_chat) # ?
        # ---------------------------------------

    def active(self):
        self.active_protocol.connect()

    def on_inject(self):
        fmts.print_inf("正在连接至服服互通..")
        self.active()

    @utils.thread_func("服服互通上报消息")
    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg

        if self.enable_trans_chat and self.active_protocol.is_actived():
            if not self.check_send(msg):
                return
            asyncio.run(
                self.send(format_data("chat.msg", {"ChatName": player, "Msg": msg}))
            )

    def check_send(self, msg: str):
        for prefix in self.cfg["基本互通配置"]["屏蔽以下前缀的信息上传"]:
            if msg.startswith(prefix):
                return False
        return True

    def listen_chat(self, dt: InternalBroadcast):
        data: Data = dt.data
        if data.type == "chat.msg" and self.enable_trans_chat:
            self.game_ctrl.say_to(
                "@a",
                utils.simple_fmt(
                    {
                        "[服名]": data.content["Sender"],
                        "[玩家名]": data.content["ChatName"],
                        "[消息]": data.content["Msg"],
                    },
                    self.cfg["基本互通配置"]["转发聊天到本服格式"],
                ),
            )
        return True


entry = plugin_entry(SuperLink, "服服互通")
