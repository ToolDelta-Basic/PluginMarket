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
    """负责云链运行时、消息分发与 WebSocket 生命周期。"""

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
        """按当前配置或本地桥接参数建立到云链的连接。"""
        header = None
        validate_code = self.cfg["云链设置"]["校验码"].strip()
        if validate_code:
            header = {"Authorization": f"Bearer {validate_code}"}
        self.ws = websocket.WebSocketApp(
            self._get_websocket_target(),
            header,
            on_message=lambda a, b: self.on_ws_message(a, b) and None,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
        )
        self.ws.on_open = self.on_ws_open
        self.ws.run_forever()

    def _get_websocket_target(self):
        """返回当前应连接的 WebSocket 地址。"""
        if self._manual_launch:
            return f"ws://127.0.0.1:{self._manual_launch_port}"
        return self.cfg["云链设置"]["地址"]

    @utils.thread_func("云链群服消息广播进程")
    def broadcast(self, data):
        """把原始群消息广播给主动注册的其他插件。"""
        for plugin_name in self.plugin:
            self.GetPluginAPI(plugin_name).QQLinker_message(data)

    def on_ws_open(self, _ws):
        """在 WebSocket 建立后标记连接可用。"""
        self.available = True
        self.print("§a已成功连接到群服互通云链版Ultra版 =============")

    @utils.thread_func("群服互通消息接收线程")
    def on_ws_message(self, _ws, message):
        """处理来自云链的群消息，并按配置分发到不同入口。"""
        data = json.loads(message)
        if self._stop_when_data_broadcast_handled(data):
            return

        payload = self._build_group_message_payload(data)
        if payload is None:
            return

        group_id, group_cfg, msg, user_id, nickname = payload
        if self._consume_waiting_reply(group_id, user_id, msg):
            return
        if self._stop_when_group_broadcast_handled(group_id, user_id, nickname, msg):
            return
        if self.execute_triggers(group_id, user_id, msg):
            return
        self._forward_group_message_to_game(group_cfg, user_id, nickname, msg)

    def _stop_when_data_broadcast_handled(self, data: dict[str, Any]) -> bool:
        """把原始数据广播给框架，其它插件声明已处理时立即停止后续流程。"""
        bc_recv = self.BroadcastEvent(InternalBroadcast("群服互通/数据json", data))
        if any(bc_recv):
            return True
        if data.get("post_type") != "message" or data.get("message_type") != "group":
            return True
        self.broadcast(data)
        return False

    def _build_group_message_payload(self, data: dict[str, Any]):
        """把云链原始消息整理成后续逻辑统一使用的结构。"""
        group_id = data.get("group_id")
        if group_id not in self.group_cfgs:
            return None
        group_cfg = self.group_cfgs[group_id]
        msg = self._extract_text_message(data["message"])
        user_id = int(data["sender"]["user_id"])
        nickname = data["sender"]["card"] or data["sender"]["nickname"]
        return group_id, group_cfg, msg, user_id, nickname

    @staticmethod
    def _extract_text_message(msg: Any) -> str:
        """从云链消息结构里提取可处理的纯文本。"""
        if isinstance(msg, list):
            msg_rawdict = msg[0]
            msg_type = msg_rawdict["type"]
            msg_data = msg_rawdict["data"]
            if msg_type != "text":
                return ""
            return msg_data["text"]
        if not isinstance(msg, str):
            raise ValueError(f"键 'message' 值不是字符串类型, 而是 {msg}")
        return msg

    def _consume_waiting_reply(self, group_id: int, user_id: int, msg: str) -> bool:
        """把当前消息投递给等待输入的菜单回调。"""
        wait_key = (group_id, user_id)
        if wait_key in self.waitmsg_cbs:
            self.waitmsg_cbs[wait_key](msg)
            return True
        if user_id in self.waitmsg_cbs:
            self.waitmsg_cbs[user_id](msg)
            return True
        return False

    def _stop_when_group_broadcast_handled(
        self,
        group_id: int,
        user_id: int,
        nickname: str,
        msg: str,
    ) -> bool:
        """把群消息广播给框架层，其它插件声明已处理时立即停止。"""
        bc_recv = self.BroadcastEvent(
            InternalBroadcast(
                "群服互通/链接群消息",
                {"群号": group_id, "QQ号": user_id, "昵称": nickname, "消息": msg},
            ),
        )
        return any(bc_recv)

    def _forward_group_message_to_game(
        self,
        group_cfg: dict[str, Any],
        user_id: int,
        nickname: str,
        msg: str,
    ):
        """把普通群消息按当前群配置转发到游戏内。"""
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
        """处理 WebSocket 错误并按配置尝试重连。"""
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
        """连接关闭时按当前状态决定是否自动重连。"""
        self.available = False
        if self.reloaded:
            return
        fmts.print_err("群服互通云链版Ultra版被关闭, 10s后尝试重连")
        time.sleep(10)
        self.connect_to_websocket()

    def on_player_join(self, playerf: Player):
        """把玩家加入事件转发到所有启用了游戏到群的群。"""
        player = playerf.name
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 加入了游戏")

    def on_player_leave(self, playerf: Player):
        """把玩家离开事件转发到所有启用了游戏到群的群。"""
        player = playerf.name
        if not self.ws:
            return
        for group_id, group_cfg in self.iter_game_to_group_targets():
            if group_cfg["游戏到群"]["转发玩家进退提示"]:
                self.sendmsg(group_id, f"{player} 退出了游戏")

    def on_player_message(self, chat: Chat):
        """按各群配置把游戏聊天消息转发到对应群聊。"""
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
        if self._handle_exact_trigger(group_id, qqid, clean_msg):
            return True
        if self._handle_prefixed_command(group_id, qqid, clean_msg):
            return True
        if self._handle_group_orion_triggers(group_id, qqid, clean_msg):
            return True
        return self._handle_external_trigger(group_id, qqid, msg)

    def _reply_to_qq(self, group_id: int, qqid: int, text: str):
        """向指定 QQ 回复一条消息。"""
        self.sendmsg(
            group_id,
            f"[CQ:at,qq={qqid}] {text}",
            do_remove_cq_code=False,
        )

    def _handle_exact_trigger(self, group_id: int, qqid: int, clean_msg: str) -> bool:
        """处理帮助、管理员菜单、背包查询等完全匹配型触发词。"""
        if clean_msg in self.get_group_help_triggers(group_id):
            self.on_qq_help(group_id, qqid, [])
            return True
        if clean_msg in self.get_group_admin_menu_triggers(group_id):
            self.qq_admin_menu(group_id, qqid)
            return True
        if clean_msg in self.get_group_player_list_triggers(group_id):
            self.on_qq_player_list(group_id, qqid, [])
            return True
        if clean_msg in self.get_group_inventory_menu_triggers(group_id):
            return self._run_admin_only_action(
                group_id,
                qqid,
                lambda: self.qq_inventory_menu(group_id, qqid),
            )
        if clean_msg in self.get_group_checker_menu_triggers(group_id):
            return self._run_admin_only_action(
                group_id,
                qqid,
                lambda: self.qq_checker_menu(group_id, qqid),
            )
        return False

    def _handle_prefixed_command(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理带统一前缀的群内执行指令入口。"""
        cmd_prefix = self.get_group_cmd_prefix(group_id)
        if not clean_msg.startswith(cmd_prefix):
            return False

        args = clean_msg.removeprefix(cmd_prefix).strip().split()
        if not self.is_group_admin(group_id, qqid):
            self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")
            return True
        if len(args) == 0:
            self._reply_to_qq(group_id, qqid, f"参数错误，格式：{cmd_prefix}[指令]")
            return True

        self.on_qq_execute_cmd(group_id, qqid, args)
        return True

    def _handle_group_orion_triggers(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
    ) -> bool:
        """处理 Orion 封禁/解封相关的前缀命令。"""
        if self._handle_orion_trigger(
            group_id,
            qqid,
            clean_msg,
            self.get_group_orion_ban_triggers(group_id),
            self.on_qq_orion_ban,
            "[玩家名/xuid] [封禁时间] [原因可选]",
            lambda args: len(args) == 0 or len(args) >= 2,
        ):
            return True
        return self._handle_orion_trigger(
            group_id,
            qqid,
            clean_msg,
            self.get_group_orion_unban_triggers(group_id),
            self.on_qq_orion_unban,
            "[玩家名/xuid]",
            lambda args: len(args) in (0, 1),
        )

    def _handle_orion_trigger(
        self,
        group_id: int,
        qqid: int,
        clean_msg: str,
        triggers: list[str],
        handler,
        args_hint: str,
        args_validator,
    ) -> bool:
        """处理一组 Orion 触发词。"""
        for trigger in triggers:
            if not clean_msg.startswith(trigger):
                continue
            args = clean_msg.removeprefix(trigger).strip().split()
            if not self.is_group_admin(group_id, qqid):
                self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")
                return True
            if not args_validator(args):
                self._reply_to_qq(group_id, qqid, f"参数错误，格式：{trigger} {args_hint}")
                return True
            handler(group_id, qqid, args)
            return True
        return False

    def _handle_external_trigger(self, group_id: int, qqid: int, msg: str) -> bool:
        """处理外部插件注册进来的自定义触发词。"""
        for trigger in self.triggers:
            matched = trigger.match(msg)
            if not matched:
                continue

            if trigger.op_only and not self.is_group_admin(group_id, qqid):
                self._reply_permission_denied(group_id, qqid)
                return True

            args = msg.removeprefix(matched).strip().split()
            if not trigger.args_pd(len(args)):
                self._reply_trigger_arg_error(
                    group_id,
                    qqid,
                    matched,
                    trigger.argument_hint,
                )
                return True

            if trigger.accept_group:
                trigger.func(group_id, qqid, args)
            else:
                trigger.func(qqid, args)
            return True
        return False

    def _reply_permission_denied(self, group_id: int, qqid: int):
        """统一处理没有管理权限时的回复。"""
        if easter_egg := EASTER_EGG_QQIDS.get(qqid):
            _name, nickname = easter_egg
            self._reply_to_qq(group_id, qqid, f"你没有权限执行此指令，即使你是 {nickname}..")
            return
        self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")

    def _reply_trigger_arg_error(
        self,
        group_id: int,
        qqid: int,
        trigger: str,
        argument_hint: str | None,
    ):
        """统一处理外部触发器参数不足时的回复。"""
        suffix = f" {argument_hint}" if argument_hint else ""
        self._reply_to_qq(group_id, qqid, f"参数错误，格式：{trigger}{suffix}")

    def _run_admin_only_action(self, group_id: int, qqid: int, action) -> bool:
        """执行仅群管理员可用的动作。"""
        if not self.is_group_admin(group_id, qqid):
            self._reply_to_qq(group_id, qqid, "你没有权限执行此指令")
            return True
        action()
        return True

    def on_sendmsg_test(self, args: list[str]):
        """供控制台快速验证群消息发送链路是否正常。"""
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
        payload = {
            "action": "send_group_msg",
            "params": {"group_id": group, "message": msg},
        }
        self.ws.send(json.dumps(payload))
