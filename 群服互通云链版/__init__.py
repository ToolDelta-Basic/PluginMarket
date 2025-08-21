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
    version = (0, 0, 11)
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
        self.init_basic_triggers()

    def init_basic_triggers(self):
        @utils.thread_func("群服执行指令并获取返回")
        def sb_execute_cmd(qqid: int, cmd: list[str]):
            if self.is_qq_op(qqid):
                res = execute_cmd_and_get_zhcn_cb(" ".join(cmd))
                self.sendmsg(self.linked_group, res)
            else:
                self.sendmsg(self.linked_group, "你是管理吗你还发指令 🤓👆")

        def execute_cmd_and_get_zhcn_cb(cmd: str):
            try:
                result = self.game_ctrl.sendwscmd_with_resp(cmd, 10)
                if len(result.OutputMessages) == 0:
                    return ["😅 指令执行失败", "😄 指令执行成功"][
                        bool(result.SuccessCount)
                    ]
                if (result.OutputMessages[0].Message == "commands.generic.syntax") | (
                    result.OutputMessages[0].Message == "commands.generic.unknown"
                ):
                    return f'😅 未知的 MC 指令, 可能是指令格式有误: "{cmd}"'
                else:
                    if translate is not None:
                        mjon = "\n".join(
                            translate(i.Message, i.Parameters)
                            for i in result.OutputMessages
                        )
                    if result.SuccessCount:
                        if translate is not None:
                            return "😄 指令执行成功， 执行结果：\n " + mjon
                        else:
                            return (
                                "😄 指令执行成功， 执行结果：\n"
                                + result.OutputMessages[0].Message
                            )
                    else:
                        if translate is not None:
                            return "😭 指令执行失败， 原因：\n" + mjon
                        else:
                            return (
                                "😭 指令执行失败， 原因：\n"
                                + result.OutputMessages[0].Message
                            )
            except IndexError as exec_err:
                import traceback

                traceback.print_exc()
                return f"执行出现问题: {exec_err}"
            except TimeoutError:
                return "😭超时： 指令获取结果返回超时"

        def send_player_list():
            players = [f"{i + 1}.{j}" for i, j in enumerate(self.game_ctrl.allplayers)]
            fmt_msg = (
                f"在线玩家有 {len(players)} 人：\n "
                + "\n ".join(players)
                + (
                    f"\n当前 TPS： {round(self.tps_calc.get_tps(), 1)}/20"
                    if self.tps_calc
                    else ""
                )
            )
            self.sendmsg(self.linked_group, fmt_msg)

        def lookup_help(sender: int, _):
            output_msg = f"[CQ:at,qq={sender}] 群服互通帮助菜单："
            for trigger in self.triggers:
                output_msg += (
                    f"  \n{trigger.triggers[0]}"
                    f"{' ' + trigger.argument_hint if trigger.argument_hint else ''} "
                    f"： {trigger.usage}"
                )
                if trigger.op_only:
                    output_msg += " （仅管理员可用）"
            self.sendmsg(self.linked_group, output_msg)

        self.frame.add_console_cmd_trigger(
            ["QQ", "发群"], "[消息]", "在群内发消息测试", self.on_sendmsg_test
        )
        self.add_trigger(
            ["/"], "[指令]", "向租赁服发送指令", sb_execute_cmd, op_only=True
        )
        self.add_trigger(["help", "帮助"], None, "查看群服互通帮助", lookup_help)
        if self.enable_playerlist:
            self.add_trigger(
                ["list", "玩家列表"],
                None,
                "查看玩家列表",
                lambda _, _2: send_player_list(),
            )

    @utils.thread_func("云链群服连接进程")
    def connect_to_websocket(self):
        header = None
        if self.cfg["云链设置"]["校验码"] is not None:
            header = {"Authorization": f"Bearer {self.cfg['云链设置']['校验码']}"}
        self.ws = websocket.WebSocketApp(  # type: ignore
            self.cfg["云链设置"]["地址"],
            header,
            on_message=lambda a, b: self.on_ws_message(a, b) and None,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
        )
        self.ws.on_open = self.on_ws_open
        self.ws.run_forever()

    @utils.thread_func("云链群服消息广播进程")
    def broadcast(self, data):
        for i in self.plugin:
            self.GetPluginAPI(i).QQLinker_message(data)

    def on_ws_open(self, ws):
        fmts.print_suc("已成功连接到群服互通")

    @utils.thread_func("群服互通消息接收线程")
    def on_ws_message(self, ws, message):
        data = json.loads(message)
        bc_recv = self.BroadcastEvent(InternalBroadcast("群服互通/数据json", data))
        if any(bc_recv):
            return
        if data.get("post_type") == "message" and data["message_type"] == "group":
            self.broadcast(data)
            if data["group_id"] != self.linked_group:
                return
            msg = data["message"]
            if isinstance(msg, list):
                # NapCat
                msg_rawdict = msg[0]
                msg_type = msg_rawdict["type"]
                msg_data = msg_rawdict["data"]
                if msg_type != "text":
                    return
                msg = msg_data["text"]
            elif not isinstance(msg, str):
                raise ValueError(f"键 'message' 值不是字符串类型, 而是 {msg}")
            if self.enable_group_2_game:
                user_id = data["sender"]["user_id"]
                nickname = data["sender"]["card"] or data["sender"]["nickname"]
                if user_id in self.waitmsg_cbs.keys():
                    self.waitmsg_cbs[user_id](
                        msg,
                    )
                    return
                bc_recv = self.BroadcastEvent(
                    InternalBroadcast(
                        "群服互通/链接群消息",
                        {"QQ号": user_id, "昵称": nickname, "消息": msg},
                    ),
                )
                if any(bc_recv):
                    return
                elif self.execute_triggers(user_id, msg):
                    return
                self.game_ctrl.say_to(
                    "@a",
                    utils.simple_fmt(
                        {
                            "[昵称]": nickname,
                            "[消息]": replace_cq(msg),
                        },
                        self.cfg["消息转发设置"]["群到游戏"]["转发格式"],
                    ),
                )

    def on_ws_error(self, ws, error):
        if not isinstance(error, Exception):
            fmts.print_inf(f"群服互通发生错误: {error}, 可能为系统退出, 已关闭")
            self.reloaded = True
            return
        fmts.print_err(f"群服互通发生错误: {error}, 15s后尝试重连")
        time.sleep(15)

    def waitMsg(self, qqid: int, timeout=60) -> str | None:
        g, s = create_result_cb()
        self.waitmsg_cbs[qqid] = s
        r = g(timeout)
        del self.waitmsg_cbs[qqid]
        return r

    def on_ws_close(self, ws, _, _2):
        if self.reloaded:
            return
        fmts.print_err("群服互通被关闭, 10s后尝试重连")
        time.sleep(10)
        self.connect_to_websocket()

    def on_player_join(self, playerf: Player):
        player = playerf.name
        if self.ws and self.enable_game_2_group:
            self.sendmsg(self.linked_group, f"{player} 加入了游戏")

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        if self.ws and self.enable_game_2_group:
            self.sendmsg(self.linked_group, f"{player} 退出了游戏")

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg

        if self.ws and self.enable_game_2_group:
            if self.game2qq_trans_chars != []:
                can_send = False
                for prefix in self.game2qq_trans_chars:
                    if msg.startswith(prefix):
                        can_send = True
                        msg = msg[len(prefix) :]
                        break
            elif self.game2qq_block_prefixs != []:
                can_send = True
                for prefix in self.game2qq_block_prefixs:
                    if msg.startswith(prefix):
                        can_send = False
                        break
            else:
                can_send = True
            if not can_send:
                return
            self.sendmsg(
                self.linked_group,
                utils.simple_fmt(
                    {"[玩家名]": player, "[消息]": remove_cq_code(msg)},
                    self.cfg["消息转发设置"]["游戏到群"]["转发格式"],
                ),
            )

    def execute_triggers(self, qqid: int, msg: str):
        for trigger in self.triggers:
            if t := trigger.match(msg):
                if self.is_qq_op(qqid) or not trigger.op_only:
                    args = msg.removeprefix(t).strip().split()
                    if trigger.args_pd(len(args)):
                        trigger.func(qqid, args)
                    else:
                        self.sendmsg(
                            self.linked_group,
                            f"[CQ:at,qq={qqid}] 参数错误，格式：{t}"
                            f"{' ' + trigger.argument_hint if trigger.argument_hint else ''}",
                            do_remove_cq_code=False,
                        )
                else:
                    if easter_egg := EASTER_EGG_QQIDS.get(qqid):
                        name, nickname = easter_egg
                        self.sendmsg(
                            self.linked_group,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令，即使你是 {nickname}..",
                            do_remove_cq_code=False,
                        )
                    else:
                        self.sendmsg(
                            self.linked_group,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                            do_remove_cq_code=False,
                        )
                return True
        return False

    def on_sendmsg_test(self, args: list[str]):
        if self.ws:
            self.sendmsg(self.linked_group, " ".join(args))
        else:
            fmts.print_err("还没有连接到群服互通")

    def sendmsg(self, group: int, msg: str, do_remove_cq_code=True):
        assert self.ws
        if do_remove_cq_code:
            msg = remove_cq_code(msg)
        jsondat = json.dumps(
            {
                "action": "send_group_msg",
                "params": {"group_id": group, "message": msg},
            }
        )
        self.ws.send(jsondat)


entry = plugin_entry(QQLinker, "群服互通")
