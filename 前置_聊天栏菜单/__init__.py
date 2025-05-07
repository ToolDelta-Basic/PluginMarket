from tooldelta import Plugin, Player, cfg as config, utils, Chat, plugin_entry
from typing import Any
from dataclasses import dataclass
from collections.abc import Callable

from .config_getter import DefaultMenuStyle, NBCMenuStyle, DEFAULT_CFG


VALID_ARGUMENT_HINT_TYPES = type[str | int | bool | float]  # | tuple[str]
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


def arg_str(arg: str | float | bool):
    if isinstance(arg, str | float):
        return str(arg)
    else:
        return "true" if arg else "false"


def show_args(
    player: Player, prefix: str, arg_hints: ARGUMENT_HINT, current_arg_index: int
):
    args = []
    for i, (name, type, default_val) in enumerate(arg_hints):
        if i == current_arg_index:
            argstr = "§b"
        else:
            argstr = "§7"
        argstr += "[" + name + ":"
        if default_val is not None:
            argstr += arg_str(default_val)
        else:
            argstr += type_str(type)
        argstr += "]"
        args.append(argstr)
    player.show(f"{prefix} " + " ".join(args))


def ask_for_args(player: Player, prefix: str, arg_hints: ARGUMENT_HINT):
    final_args = []
    for i, (name, argtype, default_val) in enumerate(arg_hints):
        while 1:
            show_args(player, prefix, arg_hints, i)
            if default_val is not None:
                resp = player.input(f"§7请输入§f{name}§7：", timeout=240)
            else:
                resp = player.input(
                    f"§7请输入§f{name}§7 （输入？使用默认值）：", timeout=240
                )
            if resp is None:
                player.show("§c输入命令参数超时")
                return None
            elif (resp == "？" or resp == "?") and default_val is not None:
                final_args.append(default_val)
                break
            try:
                arg_parsed = parse_arg(resp, argtype)
                final_args.append(arg_parsed)
                break
            except Exception as e:
                player.show(f"§c输入参数错误： {e}")
    return tuple(final_args)


