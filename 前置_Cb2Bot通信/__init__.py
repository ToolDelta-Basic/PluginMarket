import json
from collections.abc import Callable
from tooldelta import plugins, Plugin

AVALIABLE_CB = Callable[[list[str]], bool | None]


@plugins.add_plugin_as_api("Cb2Bot通信")
class TellrawCb2Bot(Plugin):
    name = "前置-命令方块与机器人数据通信"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._registered_msg_prefixs = {}

    ########################## API ###############################

    def regist_message_cb(self, prefix: str, cb: AVALIABLE_CB):
        """
        注册一个消息监听器

        Args:
            prefix (str): 消息前缀 (tellraw 第一个 rawtext文本)
            cb (AVALIABLE_CB): 监听回调
        """
        if not self._registered_msg_prefixs.get(prefix):
            self._registered_msg_prefixs[prefix] = [cb]
        else:
            self._registered_msg_prefixs[prefix].append(cb)

    ##############################################################

    @plugins.add_packet_listener(9)
    def evt_handler(self, pkt):
        # 激活雪球菜单
        if pkt["TextType"] == 9:
            messages = json.loads(pkt["Message"].strip("\n")).get("rawtext")
            msg_table = [i["text"] for i in messages if i.get("text")]
            if not msg_table:
                # 极端特殊的情况 或者 不是rawtext msg 或者 敏感词
                return False
            prefix = msg_table[0]
            if prefix in self._registered_msg_prefixs.keys():
                for cb in self._registered_msg_prefixs[prefix]:
                    res = cb(msg_table[1:])
                    if res is None or res:
                        return True
        return False
