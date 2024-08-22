from tooldelta import plugins, Plugin
from tooldelta.game_utils import getPosXYZ


@plugins.add_plugin
class ChunkShow(Plugin):
    name = "区块显示器"
    author = "SnowLotus"
    version = (0, 0, 2)

    def on_def(self):
        self.chatbar_menu = plugins.get_plugin_api("聊天栏菜单")

    def on_inject(self):
        self.chatbar_menu.add_trigger(
            ["显示区块", "区块范围"],
            None,
            "显示当前所在区块的起始点和终止点",
            self.show_chunk,
        )
        self.chatbar_menu.add_trigger(
            ["地图画起点"], None, "显示当前可用作地图画区域的起点", self.get_map_chunk
        )

    def show_chunk(self, player: str, _):
        x, y, z = getPosXYZ(player)
        chunk_start_x = int(x // 8) * 8
        chunk_start_z = int(z // 8) * 8
        self.game_ctrl.say_to(
            player, f"§7§l[§f>] §r§f当前区块起始点: ({chunk_start_x}, {chunk_start_z})"
        )
        self.game_ctrl.say_to(
            player,
            f"§7§l[§f>] §r§f当前区块终止点: ({chunk_start_x + 7}, {chunk_start_z + 7})",
        )

    def get_map_chunk(self, player: str, _):
        x, y, z = getPosXYZ(player)
        chunk_start_x = int(x // 128) * 128
        chunk_start_z = int(z // 128) * 128
        self.game_ctrl.say_to(
            player,
            f"§7§l[§f>] §r§f当前地图画区块起始点: ({chunk_start_x}, {chunk_start_z})",
        )
