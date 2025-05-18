from tooldelta import (
    Plugin,
    Config,
    game_utils,
    Utils,
    Print,
    Player,
    Chat,
    plugin_entry,
)
import os
import json
import time
import random
# import importlib
# mport player_exchange
# importlib.reload(player_exchange)
# from player_exchange import *


class airisland(Plugin):
    name = "单方块空岛系统"
    author = "猫七街"
    version = (0, 0, 5)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)

        cfg = {
            "方块更新周期(秒)": 10,
            "分配提示词": "分配单方块空岛",
            "回岛提示词": "返回空岛",
            "起点坐标": (0, 0, 0),
            "单方块坐标偏移": (1, 1, 1),
            "玩家传送坐标偏移": (1, 2, 1),
            "空岛x方向数量": 100,
            "空岛z方向数量": 100,
            "空岛间距(区块)": 120,
            "空岛唯一性": True,
            "结构名字": "空岛模板",
            "自动保存时间（秒）": 60,
            "临时常加载名字": "Temp",
            "未分配提示": "你未分配空岛",
            "重复分配提示": "你已经分配过空岛了",
            "正在分配提示": "检查成功，正在分配空岛",
            "分配成功提示": "分配成功",
            "空岛分配上限提示": "已无可供分配空岛",
            "方块包添加": "添加方块包",
            "方块包添加成功提示": "方块包添加成功",
            "方块包添加失败提示": "无法添加该方块包",
            "方块包添加密码": "%)(sk)'`sftys3",
            "方块包查询": "查询方块包",
            "查询提示标题": "§e=== 当前拥有的方块包 ===",
            "无方块包提示": "§c你还没有任何可用的方块包",
            "方块包条目格式": "§a{package_name} §7- §b剩余次数: §6{count}",
        }

        self._cfg, version = Config.get_plugin_config_and_version(
            self.name, {}, cfg, self.version
        )
        if version < self.version:
            self._cfg["交易所触发词"] = "玩家交易所"
            self._cfg["交易所菜单头"] = (
                "§b>>>>>>>>玩家交易所<<<<<<<<\n§b>>>>>>>>手续费{手续费}  <<<<<<<<"
            )
            self._cfg["使用计分板"] = "coin"
            self._cfg["提交商品"] = "提交商品"
            self._cfg["交易手续费"] = 0.1
            self._cfg["手续费起收金额"] = 0
            Config.upgrade_plugin_config(self.name, self._cfg, self.version)
        # self.exchange_menu_head = self._cfg["交易所菜单头"].format(手续费=self._cfg["交易手续费"])
        self.block_package_path = self.format_data_path("方块包.json")
        default_block_packages = {
            "基础方块包": [
                ["grass", 0],
                ["dirt", 0],
                ["wood", 0],
                ["wood", 1],
                ["stone", 0],
            ],
            "进阶方块包": [["diamond_block", 0], ["gold_block", 0], ["iron_block", 0]],
        }

        if not os.path.exists(self.block_package_path):
            try:
                with open(self.block_package_path, "w", encoding="utf-8") as f:
                    json.dump(default_block_packages, f, indent=4, ensure_ascii=False)

                Print.print_suc("已创建默认方块包配置文件")

            except Exception as e:
                Print.print_err(f"创建方块包配置文件失败: {e}")
                self.block_package = default_block_packages

        else:
            try:
                with open(self.block_package_path, encoding="utf-8") as f:
                    custom_packages = json.load(f)

                self.block_package = custom_packages
                self._cfg["方块包"] = custom_packages
                Print.print_suc("已加载自定义方块包配置")

            except Exception as e:
                Print.print_err(f"加载方块包配置失败: {e}，使用默认配置")
                self.block_package = default_block_packages
                self._cfg["方块包"] = default_block_packages

        self.players = []
        self.block_package = self._cfg["方块包"]
        data_dir = self.data_path
        data_path = os.path.join(data_dir, "单方块空岛数据.json")
        self.data_path_bat = os.path.join(data_dir, "单方块空岛数据_bat.json")
        self.Sky_Island_data = []
        self.player_island_map = {}
        try:
            with open(data_path, encoding="utf-8") as f:
                self.Sky_Island_data = json.load(f)

        except Exception:
            try:
                with open(self.data_path_bat, encoding="utf-8") as f:
                    self.Sky_Island_data = json.load(f)

                with open(data_path, "w", encoding="utf-8") as f:
                    json.dump(self.Sky_Island_data, f, indent=4, ensure_ascii=False)

            except:  # noqa: E722
                self.Sky_Island_data = [
                    {
                        "是否分配": False,
                        "玩家信息": {
                            "player_uuid": None,
                            "player_name": None,
                            "方块包": [["基础方块包", 999999]],
                        },
                        "x": x * self._cfg["空岛间距(区块)"] * 16
                        + self._cfg["起点坐标"][0],
                        "y": self._cfg["起点坐标"][1],
                        "z": z * self._cfg["空岛间距(区块)"] * 16
                        + self._cfg["起点坐标"][2],
                    }
                    for x in range(self._cfg["空岛x方向数量"])
                    for z in range(self._cfg["空岛z方向数量"])
                ]
                self.save_data(data_path)

    def save_data(self, data_path):
        try:
            with open(self.data_path_bat, "w", encoding="utf-8") as f:
                json.dump(self.Sky_Island_data, f, indent=4, ensure_ascii=False)

            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(self.Sky_Island_data, f, indent=4, ensure_ascii=False)

        except Exception as e:
            Print.print_err(f"数据保存失败: {e}")

    def on_def(self):
        self.get_structure = self.GetPluginAPI("前置-世界交互")

    def on_inject(self):
        a = 0
        while True:
            try:
                flag = self.game_ctrl.bot_name  # noqa: F841
                Print.print_suc("单方块空岛系统载入成功")
                break

            except:  # noqa: E722
                a += 1
                print(f"尝试载入单方块空岛系统, {a}")
                time.sleep(1)

        self.get_players(None)
        Utils.createThread(self.auto_setblock, (), "单方块更新")
        Utils.createThread(self.auto_save_data, (), "数据自动保存")
        # Utils.createThread(sale_check, (self,), usage="售卖检测")

    def on_player_join(self, player: Player):
        self.get_players(None)

    def on_player_leave(self, player: Player):
        self.get_players(None)

    def on_player_message(self, chat: Chat) -> None:
        player_name = chat.player.name
        msg = chat.msg

        if msg == self._cfg["分配提示词"]:
            player_uuid = self.game_ctrl.players_uuid[player_name]
            data_path = os.path.join(self.data_path, "单方块空岛数据.json")

            try:
                with open(data_path, encoding="utf-8") as f:
                    Sky_Island_data = json.load(f)

            except Exception as e:
                Print.print_err(f"加载空岛数据失败: {e}")
                self.game_ctrl.say_to(player_name, "§c系统错误，请联系管理员")
                return

            if self._cfg["空岛唯一性"]:
                if any(
                    island["玩家信息"]["player_uuid"] == player_uuid
                    for island in Sky_Island_data
                ):
                    self.game_ctrl.say_to(player_name, self._cfg["重复分配提示"])
                    return

            start_x, start_y, start_z = self._cfg["起点坐标"]
            closest_island = None
            min_distance_sq = float("inf")
            for index, island in enumerate(Sky_Island_data):
                if not island["是否分配"]:
                    dx = island["x"] - start_x
                    dz = island["z"] - start_z
                    distance_sq = dx**2 + dz**2

                    if distance_sq < min_distance_sq:
                        min_distance_sq = distance_sq
                        closest_island = index

            if closest_island is None:
                self.game_ctrl.say_to(player_name, self._cfg["空岛分配上限提示"])
                return

            selected_island = Sky_Island_data[closest_island]
            try:
                self.game_ctrl.say_to(player_name, self._cfg["正在分配提示"])
                self.game_ctrl.sendwocmd(
                    f"/tickingarea add circle {selected_island['x']} 0 {selected_island['z']} 4 {self._cfg['临时常加载名字']}"
                )
                time.sleep(1)
                self.game_ctrl.sendwocmd(
                    f'/structure load "{self._cfg["结构名字"]}" {selected_island["x"]} {start_y} {selected_island["z"]}'
                )
                self.game_ctrl.sendwocmd(
                    f"/tickingarea remove {self._cfg['临时常加载名字']}"
                )
                selected_island["是否分配"] = True
                selected_island["玩家信息"] = {
                    "player_uuid": player_uuid,
                    "player_name": player_name,
                    "方块包": [["基础方块包", 9999999]],
                }
                tp_x = selected_island["x"] + self._cfg["玩家传送坐标偏移"][0]
                tp_y = selected_island["y"] + self._cfg["玩家传送坐标偏移"][1]
                tp_z = selected_island["z"] + self._cfg["玩家传送坐标偏移"][2]
                self.game_ctrl.sendwocmd(f'/tp "{player_name}" {tp_x} {tp_y} {tp_z}')
                self.game_ctrl.sendwocmd(
                    f'/spawnpoint "{player_name}" {tp_x} {tp_y} {tp_z}'
                )
                self.Sky_Island_data = Sky_Island_data
                self.save_data(data_path)
                self.game_ctrl.say_to(player_name, self._cfg["分配成功提示"])
                self.get_players(None)

            except Exception as e:
                Print.print_err(f"空岛分配失败: {e}")
                self.game_ctrl.say_to(player_name, "§c分配过程中出现错误，请联系管理员")
                selected_island["是否分配"] = False
                selected_island["玩家信息"] = {
                    "player_uuid": None,
                    "player_name": None,
                    "方块包": ["基础方块包"],
                }

            return

        elif msg == self._cfg["回岛提示词"]:
            player_uuid = self.game_ctrl.players_uuid[player_name]
            data_path = os.path.join(self.data_path, "单方块空岛数据.json")
            with open(data_path, encoding="utf-8") as f:
                Sky_Island_data = json.load(f)

            for i in range(len(Sky_Island_data)):
                if Sky_Island_data[i]["玩家信息"]["player_uuid"] == player_uuid:
                    self.game_ctrl.sendwocmd(
                        f'/tp "{player_name}" {Sky_Island_data[i]["x"] + self._cfg["玩家传送坐标偏移"][0]} {Sky_Island_data[i]["y"] + self._cfg["玩家传送坐标偏移"][1]} {Sky_Island_data[i]["z"] + self._cfg["玩家传送坐标偏移"][2]}'
                    )
                    return

            self.game_ctrl.say_to(player_name, self._cfg["未分配提示"])
            return
        elif msg == self._cfg["方块包查询"]:
            player_uuid = self.game_ctrl.players_uuid.get(player_name)
            if not player_uuid:
                return

            island = None
            for data in self.Sky_Island_data:
                if data["玩家信息"]["player_uuid"] == player_uuid:
                    island = data
                    break

            if not island:
                self.game_ctrl.say_to(player_name, self._cfg["未分配提示"])
                return

            valid_packages = [
                (pkg[0], pkg[1]) for pkg in island["玩家信息"]["方块包"] if pkg[1] > 0
            ]
            if not valid_packages:
                self.game_ctrl.say_to(player_name, self._cfg["无方块包提示"])
                return

            messages = [self._cfg["查询提示标题"]]
            for pkg_name, count in valid_packages:
                messages.append(
                    self._cfg["方块包条目格式"].format(
                        package_name=pkg_name, count=count
                    )
                )

            for msg_line in messages:
                self.game_ctrl.say_to(player_name, msg_line)

            return
        """
        elif msg == self._cfg["交易所触发词"]:
            self.game_ctrl.say_to(player_name, self.exchange_menu_head)
            self.game_ctrl.say_to(player_name, "1.发布商品\n2.查看商品\n3.移除商品\nq.取消")
            player_uuid = self.game_ctrl.players_uuid.copy().get(player_name)
            while True:
                choice = game_utils.waitMsg(player_name)
                match choice:
                    case "1":
                        shop_add_item(self, player_name, player_uuid)
                        return
                    case "2":
                        shop_check(self, player_name, player_uuid)
                        return
                    case "3":
                        shop_remove_item(self, player_name, player_uuid)
                        return
                    case "q":
                        self.game_ctrl.say_to(player_name, "§c退出交易所。")
                        return

                    case None:
                        self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                        return

                self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入")

        """

        msg = msg.split()  # type: ignore
        if len(msg) == 4 and msg[0] == self._cfg["方块包添加"]:
            package_name = msg[1]
            password = msg[2]
            try_count = msg[3]
            if (
                package_name in self._cfg["方块包"]
                and password == self._cfg["方块包添加密码"]
            ):
                try:
                    add_count = int(try_count)
                    if add_count <= 0:
                        raise ValueError

                except ValueError:
                    self.game_ctrl.say_to(player_name, self._cfg["方块包添加失败提示"])
                    return

                player_uuid = self.game_ctrl.players_uuid.get(player_name)
                if not player_uuid:
                    return

                is_updated = False
                for island in self.Sky_Island_data:
                    if island["玩家信息"]["player_uuid"] == player_uuid:
                        for pkg in island["玩家信息"]["方块包"]:
                            if pkg[0] == package_name and pkg[1] >= 0:
                                pkg[1] += add_count
                                is_updated = True
                                break

                        else:
                            island["玩家信息"]["方块包"].append(
                                [package_name, add_count]
                            )
                            is_updated = True

                        break

                if not is_updated:
                    self.game_ctrl.say_to(player_name, self._cfg["未分配提示"])
                    return

                self.save_data(os.path.join(self.data_path, "单方块空岛数据.json"))
                self.get_players(None)
                current_count = next(
                    (
                        pkg[1]
                        for pkg in island["玩家信息"]["方块包"]
                        if pkg[0] == package_name
                    ),
                    add_count,
                )
                self.game_ctrl.say_to(
                    player_name,
                    f"{self._cfg['方块包添加成功提示']} 当前 {package_name} 剩余次数: {current_count}",
                )

            else:
                self.game_ctrl.say_to(player_name, self._cfg["方块包添加失败提示"])

    def get_players(self, player_name):
        # 尝试重新加载数据
        data_path = os.path.join(self.data_path, "单方块空岛数据.json")
        try:
            with open(data_path, encoding="utf-8") as f:
                self.Sky_Island_data = json.load(f)

        except:  # noqa: E722
            try:
                with open(self.data_path_bat, encoding="utf-8") as f:
                    self.Sky_Island_data = json.load(f)
                self.save_data(data_path)

            except:  # noqa: E722
                return

        self.players = []
        self.player_island_map.clear()
        # 构建玩家UUID到岛屿的映射
        for island in self.Sky_Island_data:
            if island["是否分配"] and island["玩家信息"]["player_uuid"]:
                uuid = island["玩家信息"]["player_uuid"]
                self.player_island_map[uuid] = island

        # 获取在线玩家信息
        players = self.frame.get_players().getAllPlayers()
        players = [p.name for p in players if p.name != self.game_ctrl.bot_name]

        for player in players:
            uuid = self.game_ctrl.players_uuid.get(player)
            if not uuid:
                continue

            island = self.player_island_map.get(uuid)
            if island:
                # 只收集仍有次数的方块包
                available_packages = [
                    pkg[0] for pkg in island["玩家信息"]["方块包"] if pkg[1] > 0
                ]
                if available_packages:
                    pos = (
                        island["x"] + self._cfg["单方块坐标偏移"][0],
                        island["y"] + self._cfg["单方块坐标偏移"][1],
                        island["z"] + self._cfg["单方块坐标偏移"][2],
                    )
                    self.players.append([available_packages, pos, player])

    def auto_setblock(self):
        while True:
            current_players = [
                p for p in self.game_ctrl.allplayers if p != self.game_ctrl.bot_name
            ]
            for player in current_players:
                uuid = self.game_ctrl.players_uuid.get(player)
                if not uuid:
                    continue

                island = self.player_island_map.get(uuid)
                if not island or not island["是否分配"]:
                    continue

                available_packages = [
                    pkg for pkg in island["玩家信息"]["方块包"] if pkg[1] > 0
                ]
                if not available_packages:
                    continue
                selected_pkg = random.choice(available_packages)
                block_list = self.block_package.get(selected_pkg[0], [])
                if block_list:
                    block = random.choice(block_list)
                    x = island["x"] + self._cfg["单方块坐标偏移"][0]
                    y = island["y"] + self._cfg["单方块坐标偏移"][1]
                    z = island["z"] + self._cfg["单方块坐标偏移"][2]
                    flag = game_utils.isCmdSuccess(
                        f"/setblock {x} {y} {z} {block[0]} {block[1]} keep"
                    )
                    if flag:
                        selected_pkg[1] -= 1

            time.sleep(self._cfg["方块更新周期(秒)"])

    def auto_save_data(self):
        data_path = os.path.join(self.data_path, "单方块空岛数据.json")
        while True:
            time.sleep(self._cfg["自动保存时间（秒）"])
            self.save_data(data_path)


entry = plugin_entry(airisland)
