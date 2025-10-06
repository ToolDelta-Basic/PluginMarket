import json
from tooldelta import Plugin, Frame, Print, plugin_entry


class ConsoleCommands(Plugin):
    name = "控制台执行MC指令"
    author = "SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.funclib = self.GetPluginAPI("基本插件功能库")

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["ws/"], "[指令]", "执行WS指令", self.SendWSCmdOnConsole
        )
        self.frame.add_console_cmd_trigger(
            ["wo/"], "[指令]", "执行控制台权限指令", self.SendWOCmdOnConsole
        )
        self.frame.add_console_cmd_trigger(
            ["ai/"], "[指令]", "执行魔法指令", self.SendAICmdOnConsole
        )

    def SendWSCmdOnConsole(self, cmd):
        try:
            result = self.game_ctrl.sendwscmd_with_resp(" ".join(cmd), 5)
        except IndexError:
            Print.print_err("缺少指令参数")
            return
        try:
            if (result.OutputMessages[0].Message == "commands.generic.syntax") | (
                result.OutputMessages[0].Message == "commands.generic.unknown"
            ):
                Print.print_err("未知的MC指令， 可能是指令格式有误")
            else:
                jso = json.dumps(
                    result.as_dict["OutputMessages"], indent=2, ensure_ascii=False
                )
                if not result.SuccessCount:
                    Print.print_war(f"指令执行失败：\n{jso}")
                else:
                    Print.print_suc(f"指令执行成功： \n{jso}")
        except IndexError:
            if result.SuccessCount:
                jso = json.dumps(
                    result.as_dict["OutputMessages"], indent=2, ensure_ascii=False
                )
                Print.print_suc(f"指令执行成功： \n{jso}")
        except TimeoutError:
            Print.print_err("[超时] 指令获取结果返回超时")

    def SendWOCmdOnConsole(self, cmd):
        self.game_ctrl.sendwocmd(" ".join(cmd))

    def SendAICmdOnConsole(self, cmd):
        self.funclib.sendaicmd(" ".join(cmd))


entry = plugin_entry(ConsoleCommands)
