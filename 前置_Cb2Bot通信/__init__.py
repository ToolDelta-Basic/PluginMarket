import json
from collections.abc import Callable
from tooldelta import Plugin, plugin_entry
from tooldelta.constants import PacketIDS

AVALIABLE_CB = Callable[[list[str]], bool | None]


class TellrawCb2Bot(Plugin):
    name = "前置-命令方块与机器人数据通信"
    author = "ToolDelta"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self._registered_msg_prefixs: dict[str, dict[int, list[AVALIABLE_CB]]] = {}
        self.ListenPacket(PacketIDS.IDText, self.evt_handler)

    ########################## API ###############################
    def regist_message_cb(self, prefix: str, cb: AVALIABLE_CB, priority: int = 1):
        """
        注册一个消息监听器
        Args:
            prefix (str): 消息前缀 (tellraw 第一个 rawtext文本)
            cb (AVALIABLE_CB): 监听回调 (返回 True 代表需要拦截)
            priority (int): 优先级, 优先级越高越先被执行且阻拦 (建议基本优先级为1)
        """
        self._registered_msg_prefixs.setdefault(prefix, {})
        self._registered_msg_prefixs[prefix].setdefault(priority, [])
        self._registered_msg_prefixs[prefix][priority].append(cb)

    ##############################################################

    def evt_handler(self, pkt):
        if pkt["TextType"] == 9:
            try:
                messages = json.loads(pkt["Message"].strip("\n"))["rawtext"]
            except Exception:
                self.game_ctrl.say_to("@a", f"无法处理数据： {pkt['Message']}")
                return False
            msg_table = [i["text"] for i in messages if i.get("text")]
            if not msg_table:
                # 极端特殊的情况 或者 不是 rawtext msg 或者 敏感词
                return False
            prefix = msg_table[0]
            if prefix in self._registered_msg_prefixs.keys():
                for _, funcs in sorted(
                    self._registered_msg_prefixs[prefix].items(),
                    key=lambda x: x[0],
                    reverse=True,
                ):
                    for func in funcs:
                        if func(msg_table[1:]):
                            return True
                return True
        return False


entry = plugin_entry(TellrawCb2Bot, "Cb2Bot通信")
