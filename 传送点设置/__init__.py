import os
from tooldelta import Plugin, Player, utils, cfg, TYPE_CHECKING, plugin_entry

DIMENSIONS = ["overworld", "nether", "the_end", *(f"dim{i}" for i in range(3, 21))]
DIMENSIONS_ZHCN = ["主世界", "下界", "末地", *(f"DIM-{i}" for i in range(3, 21))]
type1 = type
function = print


class HomePointSet(Plugin):
    name = "传送点设置"
    author = "SuperScript"
    version = (0, 0, 4)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG = {
            "最多可设置的传送点": 10,
            "聊天栏菜单内配置": {
                "设置传送点触发词": ["sethome", "保存"],
                "删除传送点触发词": ["delhome", "删除"],
                "传送点列表触发词": ["listhome", "传送点列表"],
                "传送到传送点触发词": ["home", "回"],
            },
            "雪球菜单内配置": {
                "是否嵌入雪球菜单": True,
                "菜单内显示名": "传送点",
            },
        }
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CONFIG), CONFIG, self.version
        )
        os.makedirs(self.format_data_path("传送点列表"), exist_ok=True)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        self.funclib = self.GetPluginAPI("基本插件功能库")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.snowmenu = self.GetPluginAPI("雪球菜单v3")
        if TYPE_CHECKING:
            from 前置_基本插件功能库 import BasicFunctionLib
            from 前置_聊天栏菜单 import ChatbarMenu
            from 雪球菜单v3 import SnowMenuV3
            from 前置_玩家XUID获取 import XUIDGetter

            self.funclib: BasicFunctionLib
            self.chatbar: ChatbarMenu
            self.snowmenu: SnowMenuV3
            self.xuidm: XUIDGetter

    def on_inject(self):
        self.chatbar.add_new_trigger(
            self.cfg["聊天栏菜单内配置"]["设置传送点触发词"],
            [("传送点名", str, None)],
            "设置传送点",
            self.on_set_home,
        )
        self.chatbar.add_new_trigger(
            self.cfg["聊天栏菜单内配置"]["删除传送点触发词"],
            [("传送点名", str, "")],
            "删除传送点",
            self.on_del_home,
        )
        self.chatbar.add_new_trigger(
            self.cfg["聊天栏菜单内配置"]["传送点列表触发词"],
            [],
            "传送点列表",
            self.on_list_home,
        )
        self.chatbar.add_new_trigger(
            self.cfg["聊天栏菜单内配置"]["传送到传送点触发词"],
            [],
            "前往传送点",
            self.on_home,
        )

    def on_set_home(self, player: Player, args):
        homes = self.read_homes(player)
        if len(homes) >= self.cfg["最多可设置的传送点"]:
            player.show("§7[§cx§7] 传送点数量已达到上限")
            return
        resp = args[0]
        if len(resp) > 20 or resp == "***":
            player.show("§7[§cx§7] 不合规的传送点名， 取消传送点设置"
            )
            return
        if resp in homes:
            player.show("§7[§cx§7] 已有重命名传送点")
            return
        dim, x,y,z = player.getPos()
        homes[resp] = [
            dim, x, y, z
        ]
        self.write_homes(player, homes)
        player.show(f"§7[§a√§7] §a传送点 {resp} 设置成功")

    def on_list_home(self, player: Player, _):
        homes = self.read_homes(player)
        if homes == {}:
            player.show("§7[§6!§7] §6你还没有设置任何一个传送点")
            return
        player.show("§a当前已设置的传送点：")
        for name, pos in homes.items():
            dim, x, y, z = pos
            dim_zhcn = DIMENSIONS_ZHCN[int(dim)]
            player.show(f" §7- §f{name} §6（{dim_zhcn} {x:.1f}， {y:.1f}， {z:.1f}）"
            )

    def on_del_home(self, player: Player, args: tuple):
        homes = self.read_homes(player)
        if args[0] != "":
            dhome = args[0]
            if dhome not in homes.keys():
                player.show("§7[§cx§7] §c该传送点不存在")
                return
        else:
            hlist = list(homes.keys())
            dhome = self.funclib.list_select(
                player, hlist, "§6选择一个传送点进行删除：", " §f%d §7- §6%s"
            )
            if dhome is None:
                return
        del homes[dhome]
        self.write_homes(player, homes)
        player.show(f"§7[§a√§7] §a传送点 {dhome} 已删除")

    def on_home(self, player: Player, args: tuple):
        homes = self.read_homes(player)
        # if args[0] != "":
        #     goto_home = args[0]
        #     if goto_home not in homes.keys():
        #         player.show("§7[§cx§7] §c该传送点不存在")
        #         return
        # else:
        hlist = list(homes.keys())
        goto_home = self.funclib.list_select(
            player, hlist, "§6选择一个传送点：", " §f%d §7- §6%s"
        )
        if goto_home is None:
            return
        dim, x, y, z = homes[goto_home]
        dim_id = DIMENSIONS[int(dim)]
        self.game_ctrl.sendwocmd(
            f"execute as {player.safe_name} at @s in {dim_id} run tp {x} {y} {z}"
        )
        player.show(f"§7[§a√§7] §a已传送到 {goto_home}")

    def read_homes(self, player: Player) -> dict[str, list[float]]:
        return utils.tempjson.load_and_read(self.data_path / "传送点列表" / player.xuid, False, default={})

    def write_homes(self, player: Player, content: dict[str, list[float]]):
        utils.tempjson.load_and_write(self.data_path / "传送点列表" / player.xuid, content, False)


entry = plugin_entry(HomePointSet)
