import base64
from tooldelta import Plugin, Print, plugin_entry
from tooldelta.constants import PacketIDS

cl = [
        (0, 0, 0),  # 0
        (0, 0, 140),  # 1
        (0, 140, 0),  # 2
        (0, 140, 140),  # 3
        (140, 0, 0),  # 4
        (140, 0, 0),  # 5
        (255, 140, 0),  # 6
        (140, 140, 140),  # 7
        (75, 75, 75),  # 8
        (75, 75, 255),  # 9
        # chr
        (100, 255, 100),  # a
        (100, 255, 255),  # b
        (255, 100, 100),  # c
        (255, 150, 255),  # d
        (255, 255, 100),  # e
        (255, 255, 255),  # f
        (221, 214, 5),  # g
    ]

class GetSkin(Plugin):
    author = "SuperScript"
    version = (0, 0, 5)
    name = "获取全服玩家皮肤"

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        self.ListenPreload(self.on_def)
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_pkt_skin)

    def on_def(self):
        global PILImage
        pip = self.GetPluginAPI("pip")
        if 0:
            from pip模块支持 import PipSupport
            pip = self.get_typecheck_plugin_api(PipSupport)
        pip.require({"pillow": "PIL"})
        import PIL.Image as PILImage

    def on_pkt_skin(self, pkt):
        pls = pkt["Entries"]
        for player in pls:
            name = player["Username"]
            if player["Skin"]["SkinData"]:
                skindata_raw = player["Skin"]["SkinData"]
                if isinstance(skindata_raw, str):
                    bskindata = base64.b64decode(player["Skin"]["SkinData"])
                else:
                    bskindata = skindata_raw
                siz = (
                    player["Skin"]["SkinImageWidth"],
                    player["Skin"]["SkinImageHeight"],
                )
                img = PILImage.new("RGBA", siz)
                for xp in range(siz[0]):
                    for yp in range(siz[1]):
                        rs, gs, bs, alp = bskindata[
                            xp * 4 + yp * siz[0] * 4 : xp * 4 + yp * siz[0] * 4 + 4
                        ]
                        # 绘制像素点
                        img.putpixel((xp, yp), (rs, gs, bs, alp))
                img.save(f"{self.data_path}/{name}.png", bitmap_format="png")
                Print.print_with_info(
                    f"皮肤信息: 宽={siz[0]} 高={siz[1]} 使用者={name}", info=" Skin "
                )
                img_x16 = img.crop((8, 8, 16, 16))
                img_txt = ""
                for y in range(8):
                    for x in range(8):
                        r, g, b, a = img_x16.getpixel((x, y))
                        img_txt += "§" + self.f_color(r, g, b) + "■"
                    img_txt += "\n"
        return False

    def f_color(self, r1, g1, b1):
        weights = []
        for i, (r, g, b) in enumerate(cl):
            weights.append(((r1 - r) ** 2 + (g1 - g) ** 2 + (b1 - b) ** 2, i))
        weights.sort(key=lambda x: x[0])
        res = weights[0][1]
        return "0123456789abcdefg"[res]


entry = plugin_entry(GetSkin, "SkinGetter")
