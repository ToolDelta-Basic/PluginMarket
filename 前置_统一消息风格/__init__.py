from tooldelta import Plugin, Player, cfg, utils, plugin_entry, TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from typing import TypeVar, LiteralString
    T = TypeVar("T")
    LT = TypeVar("LT", bound=LiteralString)


class StyledPlayerPrinter:
    def __init__(self, player: Player):
        self.player = player

    def info(self, text: str):
        entry.info(self.player, text)

    def warn(self, text: str):
        entry.warn(self.player, text)

    def success(self, text: str):
        entry.success(self.player, text)

    def failed(self, text: str):
        entry.failed(self.player, text)

    def error(self, text: str):
        entry.error(self.player, text)

    def input(self, text: str):
        return entry.input(self.player, text)

    def select(
        self, prompt: str, arguments: "list[T]", sections_formatter: "Callable[[T], str]"
    ) -> "T | None":
        return entry.select(self.player, prompt, arguments, sections_formatter)

    def select_meta(
        self,
        prompt: str,
        arguments: "list[T]",
        sections_formatter: "Callable[[T], str]",
        extra_sections_formatter: str,
        extra_sections: "tuple[LT, ...]",
    ) -> "T | LT | None":
        return entry.select_meta(
            self.player, prompt, arguments, sections_formatter, extra_sections_formatter, extra_sections
        )


class OneStyleMsg(Plugin):
    name = "统一消息风格"
    author = "ToolDelta"
    version = (0, 0, 3)

    def __init__(self, frame):
        super().__init__(frame)
        CFG_DEFAULT = {
            "普通消息": "§7[§fi§7] §f[消息]",
            "成功消息": "§7[§a√§7] §a[消息]",
            "警告消息": "§7[§6!§7] §6[消息]",
            "失败消息": "§7[§cx§7] §c[消息]",
            "报错消息": "§7[§4E§7] §c[消息]",
            "输入提示": "§7[§f!§7] §f[消息]",
            "选择格式": {
                "选择头": "§6[选择提示] §7>>>",
                "选项": "  [序号]. [内容]",
                "选择尾": "§7请输入 §f1~[最大序号] 中的一个序号以选择：",
                "选择尾(多页)": "§7请输入 §f1~[最大序号] 中的一个序号以选择 输入 §a+§7/§6-§7 进行翻页：",
                "向后翻页命令": "+",
                "向前翻页命令": "-",
                "单页最多项数": 10,
                "额外选项格式(如果存在额外选项)": "或[额外选项提示]："
            },
        }
        config, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )
        self.msg_common = config["普通消息"]
        self.msg_success = config["成功消息"]
        self.msg_warning = config["警告消息"]
        self.msg_failed = config["失败消息"]
        self.msg_error = config["报错消息"]
        self.msg_input = config["输入提示"]
        msg_select = config["选择格式"]
        self.msg_select_header = msg_select["选择头"]
        self.msg_select_content = msg_select["选项"]
        self.msg_select_footer = msg_select["选择尾"]
        self.msg_select_footer_multi = msg_select["选择尾(多页)"]
        self.msg_select_index_max = msg_select["单页最多项数"]
        self.cmd_select_prev_page = msg_select["向前翻页命令"]
        self.cmd_select_next_page = msg_select["向后翻页命令"]
        self.cmd_select_extra_sections = msg_select["额外选项格式(如果存在额外选项)"]
        if self.msg_select_index_max < 2:
            raise cfg.ConfigError("单页最多项数 太少; 至少需要为 2")

    def info(self, player: Player, text: str):
        player.show(self.msg_common.replace("[消息]", text))

    def warn(self, player: Player, text: str):
        player.show(self.msg_warning.replace("[消息]", text))

    def success(self, player: Player, text: str):
        player.show(self.msg_success.replace("[消息]", text))

    def failed(self, player: Player, text: str):
        player.show(self.msg_failed.replace("[消息]", text))

    def error(self, player: Player, text: str):
        player.show(self.msg_error.replace("[消息]", text))

    def input(self, player: Player, text: str):
        return player.input(self.msg_input.replace("[消息]", text))

    def select(
        self,
        player: Player,
        prompt: str,
        arguments: "list[T]",
        sections_formatter: "Callable[[T], str]",
    ) -> "T | None":
        if len(arguments) == 0:
            raise ValueError("arguments 不能为空列表")
        arguments_blocks = utils.split_list(arguments, self.msg_select_index_max)
        page = 0
        while 1:
            current_arguments = arguments_blocks[page]
            player.show(self.msg_select_header.replace("[选择提示]", prompt))
            for i, arg in enumerate(current_arguments):
                i += page * self.msg_select_index_max
                player.show(
                    utils.simple_fmt(
                        {"[序号]": i + 1, "[内容]": sections_formatter(arg)},
                        self.msg_select_content,
                    )
                )
            player.show(
                utils.simple_fmt(
                    {"[最大序号]": len(arguments) + 1}, self.msg_select_footer
                )
            )
            while 1:
                resp = player.input()
                if resp is None:
                    return None
                elif resp == self.cmd_select_prev_page:
                    page = max(0, page - 1)
                    break
                elif resp == self.cmd_select_next_page:
                    page = min(len(arguments_blocks) - 1, page + 1)
                    break
                r = utils.try_int(resp)
                if r is None or r < 1 or r > len(arguments) + 1:
                    self.warn(player, f"请输入 1~{len(arguments) + 1} 中的一个序号：")
                else:
                    return arguments[r - 1]

    def select_meta(
        self,
        player: Player,
        prompt: str,
        arguments: "list[T]",
        sections_formatter: "Callable[[T], str]",
        extra_sections_prompt: str,
        extra_sections: "tuple[LT, ...]",
    ) -> "T | LT | None":
        if len(arguments) == 0:
            raise ValueError("arguments 不能为空列表")
        arguments_blocks = utils.split_list(arguments, self.msg_select_index_max)
        page = 0
        while 1:
            current_arguments = arguments_blocks[page]
            player.show(self.msg_select_header.replace("[选择提示]", prompt))
            for i, arg in enumerate(current_arguments):
                i += page * self.msg_select_index_max
                player.show(
                    utils.simple_fmt(
                        {"[序号]": i + 1, "[内容]": sections_formatter(arg)},
                        self.msg_select_content,
                    )
                )
            if len(arguments_blocks) == 1:
                player.show(
                    utils.simple_fmt(
                        {"[最大序号]": len(arguments) + 1}, self.msg_select_footer
                    )
                )
            else:
                player.show(
                    utils.simple_fmt(
                        {"[最大序号]": len(arguments) + 1}, self.msg_select_footer_multi
                    )
                )
            player.show(self.cmd_select_extra_sections.replace("[额外选项提示]", extra_sections_prompt))
            while 1:
                resp = player.input()
                if resp is None:
                    return None
                elif resp in extra_sections:
                    return resp
                elif resp == self.cmd_select_prev_page:
                    page = max(0, page - 1)
                    break
                elif resp == self.cmd_select_next_page:
                    page = min(len(arguments_blocks) - 1, page + 1)
                    break
                r = utils.try_int(resp)
                if r is None or r < 1 or r > len(arguments) + 1:
                    self.warn(player, f"请输入 1~{len(arguments) + 1} 中的一个序号：")
                else:
                    return arguments[r - 1]

    def __call__(self, player: Player):
        return StyledPlayerPrinter(player)


entry = plugin_entry(OneStyleMsg, "统一消息风格")
