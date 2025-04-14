from tooldelta import Player, Plugin, ToolDelta, plugin_entry


class 全服喇叭(Plugin):
    name = "全服喇叭"
    author = "wling"
    version = (0, 0, 6)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        # TODO: 目前无法在消息里使用空格
        self.GetPluginAPI("聊天栏菜单").add_new_trigger(
            ["喇叭"], [("消息", str, None)], "管理广播消息", self.onLaba, op_only=True
        )

    def onLaba(self, player: Player, args: tuple):
        msg = " ".join(args)
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
        else:
            player.show("§c只有管理员可使用全服喇叭")


entry = plugin_entry(全服喇叭)
