import json
import time
from typing import Any

try:
    import websocket
except ImportError:
    from . import websocket

from tooldelta import Chat, InternalBroadcast, Player, fmts, utils

from .message_utils import (
    EASTER_EGG_QQIDS,
    remove_color,
    remove_cq_code,
    replace_cq,
)

try:
    from tooldelta.utils.mc_translator import translate
except ImportError:
    translate = None


# 运行时层只管消息流转：执行指令、WebSocket、广播、群服互通分发。
class QQLinkerRuntimeMixin:
    def execute_cmd_and_get_zhcn_cb(self, cmd: str):
        """执行 MC 指令，并把原始返回整理成适合群聊展示的文本。"""

        try:
            result = self.game_ctrl.sendwscmd_with_resp(cmd, 10)
            if len(result.OutputMessages) == 0:
                return ["😅 指令执行失败", "😄 指令执行成功"][bool(result.SuccessCount)]
            if result.OutputMessages[0].Message in (
                "commands.generic.syntax",
                "commands.generic.unknown",
            ):
                return f'😅 未知的 MC 指令, 可能是指令格式有误: "{cmd}"'
            if translate is not None:
                output_text = "\n".join(
                    translate(i.Message, i.Parameters) for i in result.OutputMessages
                )
            else:
                output_text = "\n".join(i.Message for i in result.OutputMessages)
            if result.SuccessCount:
                return "😄 指令执行成功，执行结果：\n" + output_text
            return "😭 指令执行失败，原因：\n" + output_text
        except IndexError as exec_err:
            import traceback

            traceback.print_exc()
            return f"执行出现问题: {exec_err}"
        except TimeoutError:
            return "😭 超时：指令获取结果返回超时"

    def iter_game_to_group_targets(self):
        """遍历当前启用了“游戏到群”转发的群。"""

        for group_id in self.group_order:
            group_cfg = self.group_cfgs[group_id]
            if group_cfg["游戏到群"]["是否启用"]:
                yield group_id, group_cfg

    @staticmethod
    def should_forward_game_message(msg: str, group_cfg: dict[str, Any]):
        """根据群配置判断一条游戏消息是否要转发，以及转发时应裁掉哪些前缀。"""

        trans_chars = group_cfg["游戏到群"]["仅转发以下符号开头的消息(列表为空则全部转发)"]
        block_prefixs = group_cfg["游戏到群"]["屏蔽以下字符串开头的消息"]
        if trans_chars:
            for prefix in trans_chars:
                if msg.startswith(prefix):
                    return True, msg[len(prefix) :]
            return False, msg
        if block_prefixs:
            for prefix in block_prefixs:
                if msg.startswith(prefix):
                    return False, msg
        return True, msg

    @utils.thread_func("云链群服连接进程")
    def connect_to_websocket(self):
        header = None
        validate_code = self.cfg["云链设置"]["校验码"].strip()
        if validate_code:
            header = {"Authorization": f"Bearer {validate_code}"}
        # 手动拉起本地桥时优先走本地端口，否则直接连接配置里的云链地址。
        self.ws = websocket.WebSocketApp(
            (
                f"ws://127.0.0.1:{self._manual_launch_port}"
                if self._manual_launch
                else self.cfg["云链设置"]["地址"]
            ),
            header,
            on_message=lambda a, b: self.on_ws_message(a, b) and None,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
        )
        self.ws.on_open = self.on_ws_open
        self.ws.run_forever()

    @utils.thread_func("云链群服消息广播进程")
    def broadcast(self, data):
        """把原始群消息广播给主动注册的其他插件。"""

        for plugin_name in self.plugin:
            self.GetPluginAPI(plugin_name).QQLinker_message(data)

    def on_ws_open(self, _ws):
        self.available = True
        self.print("§a已成功连接到群服互通云链版Ultra版 =============")

    @utils.thread_func("群服互通消息接收线程")
    def on_ws_message(self, _ws, message):
        data = json.loads(message)
        bc_recv = self.BroadcastEvent(InternalBroadcast("群服互通/数据json", data))
        if any(bc_recv):
            return
        if data.get("post_type") != "message" or data.get("message_type") != "group":
            return

        self.broadcast(data)

        # 先按群号过滤，再决定是走插件广播、命令分发，还是普通转发到游戏内。
        group_id = data.get("group_id")
        if group_id not in self.group_cfgs:
            return
        group_cfg = self.group_cfgs[group_id]

        msg = data["message"]
        if isinstance(msg, list):
            msg_rawdict = msg[0]
            msg_type = msg_rawdict["type"]
            msg_data = msg_rawdict["data"]
            if msg_type != "text":
                return
            msg = msg_data["text"]
        elif not isinstance(msg, str):
            raise ValueError(f"键 'message' 值不是字符串类型, 而是 {msg}")

        user_id = int(data["sender"]["user_id"])
        nickname = data["sender"]["card"] or data["sender"]["nickname"]

        wait_key = (group_id, user_id)
        if wait_key in self.waitmsg_cbs:
            self.waitmsg_cbs[wait_key](msg)
            return
        if user_id in self.waitmsg_cbs:
            self.waitmsg_cbs[user_id](msg)
            return

        bc_recv = self.BroadcastEvent(
            InternalBroadcast(
                "群服互通/链接群消息",
                {"群号": group_id, "QQ号": user_id, "昵称": nickname, "消息": msg},
            ),
        )
        if any(bc_recv):
            return

        if self.execute_triggers(group_id, user_id, msg):
            return

        if not group_cfg["群到游戏"]["是否启用"]:
            return
        if user_id in group_cfg["群到游戏"]["屏蔽的QQ号"]:
            return

        if group_cfg["群到游戏"]["替换花里胡哨的昵称"]:
            nickname = remove_color(nickname)
        if group_cfg["群到游戏"]["替换花里胡哨的消息"]:
            msg = remove_color(msg)
        self.game_ctrl.say_to(
            "@a",
            utils.simple_fmt(
                {"[昵称]": nickname, "[消息]": replace_cq(msg)},
                group_cfg["群到游戏"]["转发格式"],
            ),
        )

    def on_ws_error(self, _ws, error):
        if not isinstance(error, Exception):
            fmts.print_inf(f"群服互通云链版Ultra版发生错误: {error}, 可能为系统退出, 已关闭")
            self.reloaded = True
            return
        self.available = False
        fmts.print_err(f"群服互通云链版Ultra版发生错误: {error}, 15s后尝试重连")
        time.sleep(15)

    def waitMsg(self, qqid: int, timeout=60, group_id: int | None = None) -> str | None:
        """等待某个 QQ 在指定群里的下一条回复。

        带 `group_id` 时只收同群回复，不带时保留对旧插件的兼容行为。
        """

        getter, setter = utils.create_result_cb(str)
        key: int | tuple[int, int] = qqid if group_id is None else (group_id, qqid)
        self.waitmsg_cbs[key] = setter
        result = getter(timeout)
        if key in self.waitmsg_cbs:
            del self.waitmsg_cbs[key]
        return result

    def on_ws_close(self, _ws, _, _2):
        self.available = False
        if self.reloaded:
            return
        fmts.print_err("群服互通云链版Ultra版被关闭, 10s后尝试重连")
        time.sleep(10)
        self.connect_to_websocket()

    def on_player_join(self, playerf: Player):
        player = playerf.name
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 加入了游戏")

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 退出了游戏")

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            can_send, filtered_msg = self.should_forward_game_message(msg, group_cfg)
            if not can_send:
                continue
            self.sendmsg(
                group_id,
                utils.simple_fmt(
                    {"[玩家名]": player, "[消息]": remove_cq_code(filtered_msg)},
                    group_cfg["游戏到群"]["转发格式"],
                ),
            )

    def execute_triggers(self, group_id: int, qqid: int, msg: str):
        """对一条群消息做内置命令和外挂命令的统一分发。"""

        clean_msg = msg.strip()
        # 内置功能优先匹配，最后才轮到其他插件注册进来的自定义触发词。
        if clean_msg in self.get_group_help_triggers(group_id):
            self.on_qq_help(group_id, qqid, [])
            return True
        if clean_msg in self.get_group_admin_menu_triggers(group_id):
            self.qq_admin_menu(group_id, qqid)
            return True
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        if clean_msg.startswith(cmd_prefix):
            args = clean_msg.removeprefix(cmd_prefix).strip().split()
            if not self.is_group_admin(group_id, qqid):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 你没有权限执行此指令", do_remove_cq_code=False)
                return True
            if len(args) == 0:
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 参数错误，格式：{cmd_prefix}[指令]", do_remove_cq_code=False)
                return True
            self.on_qq_execute_cmd(group_id, qqid, args)
            return True
        if clean_msg in self.get_group_player_list_triggers(group_id):
            self.on_qq_player_list(group_id, qqid, [])
            return True
        if clean_msg in self.get_group_inventory_menu_triggers(group_id):
            if not self.is_group_admin(group_id, qqid):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 你没有权限执行此指令", do_remove_cq_code=False)
                return True
            self.qq_inventory_menu(group_id, qqid)
            return True
        if clean_msg in self.get_group_checker_menu_triggers(group_id):
            if not self.is_group_admin(group_id, qqid):
                self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 你没有权限执行此指令", do_remove_cq_code=False)
                return True
            self.qq_checker_menu(group_id, qqid)
            return True
        for trigger in self.get_group_orion_ban_triggers(group_id):
            if clean_msg.startswith(trigger):
                args = clean_msg.removeprefix(trigger).strip().split()
                if not self.is_group_admin(group_id, qqid):
                    self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 你没有权限执行此指令", do_remove_cq_code=False)
                    return True
                if not (len(args) == 0 or len(args) >= 2):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 参数错误，格式：{trigger} [玩家名/xuid] [封禁时间] [原因可选]",
                        do_remove_cq_code=False,
                    )
                    return True
                self.on_qq_orion_ban(group_id, qqid, args)
                return True
        for trigger in self.get_group_orion_unban_triggers(group_id):
            if clean_msg.startswith(trigger):
                args = clean_msg.removeprefix(trigger).strip().split()
                if not self.is_group_admin(group_id, qqid):
                    self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 你没有权限执行此指令", do_remove_cq_code=False)
                    return True
                if len(args) not in (0, 1):
                    self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 参数错误，格式：{trigger} [玩家名/xuid]", do_remove_cq_code=False)
                    return True
                self.on_qq_orion_unban(group_id, qqid, args)
                return True
        for trigger in self.triggers:
            if t := trigger.match(msg):
                if trigger.op_only and not self.is_group_admin(group_id, qqid):
                    if easter_egg := EASTER_EGG_QQIDS.get(qqid):
                        _name, nickname = easter_egg
                        self.sendmsg(
                            group_id,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令，即使你是 {nickname}..",
                            do_remove_cq_code=False,
                        )
                    else:
                        self.sendmsg(group_id, f"[CQ:at,qq={qqid}] 你没有权限执行此指令", do_remove_cq_code=False)
                    return True

                args = msg.removeprefix(t).strip().split()
                if not trigger.args_pd(len(args)):
                    self.sendmsg(
                        group_id,
                        f"[CQ:at,qq={qqid}] 参数错误，格式：{t}{' ' + trigger.argument_hint if trigger.argument_hint else ''}",
                        do_remove_cq_code=False,
                    )
                    return True
                if trigger.accept_group:
                    trigger.func(group_id, qqid, args)
                else:
                    trigger.func(qqid, args)
                return True
        return False

    def on_sendmsg_test(self, args: list[str]):
        if not self.ws:
            fmts.print_err("还没有连接到群服互通云链版Ultra版")
            return
        if not args:
            fmts.print_err("请输入要发送的消息")
            return
        target_group = None
        if len(args) >= 2:
            maybe_gid = utils.try_int(args[0])
            if maybe_gid in self.group_cfgs:
                target_group = maybe_gid
                args = args[1:]
        if target_group is not None:
            self.sendmsg(target_group, " ".join(args))
            return
        for group_id in self.group_order:
            self.sendmsg(group_id, " ".join(args))

    def sendmsg(self, group: int, msg: str, do_remove_cq_code=True):
        """向目标群发消息。

        这里顺手处理了两件事：
        - 在还没连上云链时直接忽略发送，避免抛异常
        - at 消息后面补换行，让群里显示更自然
        """

        if self.ws is None:
            raise RuntimeError("WebSocket 尚未初始化")
        if not self.available:
            self.print(f"§6未连接, 忽略发送至 {group} 的消息 {msg}")
            return
        if msg.startswith("[CQ:at,qq="):
            cq_end = msg.find("]")
            if cq_end != -1:
                head = msg[: cq_end + 1]
                tail = msg[cq_end + 1 :].lstrip()
                msg = head if tail == "" else head + "\n" + tail
        if do_remove_cq_code:
            msg = remove_cq_code(msg)
        self.ws.send(
            json.dumps(
                {"action": "send_group_msg", "params": {"group_id": group, "message": msg}}
            )
        )
