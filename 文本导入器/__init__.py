import os
from tooldelta import Plugin, game_utils, Utils, TYPE_CHECKING, plugin_entry

from PIL import Image, ImageDraw, ImageFont

ALPHA_LIMIT = 70


class NewPlugin(Plugin):
    """文字导入器插件 - 支持在Minecraft中绘制文本"""

    name = "文字导入器"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        os.makedirs(self.format_data_path("fonts"), exist_ok=True)
        self.chatbar = None
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)

    def on_def(self):
        """插件定义阶段，获取聊天栏菜单API"""
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            self.chatbar = self.get_typecheck_plugin_api(ChatbarMenu)

    def on_inject(self):
        """插件注入阶段，添加文本绘制命令触发器"""
        self.chatbar.add_trigger(
            ["text"],
            "[文本] [xy/xz] [方块材质] [字体尺寸]",
            "绘制文本",
            self.on_put_text,
            op_only=True,
        )

    def get_first_font(self):
        """获取第一个可用的字体文件路径"""
        for file in os.listdir(self.format_data_path("fonts")):
            if file.endswith(".ttf"):
                return self.format_data_path("fonts", file)
        return None

    def on_put_text(self, player: str, args: list[str]):
        """处理文本绘制命令"""
        Utils.fill_list_index(args, ["hello world", "xz", "diamond_block", "20"])
        text, mode, texture, size_str = args
        mode_fnc = {
            "xz": self.put_text_expand_xz,
            "xy": self.put_text_expand_xy,
        }.get(mode)
        if mode_fnc is None:
            self.game_ctrl.say_to(player, "§c未知模式")
            return
        if (font := self.get_first_font()) is None:
            self.game_ctrl.say_to(player, "§c没有发现字体文件")
            return
        if (size := Utils.try_int(size_str)) is None or size not in range(5, 121):
            self.game_ctrl.say_to(player, "§c字体尺寸必须为数字(5~120)")
            return
        x, y, z = (int(i) for i in game_utils.getPosXYZ(player))
        mode_fnc(text, font, size, (x, y, z), texture)
        self.game_ctrl.say_to(player, "§a绘制完成")

    def make_text(self, text: str, font_path: str, size: int):
        """创建文本图像"""
        font_type = ImageFont.truetype(font_path, size)
        _, _, text_width, text_height = font_type.getbbox(text)
        sizex, sizey = int(text_width) + 1, int(text_height) + 1
        cache_img = Image.new("RGBA", (sizex, sizey), (0, 0, 0, 0))
        cache_paint = ImageDraw.Draw(cache_img)
        cache_paint.text((0, 0), text, (255, 255, 255, 255), font_type, spacing=0)
        cache_img.save(
            self.format_data_path("fonts", "cache.png")
        )
        return cache_img, sizex, sizey

    def handle_pixel(
        self, r: int, g: int, b: int, a: int, x: int, y: int, z: int, texture: str):
        """处理单个像素的绘制"""
        if a > ALPHA_LIMIT:
            self.game_ctrl.sendwocmd(
                f"setblock {x} {y} {z} {texture}"
            )

    def put_text_expand_xz(
        self,
        text: str, font_path: str, size: int, pos: tuple[int, int, int], texture: str):
        """在xz平面上绘制文本"""
        cache_img, sizex, sizey = self.make_text(text, font_path, size)
        x, y, z = pos
        chunk_x, chunk_z = x, z
        while chunk_x < x + sizex:
            self.game_ctrl.sendcmd_with_resp(
                f"tp {self.game_ctrl.bot_name} {chunk_x} {y} {z}"
            )
            chunk_z = z
            while chunk_z < z + sizey:
                self.game_ctrl.sendcmd_with_resp(
                    f"tp {self.game_ctrl.bot_name} {chunk_x} {y} {chunk_z}"
                )
                for x1 in range(chunk_x, chunk_x + 16):
                    for z1 in range(chunk_z, chunk_z + 16):
                        posx, posz = x1 - x, z1 - z
                        if posx < sizex and posz < sizey:
                            r, g, b, a = cache_img.getpixel((posx, posz))
                            self.handle_pixel(r, g, b, a, x1, y, z1, texture)
                chunk_z += 16
            chunk_x += 16

    def put_text_expand_xy(
        self,
        text: str, font_path: str, size: int, pos: tuple[int, int, int], texture: str):
        """在xy平面上绘制文本"""
        cache_img, sizex, sizey = self.make_text(text, font_path, size)
        x, y, z = pos
        chunk_x = x
        while chunk_x < x + sizex:
            self.game_ctrl.sendcmd_with_resp(
                f"tp {self.game_ctrl.bot_name} {chunk_x} {y} {z}"
            )
            for x1 in range(chunk_x, chunk_x + 16):
                for y1 in range(y, y + sizey):
                    posx = x1 - x
                    posy = y1 - y
                    if posx < sizex:
                        r, g, b, a = cache_img.getpixel(
                            (posx, sizey - posy - 1)
                        )
                        self.handle_pixel(r, g, b, a, x1, y1, z, texture)
            chunk_x += 16


entry = plugin_entry(NewPlugin)

