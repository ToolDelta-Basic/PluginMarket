from tooldelta import Plugin, ToolDelta, plugin_entry


class ClearEnderChest(Plugin):
    name = "清空全部玩家末影箱"
    author = "wling"
    version = (0, 0, 6)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        self.GetPluginAPI("聊天栏菜单").add_trigger(
            ["encl", "清末影箱"],
            "[玩家名中的关键词]",
            "清空玩家末影箱",
            self.on_menu,
            lambda x: x == 1,
            True,
        )

    def on_menu(self, playername: str, args: list[str]):
        clearWho = args[0]
        for i in self.game_ctrl.allplayers:
            if clearWho in i:
                for j in range(0, 27):
                    self.game_ctrl.sendwocmd(
                        f"/replaceitem entity {i} slot.enderchest {j} air"
                    )
                self.game_ctrl.say_to(playername, text="§l§a清空末影箱  成功")
                return

        self.game_ctrl.say_to(playername, "§l§cERROR§r §c目标玩家不存在！")


entry = plugin_entry(ClearEnderChest)
