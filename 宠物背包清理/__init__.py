from tooldelta import Plugin, Player, plugin_entry, TYPE_CHECKING


class NewPlugin(Plugin):
    name = "宠物背包清理"
    author = "猫七街"
    version = (0, 1, 0)

    def __init__(self, frame):
        super().__init__(frame)

    def on_preload(self):
        self.cb2bot = self.GetPluginAPI("Cb2Bot通信")
        if TYPE_CHECKING:
            from ..前置_Cb2Bot通信 import TellrawCb2Bot

            self.cb2bot: TellrawCb2Bot
        self.cb2bot.regist_message_cb("clearbag_single", self.on_clear_single)
        self.cb2bot.regist_message_cb("clearbag_multiple", self.on_clear_multiple)
            
    def on_clear_single(self, args: list[str]):
        if len(args) != 1:
            self.print_err("清理宠物背包的命令参数错误")
            return
        player = self.game_ctrl.players.getPlayerByName(args[0])
        if player is None:
            self.print_err(f"玩家不存在: {args[0]}")
            return
        self.clear_pet_bag(player)
        
    def on_clear_multiple(self, _):
        for player in self.game_ctrl.players:
            self.clear_pet_bag(player)

    def clear_pet_bag(self, player: Player):
        self.game_ctrl.sendwscmd(f"/a {player.name}")


entry = plugin_entry(NewPlugin)
