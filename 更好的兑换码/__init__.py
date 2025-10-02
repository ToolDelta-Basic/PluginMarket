from tooldelta import plugin_entry, Plugin, ToolDelta, Chat, utils, game_utils, fmts
from tooldelta.utils import tempjson
import binascii
import zlib
import msgpack
import brotli
import os
import json


class NewPlugin(Plugin):
    name = "兑换码插件"
    author = "衍"
    version = (0, 0, 1)  # 插件版本号, 可选, 是一个三元整数元组

    # 初始化插件类实例
    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        """
        使用前请装载pip模块支持插件

        然后输入
        pip-install cffi
        pip-install pycryptodome
        再下载本模组
        """

        self.data_dick = {
            "id": int,  # 用于判断这个对话那么是否被使用过
            "get_item": [
                {"name": str, "age": str, "data": str}
            ],  # 给予使用兑换码的人物品(物品名字 数量 特殊值)
            "get_tag_add": [str],  # 给予使用兑换码的人标签
            "get_tag_remove": [str],  # 删除使用兑换码的人标签
            "get_command": [
                {"command1": str, "command2": str}
            ],  # 对使用兑换码的人给予指令(execute用不了)
            "get_command_freedom": [str],  # 使用兑换码后会发送的指令
            "get_structure": [str],  # 对使用兑换码的人生成一个结构
        }
        self.id = 0

        # 密钥可以自定义
        self.key = bytes.fromhex("60F1E0D1FD635362430747215C123852")
        self.ListenPreload(self.Preload)
        self.ListenChat(self.on_chat)  # 玩家发言后执行

        # 检测指令
        self.frame.add_console_cmd_trigger(
            ["生成兑换码"], None, "生成兑换码", self.add_exchange_code
        )

    def Preload(self):
        global AES, get_random_bytes, pad, unpad
        self.GetPluginAPI("pip").require({"cffi": "cffi", "pycryptodome": "Crypto", "msgpack": "msgpack"})

        from Crypto.Cipher import AES
        from Crypto.Random import get_random_bytes
        from Crypto.Util.Padding import pad
        from Crypto.Util.Padding import unpad

        if not os.path.isfile("插件配置文件/兑换码已使用列表.json"):
            fmts.print_load("检测到没有初始文件已加载")
            tempjson.load_and_write(r"插件配置文件/兑换码已使用列表.json", [], False)
        self.id = len(tempjson.load_and_read("插件配置文件/兑换码已使用列表.json"))
        fmts.print_load(f"密钥内容: {self.key}")
        if len(self.key) == 16:
            fmts.print_load("加密密钥长度为16为启用aes128模式")
        elif len(self.key) == 24:
            fmts.print_load("加密密钥长度为24为启用aes192模式")
        elif len(self.key) == 32:
            fmts.print_load("加密密钥长度为32为启用aes256模式")
        else:
            fmts.print_load("错误的密钥模式请更改不然会出现错误")

    def add_exchange_code(self, List: list[str]):
        dick = {
            "id": int,  # 用于判断这个对话那么是否被使用过
            #"get_item": [],  # 给予使用兑换码的人物品(物品名字 数量 特殊值)
            #"get_tag_add": [],  # 给予使用兑换码的人标签
            #"get_tag_remove": [],  # 删除使用兑换码的人标签
            #"get_command": [],  # 对使用兑换码的人给予指令(execute用不了)
            #"get_command_freedom": [],  # 使用兑换码后会发送的指令
            #"get_structure": [],  # 对使用兑换码的人生成一个结构
        }
        while True:
            age = input(
                "1.给予物品(give)\n2.给予标签(tag)\n3.删除标签(tag)\n4.给予指令(选择器固定为玩家本人)\n5.自由指令(自己随便写指令)\n6.生成结构(在玩家的坐标位置生成一个结构)\n7.重置兑换码\n8.生成兑换码\n9.结束\n请选择兑换码会涵盖的内容:"
            )
            match age:
                case "1":
                    if "get_item" not in dick:
                        dick["get_item"] = []
                    name = input("输入物品名称(英文名): ")
                    num = input("输入物品数量: ")
                    data = input("输入物品特殊值: ")
                    dick["get_item"].append({"name": name, "age": num, "data": data})

                case "2":
                    if "get_tag_add" not in dick:
                        dick["get_tag_add"] = []
                    tag = input("输入要添加的标签: ")
                    dick["get_tag_add"].append(tag)
                case "3":
                    if "get_tag_remove" not in dick:
                        dick["get_tag_remove"] = []
                    tag = input("输入要删除的标签: ")
                    dick["get_tag_remove"].append(tag)
                case "4":
                    if "get_command" not in dick:
                        dick["get_command"] = []
                    command1 = input("输入要前缀指令(如tp, tag, gamemode): ")
                    command2 = input("输入要后缀缀指令(如xyz): ")
                    dick["get_command"].append(
                        {"command1": command1, "command2": command2}
                    )
                case "5":
                    if "get_command_freedom" not in dick:
                        dick["get_command_freedom"] = []
                    command = input("输入要执行的完整指令: ")
                    dick["get_command_freedom"].append(command)
                case "6":
                    if "get_structure" not in dick:
                        dick["get_structure"] = []
                    structure = input("输入要生成的结构名称: ")
                    dick["get_structure"].append(structure)
                case "7":
                    dick = {
                        "id": int,  # 用于判断这个对话那么是否被使用过
                    }
                    fmts.print_inf("兑换码内容已重置")
                case "8":
                    num = input("输入要生成的兑换码数量(空着默认是1): ")
                    if num == "":
                        self.id += 1
                        dick["id"] = self.id
                        dick_msgpack = msgpack.packb(dick)
                        dick_brotli = brotli.compress(dick_msgpack, quality=11)
                        dick_ = aes_Encrypt(dick_brotli.hex(), self.key)
                        dick_n = convert_chars(dick_)
                        fmts.print_inf(f"兑换码：{dick_n}")
                        fmts.print_inf(f"已经存储进兑换码历史记录里面json里面")
                        with open("兑换码历史记录.txt", "a", encoding="utf-8") as f:
                            f.write(f"{dick_n}\n")
                        tempjson.unload_to_path("兑换码历史记录.json")
                        return
                    else:
                        List = []
                        for i in range(int(num)):
                            self.id += 1
                            dick["id"] = self.id
                            dick_msgpack = msgpack.packb(dick)
                            dick_brotli = brotli.compress(dick_msgpack, quality=11)
                            dick_ = aes_Encrypt(dick_brotli.hex(), self.key)
                            dick_n = convert_chars(dick_)
                            List.append(dick_n)
                        fmts.print_inf(f"兑换码：{List}")
                        fmts.print_inf("已经存储进兑换码历史记录里面json里面")
                        with open('兑换码历史记录.txt', 'a', encoding='utf-8') as f:
                            f.write(f'{List}\n')
                        tempjson.unload_to_path("兑换码历史记录.json")
                        return
                case "9":
                    return

    # 监听玩家发言
    @utils.thread_func("每个玩家输入对应指令后都生成一个新的线程")
    def on_chat(self, chat: Chat):
        # 获取玩家信息
        player = chat.player
        # 获取玩家信息
        player_pos = game_utils.getPos(player.name)
        # 获取玩家说的话
        msg = chat.msg
        if msg == "*使用兑换码":
            try:
                data = player.input("请输入兑换码：")
                if data is None:
                    player.show("§c兑换码使用超时")
                    return
                data_map = convert_chars(data, reverse=True)
                data_Decrypt = aes_Decrypt(data_map, self.key)
                data_brotli = brotli.decompress(data_Decrypt)
                data_msgpack = msgpack.unpackb(data_brotli)
                fmts.print_suc(f"兑换码内容：{data_msgpack}")
                if type(data_msgpack) == dict:
                    id_list = tempjson.load_and_read(
                        "插件配置文件/兑换码已使用列表.json", default=[]
                    )
                    if "id" in data_msgpack:
                        print(data_msgpack["id"])
                        print(type(data_msgpack["id"]))
                        if not data_msgpack["id"] in id_list:
                            fmts.print_inf(f"玩家{player.name}使用了兑换码")
                            id_list.append(data_msgpack["id"])
                            with open('插件配置文件/兑换码已使用列表.json', 'w', encoding='utf-8') as f:
                                f.write(f"{id_list}")

                            self.parsing(data_msgpack, player.name, player_pos)
                            self.game_ctrl.player_title(player.name, "兑换成功")
                        else:
                            fmts.print_war(
                                f"玩家{player.name}的兑换码兑换失败已经被使用过了"
                            )
                            player.show("兑换码已经被使用了")
                    else:
                        fmts.print_err(
                            f"玩家{player.name}的兑换码的字典没有id疑似伪造的"
                        )
                        player.show("错误的兑换码")
                else:
                    player.show("你输入了未知信息")
            except Exception as e:
                fmts.print_err("信息无法被转换成字典")
                player.show("你输入了未知信息")
        else:
            return

    @utils.thread_func("每次被调用都生成一个新的线程")
    def parsing(self, data: dict, player_name: str, player_pos: dict):
        try:
            for key in data.keys():
                if key == "get_item":
                    for i in data[key]:
                        self.game_ctrl.sendcmd(
                            f"/give {player_name} {i['name']} {i['age']} {i['data']}"
                        )
                elif key == "get_tag_add":
                    for i in data[key]:
                        self.game_ctrl.sendcmd(f"/tag {player_name} add {i}")
                elif key == "get_tag_remove":
                    for i in data[key]:
                        self.game_ctrl.sendcmd(f"/tag {player_name} remove {i}")
                elif key == "get_command":
                    for i in data[key]:
                        self.game_ctrl.sendcmd(
                            f"/{i['command1']} {player_name} {i['command2']}"
                        )
                elif key == "get_command_freedom":
                    for i in data[key]:
                        self.game_ctrl.sendcmd(f"/{i}")
                elif key == "get_structure":
                    for i in data[key]:
                        print(i)
                        print(player_pos)
                        self.game_ctrl.sendcmd(
                            f"/structure load {i} {player_pos['position']['x']} {player_pos['position']['y']} {player_pos['position']['z']}"
                        )
        except Exception as e:
            fmts.print_err("指令出现错误")


