from tooldelta import Plugin, Player, cfg as config, utils, Chat, plugin_entry
from typing import Any
from dataclasses import dataclass
from collections.abc import Callable

VALID_ARGUMENT_HINT_TYPES = type[str | int | bool | float] | tuple[str]
VALID_ARG_VALUE = str | int | float | None
VALID_ARG_WITHOUT_NONE = str | int | float
ARGUMENT_HINT = list[tuple[str, VALID_ARGUMENT_HINT_TYPES, VALID_ARG_VALUE]]

def isNaN(x: float):
    return x != x

def isInfinity(x: float):
    return x == float("inf") or x == float("-inf")

def isInvalidFloat(x: float):
    return isNaN(x) or isInfinity(x)


def parse_arg(
    arg: str, argtype: type[str | int | bool | float]
) -> VALID_ARG_WITHOUT_NONE:
    if argtype is str:
        return arg
    elif argtype is int:
        val = utils.try_convert(arg, int)
        if val is None:
            raise ValueError(f"{arg} 不是一个整数")
        return val
    elif argtype is float:
        val = utils.try_convert(arg, float)
        if val is None:
            raise ValueError(f"{arg} 不是一个整数或小数")
        elif isInvalidFloat(val):
            raise ValueError(f"{arg} 不合法")
        return val
    elif argtype is bool:
        if arg == "true":
            return True
        elif arg == "false":
            return False
        else:
            raise ValueError(f"{arg} 不是 true 或 false")
    else:
        raise TypeError(f"无法解析参数类型 {argtype.__name__}")


def type_str(argtype: type[str | int | bool | float]):
    if argtype is str:
        return "字符串"
    elif argtype is int:
        return "整数"
    elif argtype is float:
        return "数值"
    elif argtype is bool:
        return "[true|false]"


@dataclass
class OldChatbarTriggers:
    triggers: list[str]
    argument_hint: str | None
    usage: str
    func: Callable[[str, list[str]], Any]
    args_pd: Callable
    op_only: bool


class StandardChatbarTriggers:
    def __init__(
        self,
        triggers: list[str],
        argument_hints: ARGUMENT_HINT,
        usage: str,
        func: Callable[[Player, tuple], None],
        op_only: bool,
        cfg: dict,
    ):
        self.triggers = triggers
        self.argument_hints = argument_hints
        self.usage = usage
        self.func = func
        self.op_only = op_only
        self.cfg = cfg
        self._check_argument_hint()

    def execute(self, player: Player, args: list[str]):
        args_parsed, err = self._parse_args(args)
        if err is not None:
            player.show(f"§c{err}")
            return
        self.func(player, args_parsed)

    @property
    def argument_hints_str(self) -> str:
        outputs = []
        for hint, atype, default in self.argument_hints:
            if default is not None:
                outputs.append(
                    utils.simple_fmt(
                        {
                            "[提示词]": hint,
                            "[默认值]": default,
                        },
                        self.cfg["help菜单样式"]["参数提示配置"]["参数提示格式"],
                    )
                )
            else:
                outputs.append(
                    utils.simple_fmt(
                        {
                            "[提示词]": hint,
                            "[默认值]": "".join(atype)
                            if isinstance(atype, tuple)
                            else type_str(atype),
                        },
                        self.cfg["help菜单样式"]["参数提示配置"]["参数提示格式"],
                    )
                )
        return " ".join(outputs)

    def _parse_args(self, args: list[str]) -> tuple[tuple, Exception | None]:
        if len(args) > len(self.argument_hints):
            return (), ValueError(
                f"参数个数错误， 最多 {len(self.argument_hints)} 个参数"
            )
        elif len(args) < self.no_default_args_num:
            return (), ValueError(
                f"参数个数错误， 至少需要 {self.no_default_args_num} 个参数"
            )
        args_parsed: list[VALID_ARG_WITHOUT_NONE] = []
        for i, arg_str in enumerate(args):
            hint, argtype, _ = self.argument_hints[i]
            if isinstance(argtype, tuple):
                if arg_str not in argtype:
                    return (), ValueError(f"{hint} 的值只能为 {'、 '.join(argtype)}")
                else:
                    args_parsed.append(arg_str)
            else:
                try:
                    args_parsed.append(parse_arg(arg_str, argtype))
                except ValueError as e:
                    return (), e
        default_args = [
            default for _, _2, default in self.argument_hints if default is not None
        ]
        utils.fill_list_index(args_parsed, default_args)
        return tuple(args_parsed), None

    def _check_argument_hint(self):
        default_arg = False
        self.no_default_args_num = 0
        for i, hint in enumerate(self.argument_hints):
            if len(hint) != 3:
                raise ValueError(
                    f"添加触发词: argument_hint: 第 {i + 1} 项的元组长度应为 3, 如果其没有默认值, 第三项应为 None"
                )
            if hint[2] is None:
                if default_arg:
                    raise ValueError(
                        f"添加触发词: argument_hint: 第 {i + 1} 项没有默认值的参数之前存在默认参数"
                    )
                self.no_default_args_num += 1
            else:
                arg_type_or_tuple, default_value = hint[1:]
                if isinstance(arg_type_or_tuple, type):
                    if not isinstance(default_value, arg_type_or_tuple):
                        raise ValueError(
                            f"添加触发词: argument_hint: 第 {i + 1} 项的默认值和其类型不匹配"
                        )
                else:
                    if len(arg_type_or_tuple) < 1:
                        raise ValueError("组参数类型必须有一个以上的组成员")
                    if default_value not in arg_type_or_tuple:
                        raise ValueError(
                            f"添加触发词: argument_hint: 第 {i + 1} 项的默认值不被包含在要求的值内"
                        )
                default_arg = True


