from tooldelta import Plugin, ToolDelta, plugin_entry


class 全服喇叭(Plugin):
    name = "全服喇叭"
    author = "wling"
    version = (0, 0, 5)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        self.GetPluginAPI("聊天栏菜单").add_trigger(
            ["喇叭"], "[消息]", "管理广播消息", self.onLaba, op_only=True
        )

    def onLaba(self, playername: str, args: list[str]):
        msg = " ".join(args)
        player = self.frame.get_players().getPlayerByName(playername)
        if player is None:
            raise ValueError("玩家不存在")
        if msg.startswith(".喇叭"):
            if player.is_op():
                player.show(
                    f"§l§b{player.name} §r§7>>> §l§b{msg.replace('.喇叭', '').strip()}",
                )
                self.game_ctrl.player_title("@a", f"§l§b{player.name}§f:")
                self.game_ctrl.player_subtitle(
                    "@a", f"§l§e{msg.replace('.喇叭', '').strip()}"
                )
                self.game_ctrl.sendwocmd(
                    "execute as @a run playsound firework.launch @s ~~~ 10"
                )


entry = plugin_entry(全服喇叭)
