from tooldelta import Player, Plugin, ToolDelta, TYPE_CHECKING, plugin_entry
from tooldelta.game_utils import getPosXYZ


class ChunkShow(Plugin):
    name = "区块显示器"
    author = "SnowLotus"
    version = (0, 0, 3)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.chatbar_menu = self.GetPluginAPI("聊天栏菜单")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu

            self.chatbar_menu: ChatbarMenu

    def on_inject(self):
        self.chatbar_menu.add_new_trigger(
            ["显示区块", "区块范围"],
            [],
            "显示当前所在区块的起始点和终止点",
            self.show_chunk,
        )
        self.chatbar_menu.add_new_trigger(
            ["地图画起点"], [], "显示当前可用作地图画区域的起点", self.get_map_chunk
        )

    def show_chunk(self, player: Player, _):
        x, _, z = getPosXYZ(player.name)
        chunk_start_x = int(x // 8) * 8
        chunk_start_z = int(z // 8) * 8
        player.show(f"§7§l[§f>] §r§f当前区块起始点: ({chunk_start_x}, {chunk_start_z})")
        player.show(
            f"§7§l[§f>] §r§f当前区块终止点: ({chunk_start_x + 7}, {chunk_start_z + 7})",
        )

    def get_map_chunk(self, player: Player, _):
        x, y, z = getPosXYZ(player.name)
        chunk_start_x = int(x // 128) * 128
        chunk_start_z = int(z // 128) * 128
        player.show(
            f"§7§l[§f>] §r§f当前地图画区块起始点: ({chunk_start_x}, {chunk_start_z})",
        )

entry = plugin_entry(ChunkShow)