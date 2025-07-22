from tooldelta import Plugin, plugin_entry, Player, Chat, FrameExit, cfg, game_utils, utils, Config, fmts, TYPE_CHECKING
from tooldelta.constants import PacketIDS
class DeathBack(Plugin):
    name = "死亡点返回"
    author = "果_k"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_DEFAULT = {
            "取消返回": "§c§l已自动取消返回",
            "等待输入时间": 20,
            "是否启用标签限制": False,
            "标签名称": "backdeath",
        }
        CONFIG_STD = {
            "取消返回": str,
            "等待输入时间": Config.NNInt,
            "是否启用标签限制": bool,
            "标签名称": str,
        }
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.BackInfo = cfg["取消返回"]
        self.TimeOut = cfg["等待输入时间"]
        self.TagCheck = cfg["是否启用标签限制"]
        self.PlayerTag= cfg["标签名称"]
        self.ListenPacket(PacketIDS.Text, self.TextDeath)

    def TextDeath(self,packet):
        Message = packet['Message']
        if isinstance(Message, str) and "death" in Message.lower(): #筛选触发条件
            self.GetPos(packet['Parameters'][0])

    def GetPos(self,playername):
        players = self.frame.get_players()
        player = players.getPlayerByName(playername)
        if not player:
            return
        dim, x, y, z = player.getPos()
        if self.TagCheck:    #标签筛选玩家
            backCmd = self.game_ctrl.sendcmd(f"/testfor @a[name={player.name},tag={self.PlayerTag}]",waitForResp=True) 
            Check = backCmd.OutputMessages[0].Success
            if Check == True:
                self.AskPlayer(player,dim,x,y,z)
            else:
                return
        else:
            self.AskPlayer(player,dim,x,y,z)
  
    def AskPlayer(self,player,dim,x,y,z):
        reply = player.input(f"§a§l你死于 {dim} 维度的 {x} {y} {z} 是否返回？§b输入y同意 输入n拒绝",self.TimeOut)
        if reply == "y":
            player.show("返回")
            if dim == 0:  #不同维度的判断
                self.game_ctrl.sendwscmd(f"/execute in overworld run tp {player.name} {x} {y} {z}")
            elif dim == 1:
                self.game_ctrl.sendwscmd(f"/execute in nether run tp {player.name} {x} {y} {z}")
            elif dim == 2:
                self.game_ctrl.sendwscmd(f"/execute in the_end run tp {player.name} {x} {y} {z}")
        else:
            player.show(self.BackInfo)
    
entry = plugin_entry(DeathBack)
