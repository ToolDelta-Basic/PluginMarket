import json
import websocket
import time
import re
import threading
from typing import Any
from collections.abc import Callable
from tooldelta import (
    Plugin,
    cfg,
    utils,
    fmts,
    Chat,
    Player,
    plugin_entry,
    InternalBroadcast,
)
try:
    from tooldelta.utils.mc_translator import translate
except ImportError:
    translate = None


EASTER_EGG_QQIDS = {2528622340: ("SuperScript", "Super")}


class QQMsgTrigger:
    def __init__(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[[int, list[str]], None],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        self.triggers = triggers
        self.argument_hint = argument_hint
        self.usage = usage
        self.func = func
        self.args_pd = args_pd
        self.op_only = op_only

    def match(self, msg: str):
        for trigger in self.triggers:
            if msg.startswith(trigger):
                return trigger
        return None


def remove_cq_code(content):
    cq_start = content.find("[CQ:")
    while cq_start != -1:
        cq_end = content.find("]", cq_start) + 1
        content = content[:cq_start] + content[cq_end:]
        cq_start = content.find("[CQ:")
    return content


def create_result_cb():
    ret = [None]
    lock = threading.Lock()
    lock.acquire()

    def getter(timeout=60):
        lock.acquire(timeout=timeout)
        return ret[0]

    def setter(s):
        ret[0] = s
        lock.release()

    return getter, setter


CQ_IMAGE_RULE = re.compile(r"\[CQ:image,([^\]])*\]")
CQ_VIDEO_RULE = re.compile(r"\[CQ:video,[^\]]*\]")
CQ_FILE_RULE = re.compile(r"\[CQ:file,[^\]]*\]")
CQ_AT_RULE = re.compile(r"\[CQ:at,[^\]]*\]")
CQ_REPLY_RULE = re.compile(r"\[CQ:reply,[^\]]*\]")
CQ_FACE_RULE = re.compile(r"\[CQ:face,[^\]]*\]")


def replace_cq(content: str):
    for i, j in (
        (CQ_IMAGE_RULE, "[图片]"),
        (CQ_FILE_RULE, "[文件]"),
        (CQ_VIDEO_RULE, "[视频]"),
        (CQ_AT_RULE, "[@]"),
        (CQ_REPLY_RULE, "[回复]"),
        (CQ_FACE_RULE, "[表情]"),
    ):
        content = i.sub(j, content)
    return content


class QQLinker(Plugin):
    version = (0, 0, 10)
    name = "云链群服互通"
    author = "大庆油田"
    description = "提供简单的群服互通"
    QQMsgTrigger = QQMsgTrigger

    def __init__(self, f):
        super().__init__(f)
        self.ws = None
        self.reloaded = False
        self.triggers: list[QQMsgTrigger] = []
        CFG_DEFAULT = {
            "云链设置": {"地址": "ws://127.0.0.1:5556", "校验码": None},
            "消息转发设置": {
                "链接的群聊": 194838530,
                "游戏到群": {
                    "是否启用": False,
                    "转发格式": "<[玩家名]> [消息]",
                    "仅转发以下符号开头的消息(列表为空则全部转发)": ["#"],
                    "屏蔽以下字符串开头的消息": [".", "。"],
                },
                "群到游戏": {
                    "是否启用": True,
                    "转发格式": "群 <[昵称]> [消息]",
                    "屏蔽的QQ号": [2398282073],
                },
            },
            "指令设置": {
                "可以对游戏执行指令的QQ号名单": [2528622340, 2483724640],
                "是否允许查看玩家列表": True,
            },
        }
        cfg_std = cfg.auto_to_std(CFG_DEFAULT)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg_std, CFG_DEFAULT, self.version
        )
        self.enable_game_2_group = self.cfg["消息转发设置"]["游戏到群"]["是否启用"]
        self.enable_group_2_game = self.cfg["消息转发设置"]["群到游戏"]["是否启用"]
        self.enable_playerlist = self.cfg["指令设置"]["是否允许查看玩家列表"]
        self.linked_group = self.cfg["消息转发设置"]["链接的群聊"]
        self.block_qqids = self.cfg["消息转发设置"]["游戏到群"]
        self.game2qq_trans_chars = self.cfg["消息转发设置"]["游戏到群"][
            "仅转发以下符号开头的消息(列表为空则全部转发)"
        ]
        self.game2qq_block_prefixs = self.cfg["消息转发设置"]["游戏到群"][
            "屏蔽以下字符串开头的消息"
        ]
        self.can_exec_cmd = self.cfg["指令设置"]["可以对游戏执行指令的QQ号名单"]
        self.waitmsg_cbs = {}
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)
        self.plugin = []

    # ------------------------ API ------------------------
    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[[int, list[str]], Any],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        self.triggers.append(
            QQMsgTrigger(triggers, argument_hint, usage, func, args_pd, op_only)
        )

    def is_qq_op(self, qqid: int):
        return qqid in self.can_exec_cmd

    # ------------------------------------------------------
    def on_def(self):
        self.tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)

    def on_inject(self):
        self.connect_to_websocket()
        self.init_ba