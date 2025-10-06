from tooldelta import Plugin, Player, ToolDelta, utils, plugin_entry
from tooldelta.game_utils import getTarget


tpa_requests: list["TpaRequest"] = []


class TpaRequest:
    def __init__(self, sender: Player, target: Player, mode="tpa"):
        assert mode in ["tpa", "tpahere"], "不合法的模式"
        self.sender = sender
        self.target = target
        self.need_count = False
        self.mode = mode
        self.secs = 30
        self.sender.show( "§6已发送请求， 等待回应..")
        self.sender.show( "§6输入§e.tpa rej§6可放弃请求.")
        if mode == "tpa":
            self.target.show( f"§e{self.sender.name}§f希望传送到你这里.")
        else:
            self.target.show( f"§e{self.sender.name}§f希望你传送到他那里.")
        self.target.show( "§f输入§a.tpa acc§f同意， §c.tpa dec§f拒绝")

    def accept(self):
        self.sender.show( "§a请求已通过， 已开始传送.")
        self.target.show( "§a已同意请求！")
        self.tp()
        self.delete()

    def deny(self):
        self.sender.show( f"§6互传请求已被§f{self.target.name}§6拒绝.")
        self.target.show( f"§a已拒绝§f{self.sender.name}§a的互传请求")
        self.delete()

    def reject(self):
        self.sender.show( f"§6发往§f{self.target.name}§6的互传请求已被撤销."
        )
        self.target.show( f"§6从§f{self.sender.name}§a发来的互传请求已被撤销."
        )
        self.delete()

    def timeout(self):
        self.sender.show( f"发往§e{self.target.name}§6的请求因超时被取消.")
        self.target.show( f"§e{self.sender.name}§6发来的请求已超时， 被自动取消."
        )
        self.delete()

    def tp(self):
        if self.mode == "tpa":
            entry.game_ctrl.sendcmd(f"tp {self.sender.getSelector()} {self.target.name}")
        else:
            entry.game_ctrl.sendcmd(f"tp {self.target.name} {self.sender.getSelector()}")

    def delete(self):
        tpa_requests.remove(self)


class TpaSystem(Plugin):
    name = "多功能tpa玩家互传"
    author = "wling/SuperScript/Hazelmeow"
    version = (0, 1, 4)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.repeater_tpa)

    def on_preload(self):
        self.GetPluginAPI("聊天栏菜单").add_new_trigger(
            ["tpa"],
            [("", str, "help")],
            "显示tpa帮助菜单",
            self.tpa_menu,
        )

    @utils.thread_func("tpa菜单")
    def tpa_menu(self, player: Player, args: list[str]):
        if args[0] == "help":
            player.show( "§6玩家互传tpa功能菜单：")
            player.show( " .tpa §7§o查看互传功能命令表")
            player.show( " .tpa <玩家名> §7§o请求传送到玩家所在地")
            player.show( " .tpahere <玩家名> §7§o请求玩家传送到此地")
            player.show( " .tpa acc / .tpaccept §7§o同意玩家发来的互传申请"
            )
            player.show( " .tpa dec / .tpadeny §7§o拒绝玩家发来的互传申请"
            )
            player.show( " .tpa rej / .tpareject §7§o撤销已发出的互传申请"
            )
            player.show( " .tpa switch §7§o切换启用向自己发送互传申请的开关"
            )
        elif args[0] == "switch":
            if player.name in getTarget("@a[tag=tp.deny]"):
                player.show( "§7已§a允许§7其他人向自己发送互传请求")
                self.game_ctrl.sendcmd(f"tag {player} remove tpa.deny")
            else:
                player.show( "§7已§c禁止§7其他人向自己发送互传请求")
                self.game_ctrl.sendcmd(f"tag {player} add tpa.deny")
        elif args[0] == "acc" or args[0] == "accept":
            for i in tpa_requests:
                if i.target is player:
                    i.accept()
                    return
            player.show( "§6你当前没有需要同意的互传请求")
        elif args[0] == "dec" or args[0] == "deny":
            for i in tpa_requests:
                if i.target is player:
                    i.deny()
                    return
            player.show( "§6你当前没有需要拒绝的互传请求")
        elif args[0] == "rej" or args[0] == "reject":
            for i in tpa_requests:
                if i.target is player:
                    i.reject()
                    return
            player.show( "§6你当前没有需要撤销的互传请求")
        else:
            if args[0] == "here":
                mode = "tpahere"
                rep = args[1]
            else:
                rep = args[0]
                mode = "tpa"
            players = list(self.game_ctrl.players)
            if _getting := self.game_ctrl.players.getPlayerByName(rep):
                getting = _getting
            else:
                results = [i for i in players if rep in i.name]
                if not results:
                    player.show( f"§c没有一个玩家名匹配关键词： {rep}"
                    )
                    return
                player.show( "§6当前通过关键词找到的玩家名列表如下：")
                for i, j in enumerate(results):
                    player.show( f"§f{i + 1}§7： §f{j.name}")
                player.show( f"§6输入序号§f1~{len(results)}§6以选择："
                )
                resp = utils.try_int(player.input())
                if resp is None or resp not in range(1, len(results) + 1):
                    player.show( "§c序号错误或超过30s未输入， 已退出")
                    return
                getting = results[resp - 1]
            if getting.name in getTarget("@a[tag=tp.deny]"):
                player.show( "§c此人已设置拒绝互传！")
                return
            for i in tpa_requests:
                if i.sender == player:
                    player.show( "§c你的上一个传送请求还没有结束")
                    return
            tpa_requests.append(TpaRequest(player, getting, mode))

    @utils.timer_event(1, "玩家互传计时器")
    def repeater_tpa(self):
        for i in tpa_requests.copy():
            i.secs -= 1
            if i.secs < 1:
                i.timeout()


entry = plugin_entry(TpaSystem)