# 绕过网易检测
def convert_chars(input_str: str, *, reverse=False):
    # 正向转换映射（普通字符→特殊字符）
    forward_map = {
        "1": "Ⅰ",
        "2": "Ⅱ",
        "3": "Ⅲ",
        "4": "Ⅳ",
        "5": "Ⅴ",
        "6": "Ⅵ",
        "7": "Ⅶ",
        "8": "Ⅷ",
        "9": "Ⅸ",
        "0": "Ⅹ",
        "a": "Ａ",
        "b": "Ｂ",
        "c": "Ｃ",
        "d": "Ｄ",
        "e": "Ｅ",
        "f": "Ｆ",
    }

    # 反向转换映射（特殊字符→普通字符）
    reverse_map = {v: k for k, v in forward_map.items()}

    # 根据模式选择映射表
    mapping = reverse_map if reverse else forward_map

    # 执行转换（保留未定义字符）
    return "".join(mapping.get(c, c) for c in input_str)


# aes cbc模式加密
def aes_Encrypt(data: str, key: bytes) -> str:
    """
    :param data: 数据(hex)
    :param key: 密钥
    :return:
    """
    # 随机生成16字节（128）的iv
    iv = get_random_bytes(16)
    # 实例化加密套件，使用CBC模式
    cipher = AES.new(key, AES.MODE_CBC, iv)
    # 对内容进行填充
    data_pad = pad(bytes.fromhex(data), AES.block_size)
    # 加密
    encrypted_data = cipher.encrypt(data_pad)
    # 转换成hex
    data_hex = binascii.hexlify(encrypted_data)
    # 取密钥标识
    iva = binascii.hexlify(iv)
    data_Encrypt = iva + data_hex
    decoded_str = data_Encrypt.decode("utf-8")
    return decoded_str


# aes cbc模式解密
def aes_Decrypt(data: str, key: bytes):
    """
    :param data: 加密数据(hex)
    :param key: 密钥
    :return:
    """
    # 随机向量
    ivd = bytes.fromhex(data[:32])
    # 获取密文
    data_bytes = bytes.fromhex(data)
    # 创建 AES-CBC 解密器
    cipher = AES.new(key, AES.MODE_CBC, ivd)
    # 解密密文
    padded_plaintext = cipher.decrypt(data_bytes)
    decrypted_text = unpad(padded_plaintext, AES.block_size)
    # text_json = json.loads(decrypted_text[16:].decode('utf-8').replace("'", '"'))
    return decrypted_text[16:]


# 主线程
entry = plugin_entry(NewPlugin)
