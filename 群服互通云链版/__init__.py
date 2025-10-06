import json
import websocket
import time
import re
import os
import base64
import tempfile
from typing import Any
from collections.abc import Callable
from tooldelta import (
    Plugin,
    cfg,
    utils,
    fmts,
    Chat,
    Player,
    plugin_entry,
    InternalBroadcast,
)

try:
    from tooldelta.utils.mc_translator import translate
except ImportError:
    translate = None


EASTER_EGG_QQIDS = {2528622340: ("SuperScript", "Super")}


class QQMsgTrigger:
    def __init__(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[[int, list[str]], None],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        self.triggers = triggers
        self.argument_hint = argument_hint
        self.usage = usage
        self.func = func
        self.args_pd = args_pd
        self.op_only = op_only

    def match(self, msg: str):
        for trigger in self.triggers:
            if msg.startswith(trigger):
                return trigger
        return None


def remove_cq_code(content: str):
    cq_start = content.find("[CQ:")
    while cq_start != -1:
        cq_end = content.find("]", cq_start) + 1
        content = content[:cq_start] + content[cq_end:]
        cq_start = content.find("[CQ:")
    return content


def remove_color(content: str):
    return re.compile(r"§(.)").sub("", content)


CQ_IMAGE_RULE = re.compile(r"\[CQ:image,([^\]])*\]")
CQ_VIDEO_RULE = re.compile(r"\[CQ:video,[^\]]*\]")
CQ_FILE_RULE = re.compile(r"\[CQ:file,[^\]]*\]")
CQ_AT_RULE = re.compile(r"\[CQ:at,[^\]]*\]")
CQ_REPLY_RULE = re.compile(r"\[CQ:reply,[^\]]*\]")
CQ_FACE_RULE = re.compile(r"\[CQ:face,[^\]]*\]")


def replace_cq(content: str):
    for i, j in (
        (CQ_IMAGE_RULE, "[图片]"),
        (CQ_FILE_RULE, "[文件]"),
        (CQ_VIDEO_RULE, "[视频]"),
        (CQ_AT_RULE, "[@]"),
        (CQ_REPLY_RULE, "[回复]"),
        (CQ_FACE_RULE, "[表情]"),
    ):
        content = i.sub(j, content)
    return content


class QQLinker(Plugin):
    """QQ群与 Minecraft 服务器互通插件."""
    
    version = (0, 1, 2)
    name = "云链群服互通"
    author = "大庆油田"
    description = "提供简单的群服互通"
    QQMsgTrigger = QQMsgTrigger
    
    # 背包UI常量 (inventory.png 176x166)
    INVENTORY_WIDTH = 176
    INVENTORY_HEIGHT = 166
    SLOT_SIZE = 16  # 每个格子的尺寸
    SLOT_STEP = 18  # 格子间的步进距离
    GRID_START_X = 8  # 背包网格起始 X 坐标
    MAIN_INVENTORY_START_Y = 84  # 主背包起始 Y 坐标
    HOTBAR_START_Y = 142  # 快捷栏起始 Y 坐标
    MISSING_TEXTURE_COLOR = (80, 80, 80, 180)  # 缺失材质的灰色背景

    def __init__(self, f):
        super().__init__(f)
        self.ws = None
        self.reloaded = False
        self.triggers: list[QQMsgTrigger] = []
        self.item_name_map: dict[str, str] = {}
        self.enchantment_name_map: dict[int, str] = {}
        self.pillow_available = False
        self.Image = None
        self.ImageDraw = None
        self.ImageFont = None
        self._load_item_name_map()
        self._load_enchantment_name_map()
        CFG_DEFAULT = {
            "云链设置": {"地址": "ws://127.0.0.1:3001", "校验码": None},
            "消息转发设置": {
                "链接的群聊": 194838530,
                "游戏到群": {
                    "是否启用": False,
                    "转发格式": "<[玩家名]> [消息]",
                    "仅转发以下符号开头的消息(列表为空则全部转发)": ["#"],
                    "屏蔽以下字符串开头的消息": [".", "。"],
                    "转发玩家进退提示": True,
                },
                "群到游戏": {
                    "是否启用": True,
                    "转发格式": "群 <[昵称]> [消息]",
                    "屏蔽的QQ号": [2398282073],
                    "替换花里胡哨的昵称": True,
                    "替换花里胡哨的消息": True,
                },
            },
            "指令设置": {
                "可以对游戏执行指令的QQ号名单": [2528622340, 2483724640],
                "是否允许查看玩家列表": True,
            },
        }
        cfg_std = cfg.auto_to_std(CFG_DEFAULT)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg_std, CFG_DEFAULT, self.version
        )
        self.enable_playerlist = self.cfg["指令设置"]["是否允许查看玩家列表"]
        self.linked_group = self.cfg["消息转发设置"]["链接的群聊"]

        msg_transfer_settings = self.cfg["消息转发设置"]
        settings_g2q = msg_transfer_settings["游戏到群"]
        settings_q2g = msg_transfer_settings["群到游戏"]

        self.enable_game_2_group = settings_g2q["是否启用"]
        self.enable_group_2_game = settings_q2g["是否启用"]
        self.replace_colorful_name = settings_q2g["替换花里胡哨的昵称"]
        self.replace_colorful_msg = settings_q2g["替换花里胡哨的消息"]

        self.enable_player_join_leave = settings_g2q["转发玩家进退提示"]
        self.block_qqids = settings_g2q
        self.game2qq_trans_chars = settings_g2q[
            "仅转发以下符号开头的消息(列表为空则全部转发)"
        ]
        self.game2qq_block_prefixs = settings_g2q["屏蔽以下字符串开头的消息"]
        self.can_exec_cmd = self.cfg["指令设置"]["可以对游戏执行指令的QQ号名单"]
        self.waitmsg_cbs = {}
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)
        self.plugin = []
        self.available = False
        self._manual_launch = False
        self._manual_launch_port = -1

    def _load_item_name_map(self):
        """加载物品ID到中文名的映射表"""
        item_file_path = os.path.join(os.path.dirname(__file__), "item.txt")
        try:
            with open(item_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    # 格式: item_id: 中文名
                    item_id, cn_name = line.split(":", 1)
                    self.item_name_map[item_id.strip()] = cn_name.strip()
        except FileNotFoundError:
            self.print("§c警告: 未找到 item.txt 映射文件")
        except Exception as e:
            self.print(f"§c加载物品名称映射表时出错: {e}")

    def _load_enchantment_name_map(self):
        """加载附魔ID到中文名的映射表"""
        ench_file_path = os.path.join(os.path.dirname(__file__), "enchantment.txt")
        try:
            with open(ench_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    # 格式: enchantment_id: 中文名
                    ench_id_str, cn_name = line.split(":", 1)
                    try:
                        ench_id = int(ench_id_str.strip())
                        self.enchantment_name_map[ench_id] = cn_name.strip()
                    except ValueError:
                        continue
        except FileNotFoundError:
            self.print("§c警告: 未找到 enchantment.txt 映射文件")
        except Exception as e:
            self.print(f"§c加载附魔名称映射表时出错: {e}")

    @staticmethod
    def _get_full_item_id(slot) -> str:
        """获取物品完整ID（命名空间:id）"""
        item_id = getattr(slot, "id", "")
        namespace = getattr(slot, "namespace", "")
        if ":" in item_id:
            return item_id
        if namespace and not namespace.endswith(":"):
            namespace += ":"
        return f"{namespace}{item_id}" if (namespace or item_id) else ""

    def _localize_item(self, slot) -> str:
        """获取物品的中文名称"""
        full_id = self._get_full_item_id(slot)
        if not full_id:
            return ""
        # 移除命名空间前缀（如 minecraft:）
        item_id = full_id.split(":", 1)[1] if ":" in full_id else full_id
        # 查找映射表
        if item_id in self.item_name_map:
            return self.item_name_map[item_id]
        # 如果没找到，尝试用translate回退（仅当translate可用时）
        if translate and item_id:
            for prefix in ("item", "tile"):
                key = f"{prefix}.{item_id}.name"
                zh = translate(key)
                if zh != key:
                    return zh
        # 都失败了，返回原始ID
        return full_id

    def _generate_text_inventory(self, slots: list) -> str:
        """生成背包的文本版本，按MC布局分开快捷栏和主背包"""
        def format_slot(idx: int, slot) -> str:
            """格式化单个slot信息"""
            name = self._localize_item(slot)
            aux = getattr(slot, "aux", 0)
            cnt = getattr(slot, "stackSize", 0)
            ench = getattr(slot, "enchantments", [])
            
            if ench:
                ench_names = []
                for e in ench:
                    ench_name = getattr(e, 'name', None)
                    if ench_name:
                        ench_names.append(ench_name)
                    else:
                        ench_id = getattr(e, 'type', None)
                        if ench_id is not None and ench_id in self.enchantment_name_map:
                            ench_names.append(self.enchantment_name_map[ench_id])
                if ench_names:
                    return f"[{idx}] {name} x{cnt} ({', '.join(ench_names)})"
                else:
                    return f"[{idx}] {name} x{cnt}"
            else:
                if aux != 0:
                    return f"[{idx}] {name} x{cnt} (数据:{aux})"
                else:
                    return f"[{idx}] {name} x{cnt}"
        
        lines: list[str] = []
        
        # 快捷栏 (slots 0-8)
        hotbar_items = []
        for idx in range(9):
            if idx < len(slots) and slots[idx] is not None:
                hotbar_items.append(format_slot(idx, slots[idx]))
        
        if hotbar_items:
            lines.append("▶ 快捷栏:")
            lines.extend(hotbar_items)
        
        # 主背包 (slots 9-35)
        main_items = []
        for idx in range(9, 36):
            if idx < len(slots) and slots[idx] is not None:
                main_items.append(format_slot(idx, slots[idx]))
        
        if main_items:
            if hotbar_items:  # 如果有快捷栏，加个空行
                lines.append("")
            lines.append("▶ 主背包:")
            lines.extend(main_items)
        
        return "\n".join(lines) if lines else "背包为空"

    def _get_slot_position(self, slot_index: int) -> tuple[int, int] | None:
        """根据slot索引计算在背包UI中的像素坐标.
        
        Args:
            slot_index: 背包格子索引 (0-8快捷栏, 9-35主背包)
            
        Returns:
            (x, y) 坐标或None如果索引超出范围
        """
        if 0 <= slot_index <= 8:
            # 快捷栏：横向排列
            col = slot_index
            x = self.GRID_START_X + col * self.SLOT_STEP
            y = self.HOTBAR_START_Y
            return (x, y)
        
        if 9 <= slot_index <= 35:
            # 主背包：9-17第一行，18-26第二行，27-35第三行
            slot_in_main = slot_index - 9
            row = slot_in_main // 9
            col = slot_in_main % 9
            x = self.GRID_START_X + col * self.SLOT_STEP
            y = self.MAIN_INVENTORY_START_Y + row * self.SLOT_STEP
            return (x, y)
        
        return None

    def _render_inventory_image(self, player_name: str, slots: list) -> str | None:
        """渲染背包为图片.
        
        Args:
            player_name: 玩家名称
            slots: 背包格子列表
            
        Returns:
            临时图片文件路径或None如果渲染失败
        """
        if not self.pillow_available or self.Image is None:
            return None
        
        try:
            # 加载背包UI底图
            ui_path = os.path.join(os.path.dirname(__file__), "背包绘制", "inventory.png")
            if not os.path.exists(ui_path):
                return None
            
            inventory_img = self.Image.open(ui_path).convert("RGBA")
            
            # 裁剪到标准尺寸
            if (inventory_img.size[0] > self.INVENTORY_WIDTH or 
                inventory_img.size[1] > self.INVENTORY_HEIGHT):
                inventory_img = inventory_img.crop(
                    (0, 0, self.INVENTORY_WIDTH, self.INVENTORY_HEIGHT)
                )
            
            # 材质目录
            texture_dir = os.path.join(os.path.dirname(__file__), "背包绘制", "材质图片", "items")
            
            # 遍历物品slot
            for idx, slot in enumerate(slots):
                if slot is None:
                    continue
                
                pos = self._get_slot_position(idx)
                if pos is None:
                    continue
                
                # 获取物品材质
                full_id = self._get_full_item_id(slot)
                if not full_id:
                    continue
                
                # 移除命名空间
                item_id = full_id.split(":", 1)[1] if ":" in full_id else full_id
                texture_path = os.path.join(texture_dir, f"{item_id}.png")
                
                # 如果材质不存在，尝试常见变体
                if not os.path.exists(texture_path):
                    # 尝试添加常见后缀
                    for suffix in ["", "_normal", "_standby"]:
                        alt_path = os.path.join(texture_dir, f"{item_id}{suffix}.png")
                        if os.path.exists(alt_path):
                            texture_path = alt_path
                            break
                
                if os.path.exists(texture_path):
                    try:
                        item_img = self.Image.open(texture_path).convert("RGBA")
                        # 调整物品图标大小
                        item_img = item_img.resize(
                            (self.SLOT_SIZE, self.SLOT_SIZE),
                            self.Image.Resampling.LANCZOS
                        )
                        inventory_img.paste(item_img, pos, item_img)
                    except Exception:
                        # 材质加载失败，绘制灰色背景
                        draw = self.ImageDraw.Draw(inventory_img)
                        draw.rectangle(
                            [pos[0], pos[1], 
                             pos[0] + self.SLOT_SIZE - 1, 
                             pos[1] + self.SLOT_SIZE - 1],
                            fill=self.MISSING_TEXTURE_COLOR
                        )
                else:
                    # 没有材质，绘制灰色背景
                    draw = self.ImageDraw.Draw(inventory_img)
                    draw.rectangle(
                        [pos[0], pos[1], 
                         pos[0] + self.SLOT_SIZE - 1, 
                         pos[1] + self.SLOT_SIZE - 1],
                        fill=self.MISSING_TEXTURE_COLOR
                    )
                
                # 绘制数量
                cnt = getattr(slot, "stackSize", 0)
                if cnt > 1:
                    draw = self.ImageDraw.Draw(inventory_img)
                    text = str(cnt)
                    # 文字位置：右下角
                    text_x = pos[0] + self.SLOT_SIZE - 10
                    text_y = pos[1] + self.SLOT_SIZE - 10
                    # 阴影+白色文字
                    draw.text((text_x + 1, text_y + 1), text, fill=(0, 0, 0, 255))
                    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255))
            
            # 保存到临时文件
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(
                temp_dir, 
                f"inventory_{player_name}_{int(time.time())}.png"
            )
            inventory_img.save(output_path, "PNG")
            return output_path
            
        except Exception as e:
            self.print(f"§c渲染背包图片失败: {e}")
            return None

    def _query_inventory(self, sender: int, args: list[str]):
        """查询玩家背包内容并发送到群聊."""
        try:
            keyword = " ".join(args).strip()
            players = self.game_ctrl.players.getAllPlayers()
            matches = [p for p in players if keyword in p.name]
            
            if len(matches) == 0:
                self.sendmsg(self.linked_group, "未寻找到匹配的玩家")
                return
            
            if len(matches) > 1:
                names = ", ".join(p.name for p in matches[:5])
                suffix = "" if len(matches) <= 5 else f" 等 {len(matches)} 人"
                self.sendmsg(self.linked_group, f"匹配到多个玩家：{names}{suffix}")
                return
            
            target = matches[0]
            inv = target.queryInventory()
            slots = inv.slots or []
        except Exception as e:
            self.sendmsg(self.linked_group, f"查询失败: {e}")
            return
        
        # 如果Pillow可用，生成图片
        if self.pillow_available:
            img_path = self._render_inventory_image(target.name, slots)
            
            if img_path:
                try:
                    # 读取图片并转换为base64
                    with open(img_path, 'rb') as f:
                        img_data = f.read()
                    img_base64 = base64.b64encode(img_data).decode('utf-8')
                    
                    # 生成文本版本
                    text_lines = self._generate_text_inventory(slots)
                    
                    # 发送图片+文本
                    combined_msg = (
                        f"玩家 {target.name} 的背包:\n"
                        f"[CQ:image,file=base64://{img_base64}]\n"
                        f"\n文本版本：\n{text_lines}"
                    )
                    self.sendmsg(self.linked_group, combined_msg, do_remove_cq_code=False)
                    
                    # 删除临时文件
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass
                    return
                except Exception as e:
                    self.print(f"§c发送背包图片失败: {e}")
        
        # 回退到文本模式
        lines: list[str] = []
        for idx, slot in enumerate(slots):
            if slot is None:
                continue
            
            name = self._localize_item(slot)
            aux = getattr(slot, "aux", 0)
            cnt = getattr(slot, "stackSize", 0)
            ench = getattr(slot, "enchantments", [])
            
            if ench:
                # 展开附魔名称：优先使用name属性，否则用映射表翻译type ID
                ench_parts = []
                for e in ench:
                    # 优先尝试获取name属性（如果存在且是中文）
                    ench_name = getattr(e, 'name', None)
                    if ench_name:
                        ench_parts.append(ench_name)
                    else:
                        # 回退：name不存在，尝试用映射表翻译type ID
                        ench_id = getattr(e, 'type', None)
                        if ench_id is not None and ench_id in self.enchantment_name_map:
                            ench_parts.append(self.enchantment_name_map[ench_id])
                        else:
                            # 最后的回退：显示type和level
                            ench_type = getattr(e, 'type', '?')
                            ench_level = getattr(e, 'level', '?')
                            ench_parts.append(f"type{ench_type} Lv{ench_level}")
                ench_text = ", ".join(ench_parts)
                if aux != 0:
                    lines.append(f"\t- [{idx}] {name} x {cnt} (数据: {aux}; 附魔: {ench_text})")
                else:
                    lines.append(f"\t- [{idx}] {name} x {cnt} (附魔: {ench_text})")
            else:
                if aux != 0:
                    lines.append(f"\t- [{idx}] {name} x {cnt} (数据: {aux})")
                else:
                    lines.append(f"\t- [{idx}] {name} x {cnt}")
        
        text = "该玩家背包中没有物品" if len(lines) == 0 else "\n".join(lines)
        self.sendmsg(self.linked_group, f"玩家 {target.name} 的背包信息如下: \n{text}")

    # ------------------------ API ------------------------
    def add_trigger(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[[int, list[str]], Any],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        self.triggers.append(
            QQMsgTrigger(triggers, argument_hint, usage, func, args_pd, op_only)
        )

    def is_qq_op(self, qqid: int):
        return qqid in self.can_exec_cmd

    def set_manual_launch(self, port: int):
        self._manual_launch = True
        self._manual_launch_port = port

    def manual_launch(self):
        self.connect_to_websocket()

    # ------------------------------------------------------
    def on_def(self):
        """加载前置API和Pillow库."""
        # 加载Pillow库（符合WARP.md规范：GetPluginAPI必须在ListenPreload中调用）
        try:
            from PIL import Image, ImageDraw, ImageFont
            self.pillow_available = True
            self.Image = Image
            self.ImageDraw = ImageDraw
            self.ImageFont = ImageFont
            self.print("§aPillow库已加载")
        except ImportError:
            try:
                pip_support = self.GetPluginAPI("pip")
                if pip_support:
                    pip_support.require({"Pillow": "Pillow"})
                    from PIL import Image, ImageDraw, ImageFont
                    self.pillow_available = True
                    self.Image = Image
                    self.ImageDraw = ImageDraw
                    self.ImageFont = ImageFont
                    self.print("§aPillow库已安装并加载")
            except Exception as e:
                self.pillow_available = False
                self.Image = None
                self.ImageDraw = None
                self.ImageFont = None
                self.print(f"§c无法加载Pillow库: {e}，背包图片功能将不可用")
        
        self.tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)

    def on_inject(self):
        self.print("尝试连接到群服互通机器人..")
        if not self._manual_launch:
            self.connect_to_websocket()
        self.init_basic_triggers()

    def init_basic_triggers(self):
        @utils.thread_func("群服执行指令并获取返回")
        def sb_execute_cmd(qqid: int, cmd: list[str]):
            if self.is_qq_op(qqid):
                res = execute_cmd_and_get_zhcn_cb(" ".join(cmd))
                self.sendmsg(self.linked_group, res)
            else:
                self.sendmsg(self.linked_group, "你是管理吗你还发指令 🤓👆")

        def execute_cmd_and_get_zhcn_cb(cmd: str):
            try:
                result = self.game_ctrl.sendwscmd_with_resp(cmd, 10)
                if len(result.OutputMessages) == 0:
                    return ["😅 指令执行失败", "😄 指令执行成功"][
                        bool(result.SuccessCount)
                    ]
                if (result.OutputMessages[0].Message == "commands.generic.syntax") | (
                    result.OutputMessages[0].Message == "commands.generic.unknown"
                ):
                    return f'😅 未知的 MC 指令, 可能是指令格式有误: "{cmd}"'
                else:
                    if translate is not None:
                        mjon = "\n".join(
                            translate(i.Message, i.Parameters)
                            for i in result.OutputMessages
                        )
                    if result.SuccessCount:
                        if translate is not None:
                            return "😄 指令执行成功， 执行结果：\n " + mjon
                        else:
                            return (
                                "😄 指令执行成功， 执行结果：\n"
                                + result.OutputMessages[0].Message
                            )
                    else:
                        if translate is not None:
                            return "😭 指令执行失败， 原因：\n" + mjon
                        else:
                            return (
                                "😭 指令执行失败， 原因：\n"
                                + result.OutputMessages[0].Message
                            )
            except IndexError as exec_err:
                import traceback

                traceback.print_exc()
                return f"执行出现问题: {exec_err}"
            except TimeoutError:
                return "😭超时： 指令获取结果返回超时"

        def send_player_list():
            players = [f"{i + 1}.{j}" for i, j in enumerate(self.game_ctrl.allplayers)]
            fmt_msg = (
                f"在线玩家有 {len(players)} 人：\n "
                + "\n ".join(players)
                + (
                    f"\n当前 TPS： {round(self.tps_calc.get_tps(), 1)}/20"
                    if self.tps_calc
                    else ""
                )
            )
            self.sendmsg(self.linked_group, fmt_msg)

        def lookup_help(sender: int, _):
            output_msg = f"[CQ:at,qq={sender}] 群服互通帮助菜单："
            for trigger in self.triggers:
                output_msg += (
                    f"  \n{trigger.triggers[0]}"
                    f"{' ' + trigger.argument_hint if trigger.argument_hint else ''} "
                    f"： {trigger.usage}"
                )
                if trigger.op_only:
                    output_msg += " （仅管理员可用）"
            self.sendmsg(self.linked_group, output_msg, do_remove_cq_code=False)

        self.frame.add_console_cmd_trigger(
            ["QQ", "发群"], "[消息]", "在群内发消息测试", self.on_sendmsg_test
        )
        # 查询背包（置于通用"/"触发器之前，避免被通配符吞掉）
        self.add_trigger(
            ["/查询背包"],
            "[玩家名]",
            "获取对方背包内物品, 并输出在群里",
            self._query_inventory,
            args_pd=lambda n: n >= 1,
        )
        self.add_trigger(
            ["/"], "[指令]", "向租赁服发送指令", sb_execute_cmd, op_only=True
        )
        self.add_trigger(["help", "帮助"], None, "查看群服互通帮助", lookup_help)
        if self.enable_playerlist:
            self.add_trigger(
                ["list", "玩家列表"],
                None,
                "查看玩家列表",
                lambda _, _2: send_player_list(),
            )

    @utils.thread_func("云链群服连接进程")
    def connect_to_websocket(self):
        header = None
        if self.cfg["云链设置"]["校验码"] is not None:
            header = {"Authorization": f"Bearer {self.cfg['云链设置']['校验码']}"}
        self.ws = websocket.WebSocketApp(
            (
                f"ws://127.0.0.1:{self._manual_launch_port}"
                if self._manual_launch
                else self.cfg["云链设置"]["地址"]
            ),
            header,
            on_message=lambda a, b: self.on_ws_message(a, b) and None,
            on_error=self.on_ws_error,
            on_close=self.on_ws_close,
        )
        self.ws.on_open = self.on_ws_open
        self.ws.run_forever()

    @utils.thread_func("云链群服消息广播进程")
    def broadcast(self, data):
        for i in self.plugin:
            self.GetPluginAPI(i).QQLinker_message(data)

    def on_ws_open(self, ws):
        self.available = True
        self.print("§a已成功连接到群服互通 =============")

    @utils.thread_func("群服互通消息接收线程")
    def on_ws_message(self, ws, message):
        data = json.loads(message)
        bc_recv = self.BroadcastEvent(InternalBroadcast("群服互通/数据json", data))
        if any(bc_recv):
            return
        if data.get("post_type") == "message" and data["message_type"] == "group":
            self.broadcast(data)
            if data["group_id"] != self.linked_group:
                return
            msg = data["message"]
            if isinstance(msg, list):
                # NapCat
                msg_rawdict = msg[0]
                msg_type = msg_rawdict["type"]
                msg_data = msg_rawdict["data"]
                if msg_type != "text":
                    return
                msg = msg_data["text"]
            elif not isinstance(msg, str):
                raise ValueError(f"键 'message' 值不是字符串类型, 而是 {msg}")
            if self.enable_group_2_game:
                user_id = data["sender"]["user_id"]
                nickname = data["sender"]["card"] or data["sender"]["nickname"]
                if user_id in self.waitmsg_cbs.keys():
                    self.waitmsg_cbs[user_id](
                        msg,
                    )
                    return
                bc_recv = self.BroadcastEvent(
                    InternalBroadcast(
                        "群服互通/链接群消息",
                        {"QQ号": user_id, "昵称": nickname, "消息": msg},
                    ),
                )
                if any(bc_recv):
                    return
                elif self.execute_triggers(user_id, msg):
                    return
                if self.replace_colorful_name:
                    nickname = remove_color(nickname)
                if self.replace_colorful_msg:
                    msg = remove_color(msg)
                self.game_ctrl.say_to(
                    "@a",
                    utils.simple_fmt(
                        {
                            "[昵称]": nickname,
                            "[消息]": replace_cq(msg),
                        },
                        self.cfg["消息转发设置"]["群到游戏"]["转发格式"],
                    ),
                )

    def on_ws_error(self, ws, error):
        if not isinstance(error, Exception):
            fmts.print_inf(f"群服互通发生错误: {error}, 可能为系统退出, 已关闭")
            self.reloaded = True
            return
        else:
            self.available = False
        fmts.print_err(f"群服互通发生错误: {error}, 15s后尝试重连")
        time.sleep(15)

    def waitMsg(self, qqid: int, timeout=60) -> str | None:
        g, s = utils.create_result_cb(str)
        self.waitmsg_cbs[qqid] = s
        r = g(timeout)
        del self.waitmsg_cbs[qqid]
        return r

    def on_ws_close(self, ws, _, _2):
        self.available = False
        if self.reloaded:
            return
        fmts.print_err("群服互通被关闭, 10s后尝试重连")
        time.sleep(10)
        self.connect_to_websocket()

    def on_player_join(self, playerf: Player):
        player = playerf.name
        if self.ws and self.enable_game_2_group and self.enable_player_join_leave:
            self.sendmsg(self.linked_group, f"{player} 加入了游戏")

    def on_player_leave(self, playerf: Player):
        player = playerf.name
        if self.ws and self.enable_game_2_group and self.enable_player_join_leave:
            self.sendmsg(self.linked_group, f"{player} 退出了游戏")

    def on_player_message(self, chat: Chat):
        player = chat.player.name
        msg = chat.msg

        if self.ws and self.enable_game_2_group:
            if self.game2qq_trans_chars != []:
                can_send = False
                for prefix in self.game2qq_trans_chars:
                    if msg.startswith(prefix):
                        can_send = True
                        msg = msg[len(prefix) :]
                        break
            elif self.game2qq_block_prefixs != []:
                can_send = True
                for prefix in self.game2qq_block_prefixs:
                    if msg.startswith(prefix):
                        can_send = False
                        break
            else:
                can_send = True
            if not can_send:
                return
            self.sendmsg(
                self.linked_group,
                utils.simple_fmt(
                    {"[玩家名]": player, "[消息]": remove_cq_code(msg)},
                    self.cfg["消息转发设置"]["游戏到群"]["转发格式"],
                ),
            )

    def execute_triggers(self, qqid: int, msg: str):
        for trigger in self.triggers:
            if t := trigger.match(msg):
                if self.is_qq_op(qqid) or not trigger.op_only:
                    args = msg.removeprefix(t).strip().split()
                    if trigger.args_pd(len(args)):
                        trigger.func(qqid, args)
                    else:
                        self.sendmsg(
                            self.linked_group,
                            f"[CQ:at,qq={qqid}] 参数错误，格式：{t}"
                            f"{' ' + trigger.argument_hint if trigger.argument_hint else ''}",
                            do_remove_cq_code=False,
                        )
                else:
                    if easter_egg := EASTER_EGG_QQIDS.get(qqid):
                        name, nickname = easter_egg
                        self.sendmsg(
                            self.linked_group,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令，即使你是 {nickname}..",
                            do_remove_cq_code=False,
                        )
                    else:
                        self.sendmsg(
                            self.linked_group,
                            f"[CQ:at,qq={qqid}] 你没有权限执行此指令",
                            do_remove_cq_code=False,
                        )
                return True
        return False

    def on_sendmsg_test(self, args: list[str]):
        if self.ws:
            self.sendmsg(self.linked_group, " ".join(args))
        else:
            fmts.print_err("还没有连接到群服互通")

    def sendmsg(self, group: int, msg: str, do_remove_cq_code=True):
        assert self.ws
        if not self.available:
            self.print(f"§6未连接, 忽略发送至 {group} 的消息 {msg}")
            return
        if do_remove_cq_code:
            msg = remove_cq_code(msg)
        jsondat = json.dumps(
            {
                "action": "send_group_msg",
                "params": {"group_id": group, "message": msg},
            }
        )
        self.ws.send(jsondat)


entry = plugin_entry(QQLinker, "群服互通")
