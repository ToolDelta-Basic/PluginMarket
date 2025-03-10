import re
from tooldelta import (
    ToolDelta,
    Plugin,
    Config,
    utils,
    Print,
    game_utils,
    plugin_entry,
    TYPE_CHECKING,
)


class CustomChatbarMenu(Plugin):
    name = "自定义聊天栏菜单"
    author = "SuperScript"
    version = (0, 0, 6)
    description = "自定义ToolDelta的聊天栏菜单触发词等"
    args_match_rule = re.compile(r"(\[参数:([0-9]+)\])")
    scb_simple_rule = re.compile(r"\[计分板:([^\[\]]+)\]")
    scb_replace_simple_rule = re.compile(r"\[计分板替换:([^\[\(\)\]]+)\(([^\)]+)\)\]")
    scb_replace_next_rule = re.compile(r"([0-9~]+):([^ ]+)")
    _counter = 0

    def __init__(self, frame: ToolDelta):
        self.game_ctrl = frame.get_game_control()
        STD_CFG = {
            "菜单项": Config.JsonList(
                {
                    "触发词": Config.JsonList(str),
                    "参数提示": str,
                    "功能简介": str,
                    "需要的参数数量": Config.NNInt,
                    "触发后执行的指令": Config.JsonList(str),
                    "仅OP可用": bool,
                },
            )
        }
        DEFAULT_CFG = {
            "菜单项": [
                {
                    "说明": "返回重生点",
                    "触发词": ["kill", "自尽"],
                    "需要的参数数量": 0,
                    "参数提示": "",
                    "功能简介": "返回重生点",
                    "触发后执行的指令": [
                        "/kill [玩家名]",
                        "/title [玩家名] actionbar 自尽成功",
                    ],
                    "仅OP可用": False,
                },
                {
                    "说明": "一个测试菜单参数项的触发词菜单项",
                    "触发词": ["测试参数"],
                    "需要的参数数量": 2,
                    "参数提示": "[参数1] [参数2]",
                    "功能简介": "测试触发词参数",
                    "触发后执行的指令": [
                        "/w [玩家名] 触发词测试成功: 参数1=[参数:1], 参数2=[参数:2]"
                    ],
                    "仅OP可用": True,
                },
                {
                    "说明": "一个个人档案的示例",
                    "触发词": ["个人档案", "prof"],
                    "需要的参数数量": 0,
                    "参数提示": "",
                    "功能简介": "查看个人档案",
                    "触发后执行的指令": [
                        "td:/show §e| §l个人档案§r§e |",
                        "td:/show §7▶ §e金币: [计分板:金币]",
                        "td:/show §7▶ §d在线时长: [计分板:在线时长]",
                        "td:/show §7▶ §6您的性别: [计分板替换:性别(0:未知 1:男 2:女)]",
                        "td:/show §7▶ §c金币称号: [计分板替换:金币(0~1000:平民 1001~10000:公民 10001~80000:中产 80001~150000:富婆)]",
                    ],
                    "仅OP可用": False,
                },
            ]
        }
        self.cfg, _ = Config.getPluginConfigAndVersion(
            self.name, STD_CFG, DEFAULT_CFG, self.version
        )
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu

            self.chatbar = self.get_typecheck_plugin_api(ChatbarMenu)

    @utils.thread_func("初始化菜单项")
    def on_inject(self):
        for menu in self.cfg["菜单项"]:
            cb = self.make_cb_func(menu)
            self.chatbar.add_trigger(
                menu["触发词"],
                menu["参数提示"],
                menu["功能简介"],
                cb,
                op_only=menu["仅OP可用"],
            )

    def make_cb_func(self, menu):
        cmds = menu["触发后执行的指令"]

        @utils.thread_func("自定义聊天栏菜单执行")
        def _menu_cb_func(player: str, args: list):
            if not self.check_args_len(player, args, menu["需要的参数数量"]):
                return
            for cmd in cmds:
                f_cmd = utils.simple_fmt(
                    {"[玩家名]": player}, self.args_replace(args, cmd, player)
                )
                if f_cmd.startswith("td:/show "):
                    self.game_ctrl.say_to(player, f_cmd[8:])
                else:
                    self.game_ctrl.sendwscmd(f_cmd)

        return _menu_cb_func

    def args_replace(self, args: list, sub: str, user: str):
        res = self.args_match_rule.findall(sub)
        for varsub, var_arg in res:
            try:
                var_value = args[int(var_arg) - 1]
                sub = sub.replace(varsub, var_value)
            except IndexError:
                Print.print_err("聊天栏菜单: 菜单的参数项提供异常!")
                self.game_ctrl.say_to(
                    "@a", "聊天栏菜单: 菜单的参数项提供异常， 请联系管理员以修复"
                )
                raise SystemExit
        res = self.scb_simple_rule.findall(sub)
        for scb_name in res:
            try:
                score = str(game_utils.getScore(scb_name, user, 3))
            except ValueError:
                score = "<未知>"
                Print.print_war(f"自定义聊天栏菜单: 获取 {scb_name}:{user} 的分数失败")
            except TimeoutError:
                score = "<未知>"
            sub = sub.replace(f"[计分板:{scb_name}]", score)
        res = self.scb_replace_simple_rule.findall(sub)
        for scb_name, scb_repl in res:
            try:
                repl_text = "<未知分数>"
                score = game_utils.getScore(scb_name, user, 3)
                repl_text = f"<未知替换样式:{score}>"
                res2 = self.scb_replace_next_rule.findall(scb_repl)
                for scb_num_repl, scb_str_repl in res2:
                    if "~" not in scb_num_repl:
                        if score == int(scb_num_repl):
                            repl_text = scb_str_repl
                            break
                    elif scb_num_repl.count("~") != 1:
                        repl_text = "<错误的替换样式:波浪号过多>"
                        break
                    else:
                        score_front, score_back = scb_num_repl.split("~")
                        score_front, score_back = int(score_front), int(score_back)
                        if score in range(score_front, score_back + 1):
                            repl_text = scb_str_repl
                            break
            except ValueError:
                score = None
                Print.print_war(f"自定义聊天栏菜单: 获取 {scb_name}:{user} 的分数失败")
            except TimeoutError:
                score = None
                Print.print_war(f"自定义聊天栏菜单: 获取 {scb_name}:{user} 的分数超时")
            sub = sub.replace(f"[计分板替换:{scb_name}({scb_repl})]", repl_text)
        return sub

    def check_args_len(self, player, args, need_len):
        if len(args) < need_len:
            self.game_ctrl.say_to(player, f"§c菜单参数太少， 需要 {need_len} 个")
            return False
        return True


entry = plugin_entry(CustomChatbarMenu)
