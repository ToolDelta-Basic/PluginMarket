import time
from tooldelta import Plugin, plugins, Utils, Print


def getPrevChar(string: str, index: int):
    return string[index - 1] if index - 1 in range(len(string)) else ""

def getNextChar(string: str, index: int):
    return string[index + 1] if index + 1 in range(len(string)) else ""

def hasUpper(string: str):
    return any(i.isupper() for i in string)


def hasLower(string: str):
    return any(i.islower() for i in string)


def hasNumber(string: str):
    return any(i.isdigit() for i in string)

def test_name_similar_percent(name: str):
    probably = 0
    if len(name) == 10 and name.isascii():
        # 很可能就是机器人随机生成的名字
        probably += 5
    for i, char in enumerate(name):
        nextChar = getNextChar(name, i)
        if not char.isascii():
            # 中文名, 不大可能是了, 权重减小
            probably -= 1
        if char.isdigit() and nextChar.isalpha():
            # 数字后面接着字母
            probably += 2.5
        if char.islower() and nextChar.isupper():
            # 小写字母后跟着大写字母
            probably += 1.5
    return probably / len(name)


@plugins.add_plugin
class ServerRestKicker(Plugin):
    name = "崩服机器人踢出"
    author = "SuperScript"
    version = (0, 0, 1)

    def on_def(self):
        self.action_list = []

    def on_player_prejoin(self, player: str):
        if test_name_similar_percent(player) >= 0.4:
            self.action(player)

    def on_player_leave(self, player: str):
        if player in self.action_list:
            self.action_list.remove(player)

    @Utils.thread_func("可疑崩服机器人制裁")
    def action(self, player: str):
        self.action_list.append(player)
        Print.print_war(f"疑似 {player} 为崩服机器人， 正在制裁..")
        while player in self.action_list:
            self.game_ctrl.sendwocmd(f'kick "{player}" PyRPC Check failed')
            time.sleep(0.01)
        Print.print_suc(f"疑似 {player} 为崩服机器人， 制裁已完成")
