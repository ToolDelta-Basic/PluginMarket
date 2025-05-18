import time
from tooldelta import Plugin, Player, fmts, plugin_entry, TYPE_CHECKING
from tooldelta.constants import PacketIDS


class Display32KShulkerBox(Plugin):
    name = "32k盒子显示"
    description = "检测32k盒子并反制"
    author = "SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.BlockActorData, self.box_get)

    def on_def(self):
        self.bas_api = self.GetPluginAPI("基本插件功能库")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.ban_sys = self.GetPluginAPI("封禁系统")
        if TYPE_CHECKING:
            from 前置_基本插件功能库 import BasicFunctionLib
            from 前置_聊天栏菜单 import ChatbarMenu
            from 封禁系统 import BanSystem
            self.bas_api: BasicFunctionLib
            self.chatbar: ChatbarMenu
            self.ban_sys: BanSystem

    def on_inject(self):
        self.chatbar.add_new_trigger(
            [".32kboxes", ".32k盒"],
            [],
            "查看最近产生的32k潜影盒",
            self.on_menu,
            True,
        )

    def box_get(self, jsonPkt):
        if "Items" in jsonPkt["NBTData"]:
            shulkerBoxPos = f"{jsonPkt['Position'][0]} {jsonPkt['Position'][1]} {jsonPkt['Position'][2]}"
            shulkerx, shulkery, shulkerz = jsonPkt["Position"][0:3]
            shulkerBoxItemList = jsonPkt["NBTData"]["Items"]
            ench32kName = []
            for i in shulkerBoxItemList:
                enchItemName = i["Name"]
                if "tag" in i:
                    if "ench" in i["tag"]:
                        for j in i["tag"]["ench"]:
                            if j["lvl"] > 10:
                                ench32kName.append(enchItemName)
            if ench32kName:
                structID = "b" + hex(round(time.time())).replace("0x", "")
                try:
                    playerNearest = self.bas_api.getTarget(
                        f"@a[x={shulkerx},y={shulkery},z={shulkerz},name=!{self.game_ctrl.bot_name},c=1]"
                    )[0]
                except Exception:
                    playerNearest = "未找到"
                self.game_ctrl.sendcmd(
                    f"/structure save {structID} {shulkerBoxPos} {shulkerBoxPos} disk"
                )
                self.game_ctrl.sendcmd(
                    f"/setblock {shulkerBoxPos} reinforced_deepslate"
                )
                self.game_ctrl.say_to(
                    "@a",
                    f"§4警报 §c发现坐标§e({shulkerBoxPos.replace(' ', ',')})§c的32k潜影盒，已自动保存并清除，最近玩家：{playerNearest}，结构方块结构名：",
                )
                self.game_ctrl.sendcmd(f'/tag "{playerNearest}" add ban')
                self.game_ctrl.say_to(
                    "@a[m=1]", "§6" + structID + "§6，给予玩家的标签是ban"
                )
                self.ban_sys.ban(
                    playerNearest, -1, "使用 32k 潜影盒"
                )
                fmts.print_war(
                    f"!!! 发现含32k的潜影盒, 坐标: {shulkerBoxPos}, 结构id: {structID}"
                )
                self.write32kBox(structID)
        return False

    def on_menu(self, player: Player, _):
        boxes = self.getAll32kBoxes()
        if boxes:
            for i in boxes:
                self.game_ctrl.sendcmd(
                    f'/execute as "{player.name}" run structure load {i} ~~~'
                )
                self.game_ctrl.sendcmd(
                    f'/execute as "{player.name}" run setblock ~~~ air 0 destroy'
                )
                self.game_ctrl.sendcmd("/structure delete " + i)
                time.sleep(0.05)
            player.show("§6检查完成.")
        else:
            player.show("§c没有检测到最近产生的32k潜影盒.")

    @staticmethod
    def getAll32kBoxes() -> list[str]:
        try:
            with open("插件数据文件/32kBoxes.txt", encoding="utf-8") as f:
                boxes = f.read().split("\n")
                f.close()
            return boxes
        except FileNotFoundError:
            return []

    @staticmethod
    def write32kBox(structID):
        with open("插件数据文件/32kBoxes.txt", "a", encoding="utf-8") as f:
            f.write("\n" + structID)
            f.close()


entry = plugin_entry(Display32KShulkerBox)
