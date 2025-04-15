import json
from tooldelta import Plugin, Frame, fmts, plugin_entry


class ConsoleCommands(Plugin):
    name = "控制台执行MC指令"
    author = "SuperScript"
    version = (0, 0, 4)

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.ListenActive(self.on_inject)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["ws/"], "[指令]", "执行WS指令", self.SendWSCmdOnConsole
        )
        self.frame.add_console_cmd_trigger(
            ["wo/"], "[指令]", "执行控制台权限指令", self.SendWOCmdOnConsole
        )

    def SendWSCmdOnConsole(self, cmd):
        try:
            result = self.game_ctrl.sendcmd_with_resp(" ".join(cmd), 5)
        except IndexError:
            fmts.print_err("缺少指令参数")
            return
        try:
            if (result.OutputMessages[0].Message == "commands.generic.syntax") | (
                result.OutputMessages[0].Message == "commands.generic.unknown"
            ):
                fmts.print_err("未知的MC指令， 可能是指令格式有误")
            else:
                jso = json.dumps(
                    result.as_dict["OutputMessages"], indent=2, ensure_ascii=False
                )
                if not result.SuccessCount:
                    fmts.print_war(f"指令执行失败：\n{jso}")
                else:
                    fmts.print_suc(f"指令执行成功： \n{jso}")
        except IndexError:
            if result.SuccessCount:
                jso = json.dumps(
                    result.as_dict["OutputMessages"], indent=2, ensure_ascii=False
                )
                fmts.print_suc(f"指令执行成功： \n{jso}")
        except TimeoutError:
            fmts.print_err("[超时] 指令获取结果返回超时")

    def SendWOCmdOnConsole(self, cmd):
        self.game_ctrl.sendwocmd(" ".join(cmd))


entry = plugin_entry(ConsoleCommands)
