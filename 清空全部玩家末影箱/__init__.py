from tooldelta import Plugin, Player, ToolDelta, plugin_entry


class ClearEnderChest(Plugin):
    name = "清空全部玩家末影箱"
    author = "wling"
    version = (0, 0, 6)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        self.GetPluginAPI("聊天栏菜单").add_new_trigger(
            ["encl", "清末影箱"],
            [("玩家名中的关键词", str, None)],
            "清空玩家末影箱",
            self.on_menu,
            True,
        )

    def on_menu(self, player: Player, args: list[str]):
        clearWho = args[0]
        for i in self.game_ctrl.allplayers:
            if clearWho in i:
                for j in range(0, 27):
                    self.game_ctrl.sendwocmd(
                        f"/replaceitem entity {i} slot.enderchest {j} air"
                    )
                player.show(f"§l§a清空 {i} 的末影箱：成功")
                return

        player.show("§l§cERROR§r §c目标玩家不存在！")


entry = plugin_entry(ClearEnderChest)