def type_str(argtype: VALID_ARGUMENT_HINT_TYPES):
    if argtype is str:
        return "字符串"
    elif argtype is int:
        return "整数"
    elif argtype is float:
        return "数值"
    elif argtype is bool:
        return "[true|false]"
    else:
        return "未知类型"


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
        func: Callable[[Player, tuple], Any],
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

    def execute_with_no_args(self, player: Player, command_prefix: str):
        args = ask_for_args(player, command_prefix, self.argument_hints)
        if args is None:
            return
        self.func(player, args)

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

        elif ver < (0, 3, 3):
            self.cfg["是否启用指令序号式菜单样式"] = DEFAULT_CFG[
                "是否启用指令序号式菜单样式"
            ]
            self.cfg["指令序号式菜单样式"] = DEFAULT_CFG["指令序号式菜单样式"]
            config.upgrade_plugin_config(self.name, self.cfg, self.version)
            self.print(
                "§a配置文件已升级: 指令序号式菜单样式、是否启用指令序号式菜单样式"
            )

        self.cfg, ver = config.get_plugin_config_and_version(
            self.name, config.auto_to_std(DEFAULT_CFG), DEFAULT_CFG, self.version
        )
        self.prefixs = self.cfg["被识别为触发词的前缀(不填则为无命令前缀)"]
        self.help_args_limit = self.cfg["单页内最多显示数"]
        self.enable_nbc_format = self.cfg["是否启用指令序号式菜单样式"]
        # default style
        self.default_style = DefaultMenuStyle(self.cfg)
        # num-based command menu style
        self.nbc_style = NBCMenuStyle(self.cfg)
        #
        self.ListenChat(lambda chat: self.on_player_message(chat) and None)
        if self.enable_nbc_format:
            self.add_new_trigger(
                self.cfg["/help触发词"],
                [],
                "打开菜单",
                self.show_nbc_menu,
            )
            self.add_new_trigger(
                ["test", "td"],
                [("aint", int, None), ("bstr", str, "a"), ("cbool", bool, False)],
                "testargs",
                lambda a, b: a.show(f"args: {b}"),
            )
        else:
            self.add_new_trigger(
                self.cfg["/help触发词"],
                [("页数", int, 1)],
                "展示命令帮助菜单",
                self.show_default_help,
            )

    # ----API----
    def add_new_trigger(
        self,
        triggers: list[str],
        argument_hint: ARGUMENT_HINT,
        usage: str,
        func: Callable[[Player, tuple], Any],
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
        func: Callable[[str, list[str]], Any] | None,
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only=False,
    ):
        """
        Deprecated: Use `add_new_trigger` instead.
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

    # ------------

    def show_default_help(self, player: Player, args):
        # page min = 1
        page: int = args[0]
        all_menu_args = self.chatbar_triggers
        if not player.is_op():
            # 仅 OP 可见的部分 过滤掉
            all_menu_args = list(filter(lambda x: not x.op_only, all_menu_args))
        total = len(all_menu_args)
        max_page = (total + self.help_args_limit - 1) // self.help_args_limit
        if page < 1:
            page_split_index = 0
        elif page > max_page:
            page_split_index = max_page - 1
        else:
            page_split_index = page - 1
        diplay_menu_args = all_menu_args[
            page_split_index * self.help_args_limit : (page_split_index + 1)
            * self.help_args_limit
        ]
        isCreate = bool(
            self.game_ctrl.sendcmd_with_resp(
                '/querytarget @a[name="' + player.name + '",m=creative]', 1
            ).SuccessCount
        )
        player.show(
            utils.simple_fmt(
                {
                    self.default_style.op_format: self.default_style.is_op_format
                    if player.is_op()
                    else self.default_style.isnot_op_format,
                    self.default_style.create_format: self.default_style.is_create_format
                    if isCreate
                    else self.default_style.isnot_create_format,
                    self.default_style.member_format: self.default_style.is_member_format,  # 没想到怎么检测是否为成员
                },
                self.default_style.header,
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
                            self.default_style.cmd_color_op
                            if tri.op_only
                            else self.default_style.cmd_color_member
                        )
                        + (
                            self.default_style.cmd_sep
                            + (
                                self.default_style.cmd_color_op
                                if tri.op_only
                                else self.default_style.cmd_color_member
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
                    self.default_style.content,
                ),
            )
        player.show(
            utils.simple_fmt(
                {"[当前页数]": page_split_index + 1, "[总页数]": max_page},
                self.default_style.footer,
            ),
        )

    @utils.thread_func("打开聊天栏序号选择菜单")
    def show_nbc_menu(self, player: Player, _):
        all_sections = [
            section
            for section in self.chatbar_triggers
            if isinstance(section, StandardChatbarTriggers)
        ]
        if all_sections == []:
            player.show("§c目前菜单内一项命令都没有哦？！")
            return
        sections_with_blocks = utils.split_list(all_sections, self.help_args_limit)
        max_page_num = len(sections_with_blocks)
        is_creation_mode = bool(
            self.game_ctrl.sendcmd_with_resp(
                '/querytarget @a[name="' + player.name + '",m=creative]', 1
            ).SuccessCount
        )
        section_page = 0
        if self.prefixs != []:
            first_prefix = self.prefixs[0]
        else:
            first_prefix = ""
        while 1:
            sections_now_page = sections_with_blocks[section_page]
            player.show(
                utils.simple_fmt(
                    {
                        self.nbc_style.op_format: self.nbc_style.is_op_format
                        if player.is_op()
                        else self.nbc_style.isnot_op_format,
                        self.nbc_style.create_format: self.nbc_style.is_create_format
                        if is_creation_mode
                        else self.nbc_style.isnot_create_format,
                        self.nbc_style.member_format: self.nbc_style.is_member_format,  # 没想到怎么检测是否为成员
                    },
                    self.nbc_style.header,
                )
            )
            for i, tri in enumerate(sections_now_page):
                display_index = i + 1 + section_page * self.help_args_limit
                player.show(
                    utils.simple_fmt(
                        {
                            "[序号]": display_index,
                            "[菜单指令]": (
                                self.nbc_style.cmd_color_op
                                if tri.op_only
                                else self.nbc_style.cmd_color_member
                            )
                            + (
                                self.nbc_style.cmd_sep
                                + (
                                    self.nbc_style.cmd_color_op
                                    if tri.op_only
                                    else self.nbc_style.cmd_color_member
                                )
                            ).join([first_prefix + i for i in tri.triggers])
                            + "§r",
                            "[参数提示]": (
                                " " + tri.argument_hints_str
                                if tri.argument_hints
                                else ""
                            ),
                            "[菜单功能说明]": (
                                "" if tri.usage is None else "以" + tri.usage
                            ),
                        },
                        self.nbc_style.content,
                    ),
                )
            player.show(
                utils.simple_fmt(
                    {"[当前页数]": section_page + 1, "[总页数]": max_page_num},
                    self.nbc_style.footer,
                ),
            )
            while 1:
                resp = player.input(timeout=300)
                if resp is None:
                    player.show("§c看起来你太久没有选择一项菜单项.. 已退出")
                    return
                resp = resp.strip()
                if resp == "退出" or resp == "q":
                    player.show(self.nbc_style.exit_format)
                    return
                elif resp == "+":
                    section_page = min(section_page + 1, max_page_num - 1)
                    break
                elif resp == "-":
                    section_page = max(section_page - 1, 0)
                    break
                resp_int = utils.try_int(resp)
                if resp_int is None or resp_int not in range(1, len(all_sections) + 1):
                    player.show(f"§c请输入 1 ~ {len(all_sections) + 1} 范围内的序号")
                    continue
                section = all_sections[resp_int - 1]
                section.execute_with_no_args(player, section.triggers[0])
                return

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
