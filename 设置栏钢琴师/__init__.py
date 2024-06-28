from tooldelta import plugins, Plugin

@plugins.add_plugin
class SettingsPiano(Plugin):
    name = "设置栏弹钢琴v2"
    author = "SuperScript"
    version = (0, 0, 7)
    description = "调节设置栏-世界选项的前8个选项会发出不同的乐音, 第九个选项可开启或关闭钢琴弹奏和键位锁定, 重生半径可设置音高域"

    lock = False
    ks = []
    base_8 = 0

    @plugins.add_packet_listener(72)
    def rec(self, pkt):
        pitch = 0
        pk = pkt["GameRules"][0]["Name"]
        match pk:
            case "pvp":
                pitch = 1.4
            case "showcoordinates":
                pitch = 1.55
            case "dofiretick":
                pitch = 1.75
            case "tntexplodes":
                pitch = 1.9
            case "respawnblocksexplode":
                pitch = 2.1
            case "domobloot":
                pitch = 2.35
            case "naturalregeneration":
                pitch = 2.6
            case "dotiledrops":
                pitch = 2.8
            case "spawnradius":
                self.base_8 = max(0, pkt["GameRules"][0]["Value"]/2) - 5
                if self.base_8 + 5 not in range(3, 7):
                    self.game_ctrl.say_to("@a", f"§c音域太高或者太低啦({self.base_8 + 5})， 这样是听不到钢琴音乐的！ §6建议范围： 3~7")
                else:
                    self.game_ctrl.say_to("@a", f"设置栏钢琴 音高域已变为: §a{self.base_8 + 5}")
            case "doimmediaterespawn":
                if pkt["GameRules"][0]["Value"]:
                    self.lock = [True, False][self.lock]
                    self.game_ctrl.say_to("@a", f"钢琴键演奏&锁定模式: {['§cOff', '§aOn'][self.lock]}")
                    if self.lock:
                        self.game_ctrl.sendcmd("execute as @a run playsound random.toast @s")
                    else:
                        self.game_ctrl.sendcmd("execute as @a run playsound random.toast @s ~~~ 1 0.5")
                return False
            case _:
                return False
        if self.lock and isinstance(pkt['GameRules'][0]['Value'], bool):
            if  pk not in self.ks:
                self.ks.append(pk)
                self.game_ctrl.sendwocmd(f"/gamerule {pk} {['true', 'false'][pkt['GameRules'][0]['Value']]}")
                cmd = f"/execute as @a run playsound note.pling @s ~~~ 1 {pitch * 2 ** self.base_8}"
                self.game_ctrl.sendwocmd(cmd)
            else:
                self.ks.remove(pk)
        return False

        # pvp
        # showcoordinates
        # dofiretick
        # tntexplodes
        # respawnblocksexplode
        # domobloot
        # naturalregeneration
        # dotiledrops
        # doimmediaterespawn

        # spawnradius

        # dodaylightcycle
        # keepinventory
        # domobspawning
        # mobgriefing
        # doentitydrops
        # doweathercycle