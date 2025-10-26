from tooldelta import Plugin, plugin_entry, Player, utils, Config
from tooldelta.constants import PacketIDS

class DeathBack(Plugin):
    name = "死亡点返回"
    author = "果_k"
    version = (0, 0, 3)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_DEFAULT = {
            "取消返回": "§c§l已自动取消返回",
            "成功返回提示词": "§a§l已返回死亡点",
            "等待输入时间": 20,
            "是否启用标签限制": False,
            "标签名称": "backdeath",
            "返回询问消息": "§a§l你死于 {dim} 维度的 {x} {y} {z} 是否返回？§b输入y同意 输入n拒绝"
        }
        CONFIG_STD = {
            "取消返回": str,
            "成功返回提示词": str,
            "等待输入时间": Config.NNInt,
            "是否启用标签限制": bool,
            "标签名称": str,
            "返回询问消息": str
        }
        cfg, _ = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.BackInfo = cfg["取消返回"]
        self.SuccessInfo = cfg["成功返回提示词"]
        self.TimeOut = cfg["等待输入时间"]
        self.TagCheck = cfg["是否启用标签限制"]
        self.PlayerTag = cfg["标签名称"]
        self.DeathMessage = cfg["返回询问消息"]
        self.ListenPacket(PacketIDS.PyRpc, self.on_pyrpc)

    def on_pyrpc(self, packet):
        """使用PyRpc监听死亡事件"""
        try:
            self._test_die(packet)
        except:
            pass
        return False

    def _test_die(self, pk: dict):
        values = pk["Value"]
        if len(values) != 3:
            return
        eventType, contents = values[0:2]
        if eventType != "ModEventS2C":
            return
        elif len(contents) != 4:
            return
        eventName, eventData = contents[2:4]
        if eventName != "OnPlayerDie":
            return
        die = eventData["die"]
        # 死亡时为True，重生时为False
        if die:
            playerUniqueID = int(eventData["pid"])
            player = self.game_ctrl.players.getPlayerByUniqueID(playerUniqueID)
            if player is None:
                return
            self.on_player_die(player)

    def on_player_die(self, player: Player):
        """当玩家死亡时调用"""
        try:
            dim, x, y, z = player.getPos()
            if self.TagCheck:
                backCmd = self.game_ctrl.sendcmd(f"/testfor @a[name={player.name},tag={self.PlayerTag}]", waitForResp=True)
                Check = backCmd.OutputMessages[0].Success
                if Check == True:
                    self.AskPlayer(player, dim, x, y, z)
            else:
                self.AskPlayer(player, dim, x, y, z)
        except:
            pass

    def AskPlayer(self, player, dim, x, y, z):
        try:
            message = utils.simple_fmt({
                "{dim}": dim,
                "{x}": round(x, 2),
                "{y}": round(y, 2),
                "{z}": round(z, 2)
            }, self.DeathMessage)
            
            reply = player.input(message, self.TimeOut)
            if reply == "y":
                player.show(self.SuccessInfo)
                if dim == 0:
                    self.game_ctrl.sendwscmd(f"/execute in overworld run tp {player.name} {x} {y} {z}")
                elif dim == 1:
                    self.game_ctrl.sendwscmd(f"/execute in nether run tp {player.name} {x} {y} {z}")
                elif dim == 2:
                    self.game_ctrl.sendwscmd(f"/execute in the_end run tp {player.name} {x} {y} {z}")
                else:
                    self.game_ctrl.sendwscmd(f"/execute in dm{dim} run tp {player.name} {x} {y} {z}")
            else:
                player.show(self.BackInfo)
        except:
            pass
    
entry = plugin_entry(DeathBack)