class ChatbarMenu(Plugin):
    name = "聊天栏菜单新版"
    author = "SuperScript/猫猫"
    version = (0, 3, 3)
    description = "前置插件, 提供聊天栏菜单功能"

    def __init__(self, frame):
        super().__init__(frame)
        self.chatbar_triggers: list[OldChatbarTriggers | StandardChatbarTriggers] = []
        DEFAULT_CFG = {
            "help菜单样式": {
                "菜单头": "§r========== §bＴｏｏｌＤｅｌｔａ§r ==========\n§r§d§l❒ §r§d权限: [是否为管理员] [是否为创造] [是否为成员]",
                "菜单列表": " §f< [菜单指令]§f > [参数提示] §7>>> §f§o[菜单功能说明]§r§7",
                "菜单尾": "§r§f============§7[§a[当前页数] §7/ §a[总页数]§7]§f=============\n§r>>> §7输入 .help <页数> 可以跳转到该页",
                "管理选项": {
                    "格式化": "[是否为管理员]",
                    "为管理员": "§r[§a管理选项§l✔§r]",
                    "不为管理员": "§r[§c管理选项§l✘§r]",
                },
                "创造选项": {
                    "格式化": "[是否为创造]",
                    "为创造": "§r[§a创造选项§l✔§r]",
                    "不为创造": "§r[§c创造选项§l✘§r]",
                },
                "成员选项": {
                    "格式化": "[是否为成员]",
                    "为成员": "§r[§a成员选项§l✔§r]",
                    "不为成员": "§r[§c成员选项§l✘§r]",
                },
                "菜单指令配置": {
                    "指令分隔符": " §r§7| ",
                    "指令配色": {
                        "管理": "§a",
                        "成员": "§a",
                    },
                },
                "参数提示配置": {
                    "参数间隔符": " ",
                    "参数提示格式": "[§6[提示词]§r]",
                },
            },
            "/help触发词": ["help"],
            "被识别为触发词的前缀(不填则为无命令前缀)": [".", "。", "·"],
            "单页内最多显示数": 6,
        }
        STD_CFG_TYPE = {
            "help菜单样式": {
                "菜单头": str,
                "菜单列表": str,
                "菜单尾": str,
                "管理选项": {
                    "格式化": str,
                    "为管理员": str,
                    "不为管理员": str,
                },
                "创造选项": {
                    "格式化": str,
                    "为创造": str,
                    "不为创造": str,
                },
                "成员选项": {
                    "格式化": str,
                    "为成员": str,
                    "不为成员": str,
                },
                "菜单指令配置": {
                    "指令分隔符": str,
                    "指令配色": {
                        "管理": str,
                        "成员": str,
                    },
                },
                "参数提示配置": {
                    "参数间隔符": str,
                    "参数提示格式": str,
                },
            },
            "/help触发词": config.JsonList(str),
            "单页内最多显示数": config.PInt,
            "被识别为触发词的前缀(不填则为无命令前缀)": config.JsonList(str),
        }
        self.cfg, ver = config.get_plugin_config_and_version(
            self.name, {}, DEFAULT_CFG, self.version
        )

        if ver < (0, 3, 2) and self.cfg.get("help菜单样式"):
            updateCfg = [
                "管理选项",
                "创造选项",
                "成员选项",
                "菜单指令配置",
                "参数提示配置",
            ]
            for cfg in updateCfg:
                if cfg in DEFAULT_CFG["help菜单样式"]:
                    self.cfg["help菜单样式"][cfg] = DEFAULT_CFG["help菜单样式"][cfg]
            config.upgrade_plugin_config(self.name, self.cfg, self.version)
            self.print("§a配置文件已升级: " + ",".join(updateCfg))

        self.cfg, ver = config.get_plugin_config_and_version(
            self.name, STD_CFG_TYPE, DEFAULT_CFG, self.version
        )
        self.prefixs = self.cfg["被识别为触发词的前缀(不填则为无命令前缀)"]
        self.op_format = self.cfg["help菜单样式"]["管理选项"]["格式化"]
        self.is_op_format = self.cfg["help菜单样式"]["管理选项"]["为管理员"]
        self.isnot_op_format = self.cfg["help菜单样式"]["管理选项"]["不为管理员"]
        self.create_format = self.cfg["help菜单样式"]["创造选项"]["格式化"]
        self.is_create_format = self.cfg["help菜单样式"]["创造选项"]["为创造"]
        self.isnot_create_format = self.cfg["help菜单样式"]["创造选项"]["不为创造"]
        self.member_format = self.cfg["help菜单样式"]["成员选项"]["格式化"]
        self.is_member_format = self.cfg["help菜单样式"]["成员选项"]["为成员"]
        self.isnot_member_format = self.cfg["help菜单样式"]["成员选项"]["不为成员"]
        self.ListenChat(lambda chat: self.on_player_message(chat) and None)
        self.add_new_trigger(
            self.cfg["/help触发词"],
            [("页数", int, 1)],
            "展示命令帮助菜单",
            self.show_help,
        )

    # ----API----
    def add_new_trigger(
        self,
        triggers: list[str],
        argument_hint: ARGUMENT_HINT,
        usage: str,
        func: Callable[[Player, tuple], None],
        op_only: bool = False,
    ):
        """
        添加菜单触发词项.
        Args:
            triggers: 触发词列表
            argument_hint: 触发词参数提示, 每个元组为 (参数提示词: str, 参数类型: type, 默认参数值: Any (没有默认值则为 None))
            usage: 触发词功能说明
            func: 触发词对应的函数
            op_only: 是否仅 OP 可见和可用
        """
        for tri in triggers:
            if tri.startswith("."):
                triggers[triggers.index(tri)] = tri[1:]
        self.chatbar_triggers.append(
            StandardChatbarTriggers(
                triggers, argument_hint, usage, func, op_only, self.cfg
            )
        )

    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[[str, list[str]], None] | None,
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only=False,
    ):
        """
        添加菜单触发词项.
        Args:
            triggers (list[str]): 所有命令触发词
            argument_hint (str | None): 提示词(命令参数)
            usage (str): 显示的命令说明
            func (Callable | None): 菜单触发回调, 回调参数为(玩家名: str, 命令参数: list[str])
            args_pd ((int) -> bool): 判断方法 (参数数量:int) -> 参数数量是否合法: bool
            op_only (bool): 是否仅op可触发; 目前认为创造模式的都是OP, 你也可以自行更改并进行PR
        """
        for tri in triggers:
            if tri.startswith("."):
                triggers[triggers.index(tri)] = tri[1:]
        if func is None:

            def call_none(*args):
                return None

            self.chatbar_triggers.append(
                OldChatbarTriggers(
                    triggers, argument_hint, usage, call_none, args_pd, op_only
                )
            )
            return
        self.chatbar_triggers.append(
            OldChatbarTriggers(triggers, argument_hint, usage, func, args_pd, op_only)
        )

    # Desperated
    def add_simple_trigger(
        self,
        triggers: list[str],
        usage: str,
        func: Callable[[str, list[str]], Any],
        op_only=False,
    ):
        self.add_trigger(
            triggers,
            None,
            usage,
            func,
            op_only=op_only,
        )

    # ------------

    def show_help(self, player: Player, args):
        # page min = 1
        page: int = args[0]
        all_menu_args = self.chatbar_triggers
        if not player.is_op():
            # 仅 OP 可见的部分 过滤掉
            all_menu_args = list(filter(lambda x: not x.op_only, all_menu_args))
        lmt = self.cfg["单页内最多显示数"]
        total = len(all_menu_args)
        max_page = (total + lmt - 1) // lmt
        if page < 1:
            page_split_index = 0
        elif page > max_page:
            page_split_index = max_page - 1
        else:
            page_split_index = page - 1
        diplay_menu_args = all_menu_args[
            page_split_index * lmt : (page_split_index + 1) * lmt
        ]
        isCreate = bool(
            self.game_ctrl.sendcmd_with_resp(
                "/querytarget @a[name=" + player.name + ",m=creative]", 1
            ).SuccessCount
        )
        player.show(
            utils.simple_fmt(
                {
                    self.op_format: self.is_op_format
                    if player.is_op()
                    else self.isnot_op_format,
                    self.create_format: self.is_create_format
                    if isCreate
                    else self.isnot_create_format,
                    self.member_format: self.is_member_format,  # 没想到怎么检测是否为成员
                },
                self.cfg["help菜单样式"]["菜单头"],
            )
        )
        if self.prefixs != []:
            first_prefix = self.prefixs[0]
        else:
            first_prefix = ""
        for tri in diplay_menu_args:
            player.show(
                utils.simple_fmt(
                    {
                        "[菜单指令]": (
                            self.cfg["help菜单样式"]["菜单指令配置"]["指令配色"]["管理"]
                            if tri.op_only
                            else self.cfg["help菜单样式"]["菜单指令配置"]["指令配色"][
                                "成员"
                            ]
                        )
                        + (
                            self.cfg["help菜单样式"]["菜单指令配置"]["指令分隔符"]
                            + (
                                self.cfg["help菜单样式"]["菜单指令配置"]["指令配色"][
                                    "管理"
                                ]
                                if tri.op_only
                                else self.cfg["help菜单样式"]["菜单指令配置"][
                                    "指令配色"
                                ]["成员"]
                            )
                        ).join([first_prefix + i for i in tri.triggers])
                        + "§r",
                        "[参数提示]": (
                            " " + tri.argument_hints_str
                            if (
                                isinstance(tri, StandardChatbarTriggers)
                                and tri.argument_hints
                            )
                            else ""
                        ),
                        "[菜单功能说明]": (
                            "" if tri.usage is None else "以" + tri.usage
                        ),
                    },
                    self.cfg["help菜单样式"]["菜单列表"],
                ),
            )
        player.show(
            utils.simple_fmt(
                {"[当前页数]": page_split_index + 1, "[总页数]": max_page},
                self.cfg["help菜单样式"]["菜单尾"],
            ),
        )

    @utils.thread_func("聊天栏菜单执行")
    def on_player_message(self, chat: Chat):
        player = chat.player
        msg = chat.msg
        if self.prefixs:
            for prefix in self.prefixs:
                if msg.startswith(prefix):
                    msg = msg[len(prefix) :]
                    break
            else:
                return
        player_is_op = player.is_op()
        for trigger in self.chatbar_triggers:
            for trigger_str in trigger.triggers:
                if msg.startswith(trigger_str):
                    if (not player_is_op) and trigger.op_only:
                        player.show("§c创造模式或者OP才可以使用该菜单项")
                        return
                    args = msg.removeprefix(trigger_str).split()
                    with utils.ChatbarLock(player.name):
                        if isinstance(trigger, StandardChatbarTriggers):
                            trigger.execute(player, args)
                        else:
                            trigger.func(player.name, args)
                        return

    def on_menu_warn(self, player: str):
        self.game_ctrl.say_to(player, "§c退出当前菜单才能继续唤出菜单")


entry = plugin_entry(ChatbarMenu, ["聊天栏菜单", "chatbarmenu"])
