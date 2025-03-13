from tooldelta import tooldelta, utils
from tooldelta.plugin_load.injected_plugin import (
    repeat,
)
from tooldelta.game_utils import get_all_player, rawText, sendcmd, getTarget, waitMsg

__plugin_meta__ = {
    "name": "多功能tpa",
    "version": "0.1.0",
    "author": "wling/SuperScript",
}

display = "§a§l传送系统 §7>>> §r"

tpa_requests: list["TpaRequest"] = []


class TpaRequest:
    def __init__(self, sender: str, target: str, mode="tpa"):
        assert mode in ["tpa", "tpahere"], "不合法的模式"
        self.sender = sender
        self.target = target
        self.need_count = False
        self.mode = mode
        self.secs = 30
        rawText(self.sender, "§6已发送请求， 等待回应..")
        rawText(self.sender, "§6输入§e.tpa rej§6可放弃请求.")
        if mode == "tpa":
            rawText(self.target, f"§e{self.sender}§f希望传送到你这里.")
        else:
            rawText(self.target, f"§e{self.sender}§f希望你传送到他那里.")
        rawText(self.target, "§f输入§a.tpa acc§f同意， §c.tpa dec§f拒绝")

    def accept(self):
        rawText(self.sender, "§a请求已通过， 已开始传送.")
        rawText(self.target, "§a已同意请求！")
        self.tp()
        self.delete()

    def deny(self):
        rawText(self.sender, f"§6互传请求已被§f{self.target}§6拒绝.")
        rawText(self.target, f"§a已拒绝§f{self.sender}§a的互传请求")
        self.delete()

    def reject(self):
        rawText(self.sender, f"§6发往§f{self.target}§6的互传请求已被撤销.")
        rawText(self.target, f"§6从§f{self.sender}§a发来的互传请求已被撤销.")
        self.delete()

    def timeout(self):
        rawText(self.sender, f"发往§e{self.target}§6的请求因超时被取消.")
        rawText(self.target, f"§e{self.sender}§6发来的请求已超时， 被自动取消.")
        self.delete()

    def tp(self):
        if self.mode == "tpa":
            sendcmd(f"tp {self.sender} {self.target}")
        else:
            sendcmd(f"tp {self.target} {self.sender}")

    def delete(self):
        tpa_requests.remove(self)


@utils.thread_func("tpa菜单")
def tpa_menu(player: str, args: list[str]):
    if args == []:
        rawText(player, "§6玩家互传tpa功能菜单：")
        rawText(player, " .tpa §7§o查看互传功能命令表")
        rawText(player, " .tpa <玩家名> §7§o请求传送到玩家所在地")
        rawText(player, " .tpahere <玩家名> §7§o请求玩家传送到此地")
        rawText(player, " .tpa acc / .tpaccept §7§o同意玩家发来的互传申请")
        rawText(player, " .tpa dec / .tpadeny §7§o拒绝玩家发来的互传申请")
        rawText(player, " .tpa rej / .tpareject §7§o撤销已发出的互传申请")
        rawText(player, " .tpa switch §7§o切换启用向自己发送互传申请的开关")
    elif args[0] == "switch":
        if player in getTarget("@a[tag=tp.deny]"):
            rawText(player, "§7已§a允许§7其他人向自己发送互传请求")
            sendcmd(f"tag {player} remove tpa.deny")
        else:
            rawText(player, "§7已§c禁止§7其他人向自己发送互传请求")
            sendcmd(f"tag {player} add tpa.deny")
    elif args[0] == "acc" or args[0] == "accept":
        for i in tpa_requests:
            if i.target == player:
                i.accept()
                return
        rawText(player, "§6你当前没有需要同意的互传请求")
    elif args[0] == "dec" or args[0] == "deny":
        for i in tpa_requests:
            if i.target == player:
                i.deny()
                return
        rawText(player, "§6你当前没有需要拒绝的互传请求")
    elif args[0] == "rej" or args[0] == "reject":
        for i in tpa_requests:
            if i.target == player:
                i.reject()
                return
        rawText(player, "§6你当前没有需要撤销的互传请求")
    else:
        if args[0] == "here":
            mode = "tpahere"
            rep = args[1]
        else:
            rep = args[0]
            mode = "tpa"
        allplayers = get_all_player()
        if rep in allplayers:
            getting = rep
        else:
            results = [i for i in allplayers if rep in i]
            if not results:
                rawText(player, f"§c没有一个玩家名匹配关键词： {rep}")
                return
            rawText(player, "§6当前通过关键词找到的玩家名列表如下：")
            for i, j in enumerate(results):
                rawText(player, f"§f{i+1}§7： §f{j}")
            rawText(player, f"§6输入序号§f1~{len(results)}§6以选择：")
            resp = utils.try_int(waitMsg(player))
            if resp is None or resp not in range(1, len(results) + 1):
                rawText(player, "§c序号错误或超过30s未输入， 已退出")
                return
            getting = results[resp - 1]
        if getting in getTarget("@a[tag=tp.deny]"):
            rawText(player, "§c此人已设置拒绝互传！")
            return
        for i in tpa_requests:
            if i.sender == player:
                rawText(player, "§c你的上一个传送请求还没有结束")
                return
        tpa_requests.append(TpaRequest(player, getting, mode))


tooldelta.plugin_group.get_plugin_api("聊天栏菜单").add_trigger(
    ["tpa"],
    None,
    "显示tpa帮助菜单",
    tpa_menu,
)


@repeat(1)
async def repeater_tpa():
    for i in tpa_requests:
        i.secs -= 1
        if i.secs < 1:
            i.timeout()
