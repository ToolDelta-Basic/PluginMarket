from tooldelta import Frame, plugins, Plugin
from tooldelta.game_utils import getTarget

import time

@plugins.add_plugin
class WorldEdit(Plugin):
    author = "SuperScript"
    version = (0, 0, 6)
    name = "简易建造"
    description = "以更方便的方法在租赁服进行创作, 输入.we help查看说明"

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()

    def on_def(self):
        self.add_trigger = plugins.get_plugin_api("聊天栏菜单").add_trigger
        from 前置_聊天栏菜单 import ChatbarMenu
        self.add_trigger = plugins.instant_plugin_api(ChatbarMenu).add_trigger
        self.getX = None
        self.getY = None
        self.getZ = None

    def on_inject(self):
        self.add_trigger(["we help"], None, "查看 简易建造插件 的使用说明", self.description_show)

    def description_show(self, who: str, _):
        self.game_ctrl.say_to(
            who,
            "简易建造，帮助你更快速地在租赁服实现快速填充等操作; 使用插件管理器的手册查看功能以查看使用说明",
        )

    @plugins.add_packet_listener(56)
    def we_pkt56(self, jsonPkt: dict):
        if "NBTData" in jsonPkt and "id" in jsonPkt["NBTData"]:
            if (
                jsonPkt["NBTData"]["id"] == "Sign"
                and jsonPkt["NBTData"]["Text"] == "We start"
            ):
                placeX, placeY, placeZ, text = (
                    jsonPkt["NBTData"]["x"],
                    jsonPkt["NBTData"]["y"],
                    jsonPkt["NBTData"]["z"],
                    jsonPkt["NBTData"]["Text"],
                )
                try:
                    signPlayerName = getTarget(
                        f"@a[x={placeX}, y={placeY}, z={placeZ}, c=1, r=8]"
                    )[0]
                    if getTarget(
                        f"@a[x={placeX}, y={placeY}, z={placeZ}, r=8, m=!1]"
                    ) != []:
                        self.game_ctrl.say_to(signPlayerName, "无法使用，请确保告示牌附近8格内无非创造模式玩家")
                except Exception as err:
                    signPlayerName = ""
                    self.game_ctrl.say_to("@a", f"§c告示牌简易建造 (x={placeX}, y={placeY}, z={placeZ}) 失败: {err}")
                self.getX = int(jsonPkt["NBTData"]["x"])
                self.getY = int(jsonPkt["NBTData"]["y"])
                self.getZ = int(jsonPkt["NBTData"]["z"])
                if signPlayerName in getTarget("@a[m=1]"):
                    self.game_ctrl.sendcmd(
                        f"/setblock {self.getX} {self.getY} {self.getZ} air 0 destroy"
                    )
                    self.game_ctrl.say_to(
                        signPlayerName,
                        f"§a设置第一点: {self.getX}, {self.getY}, {self.getZ}",
                    )

            elif (
                jsonPkt["NBTData"]["id"] == "Sign"
                and jsonPkt["NBTData"]["Text"].startswith("We fill ")
                and len(jsonPkt["NBTData"]["Text"]) > 8
            ):
                placeX, placeY, placeZ, text = (
                    jsonPkt["NBTData"]["x"],
                    jsonPkt["NBTData"]["y"],
                    jsonPkt["NBTData"]["z"],
                    jsonPkt["NBTData"]["Text"],
                )
                try:
                    signPlayerName = getTarget(
                        f"@a[x={placeX}, y={placeY}, z={placeZ}, c=1, r=10]"
                    )[0]
                    getXend = int(jsonPkt["NBTData"]["x"])
                    getYend = int(jsonPkt["NBTData"]["y"])
                    getZend = int(jsonPkt["NBTData"]["z"])
                except Exception as err:
                    signPlayerName = ""
                    self.game_ctrl.say_to("@a", f"§cERROR：目标选择器报错 §6{(placeX, placeY, placeZ)}")
                blockData = text[8:].replace("陶瓦", "stained_hardened_clay")
                try:
                    if signPlayerName in getTarget("@a[m=1]"):
                        if not self.getX:
                            raise AssertionError
                        self.game_ctrl.sendcmd(
                            f"/fill {self.getX} {self.getY} {self.getZ} {getXend} {getYend} {getZend} {blockData}"
                        )
                        self.game_ctrl.say_to(
                            signPlayerName, "§c§lWorldEdit§r>> §a填充完成"
                        )
                    else:
                        self.game_ctrl.say_to(
                            signPlayerName, "§c§lWorldEdit§r>> §c没有权限"
                        )
                except AssertionError:
                    self.game_ctrl.say_to(
                        signPlayerName, "§c§lWorldEdit§r>> §c没有设置起点或终点"
                    )
            elif (
                jsonPkt["NBTData"]["id"] == "Sign"
                and jsonPkt["NBTData"]["Text"] == "We cn"
            ):
                try:
                    if not self.getX:
                        raise AssertionError("还未获取起点坐标")
                    signPlayerName = getTarget(
                        f"@a[x={jsonPkt['NBTData']['x']}, y={jsonPkt['NBTData']['y']}, z={jsonPkt['NBTData']['z']}, c=1, r=10]"
                    )[0]
                    if signPlayerName in getTarget("@a[m=1]"):
                        self.frame.createThread(
                            self.fillwith,
                            (
                                self.getX,
                                self.getY,
                                self.getZ,
                                int(jsonPkt["NBTData"]["x"]),
                                int(jsonPkt["NBTData"]["y"]),
                                int(jsonPkt["NBTData"]["z"]),
                            ),
                        )
                except Exception as err:
                    self.game_ctrl.say_to("@a", f"§c无法执行方块批量复制操作， 因为 {err} ({err.__class__.__name__})")
        return False

    def fillwith(self, sx, sy, sz, dx, dy, dz):
        p2n = lambda n: 1 if n >= 0 else -1
        fx = p2n(dx - sx)
        fy = p2n(dy - sy)
        fz = p2n(dz - sz)
        for x in range(sx, dx + fx, fx):
            for y in range(sy, dy + fy, fy):
                for z in range(sz, dz + fz, fz):
                    self.game_ctrl.sendwocmd(
                        f"/clone {sx} {sy} {sz} {sx} {sy} {sz} {x} {y} {z}"
                    )
                    time.sleep(0.01)
