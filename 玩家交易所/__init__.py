from tooldelta import (
    Plugin,
    Config,
    game_utils,
    utils,
    Print,
    TYPE_CHECKING,
    Chat,
    plugin_entry,
)

from data_operation import save_data, load_data
import os, time


class NewPlugin(Plugin):
    name = "玩家交易所"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        config = {
            "交易所触发词": "玩家交易所",
            "交易所菜单头": "§b>>>>>>>>玩家交易所<<<<<<<<\n§b>>>>>>>>手续费{手续费}  <<<<<<<<",
            "使用计分板": "coin",
            "提交商品": "提交商品",
            "交易手续费": 0.1,
            "手续费起收金额": 0,
        }
        self.config, _ = Config.get_plugin_config_and_version(
            self.name, {}, config, self.version
        )
        self.menu_head = self.config["交易所菜单头"].format(
            手续费=self.config["交易手续费"]
        )
        self._data_path = os.path.join(self.data_path, "商品列表.json")
        self.shops = load_data(self._data_path)
        self.ListenActive(self.on_inject)
        self.ListenChat(self.on_player_message)

    def on_player_message(self, chat: Chat):
        player_name = chat.player.name
        msg = chat.msg

        if msg.startswith(self.config["交易所触发词"]):
            self.game_ctrl.say_to(player_name, self.menu_head)
            self.game_ctrl.say_to(
                player_name, "1.发布商品\n2.查看商品\n3.移除商品\nq.取消"
            )
            player_uuid = self.game_ctrl.players_uuid.copy().get(player_name)
            while True:
                choice = game_utils.waitMsg(player_name)
                match choice:
                    case "1":
                        self.add_shop(player_name, player_uuid)
                        return
                    case "2":
                        self.check_shop(player_name, player_uuid)
                        return
                    case "3":
                        self.remove_shop(player_name, player_uuid)
                        return
                    case "q":
                        self.game_ctrl.say_to(player_name, "§c退出交易所。")
                        return

                    case None:
                        self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                        return

                self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入")

    def add_shop(self, player_name, player_uuid):
        if player_uuid in self.shops:
            self.game_ctrl.say_to(player_name, "§c你已经发布过商品，请先取消发布商品。")
            return

        pos = game_utils.getPosXYZ(player_name)
        self.game_ctrl.say_to(player_name, "§b请输入商品价格：")
        while True:
            price = game_utils.waitMsg(player_name)
            if price is None:
                self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                return

            if price.isdigit():
                price = int(price)
                if price < 0:
                    self.game_ctrl.say_to(player_name, "§c价格不能为负数，请重新输入")
                    continue
                self.game_ctrl.say_to(player_name, f"§b请输入商品名称")
                shop_name = game_utils.waitMsg(player_name)
                if shop_name is None:
                    self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                    return

                self.game_ctrl.say_to(player_name, f"§b请输入商品描述")
                shop_desc = game_utils.waitMsg(player_name)
                if shop_desc is None:
                    self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                    return

                self.game_ctrl.say_to(
                    player_name,
                    f"请在30秒内将商品扔在坐标{int(pos[0])} {int(pos[1])} {int(pos[2])}处，然后发送 {self.config['提交商品']} ，输入q取消",
                )
                while True:
                    tip = game_utils.waitMsg(player_name)
                    if tip == self.config["提交商品"]:
                        shop_list = self.game_ctrl.sendwscmd_with_resp(
                            f"/testfor @e[x={pos[0]}, y={pos[1]}, z={pos[2]}, r = 1, type=!player]"
                        ).as_dict
                        shop_list = shop_list.get("OutputMessages")[0].get("Parameters")  # type: ignore
                        if shop_list == []:
                            self.game_ctrl.say_to(player_name, "§c没有找到商品。")
                            return

                        self.game_ctrl.sendwocmd(
                            f"/structure save {player_name} {pos[0]} {pos[1]} {pos[2]} {pos[0]} {pos[1]} {pos[2]}"
                        )

                        self.shops[player_uuid] = {
                            "player_name": player_name,
                            "shopname": shop_name,
                            "shopdesc": shop_desc,
                            "shopprice": price,
                            "structure": player_name,
                            "item": "",
                        }
                        for i in shop_list:
                            self.shops[player_uuid]["item"] += i

                        save_data(self._data_path, self.shops)

                        rawtext = '{"rawtext": [{"text": "' + self.menu_head + '"}]}'
                        self.game_ctrl.sendwocmd(f"/tellraw @a {rawtext}")
                        rawtext = (
                            '{"rawtext": [{"text": "§b'
                            + player_name
                            + " §f发布了商品 §b"
                            + shop_name
                            + "§f，价格为 §b"
                            + str(price)
                            + " §f。其中包含物品：§b"
                            + f"{shop_list}"
                            + '"}]}'
                        )
                        self.game_ctrl.sendwocmd(f"/tellraw @a {rawtext}")
                        self.game_ctrl.sendwocmd(
                            f"/kill @e [type =! player, x = {int(pos[0])}, y = {int(pos[1])}, z = {int(pos[2])}, r = 1]"
                        )
                        return
                    if tip is None:
                        self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                        return

                    if tip == "q":
                        self.game_ctrl.say_to(player_name, "§c取消发布商品。")
                        return

                    else:
                        self.game_ctrl.say_to(player_name, "§c请重新输入（输入q取消）")
            else:
                self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入")

    def remove_shop(self, player_name, player_uuid):
        self.game_ctrl.say_to(player_name, self.menu_head)
        if player_uuid in self.shops:
            pos = game_utils.getPosXYZ(player_name)
            self.game_ctrl.say_to(
                player_name, f"§a已为您删除 §b{self.shops[player_uuid]['shopname']}"
            )
            self.game_ctrl.sendwocmd(
                f"/structure load {self.shops[player_uuid]['structure']} {int(pos[0])} {int(pos[1])} {int(pos[2])}"
            )
            del self.shops[player_uuid]
            save_data(self._data_path, self.shops)
            return
        self.game_ctrl.say_to(player_name, "§c删除失败：您未上架任何商品")
        return

    def check_shop(self, player_name, player_uuid):
        self.game_ctrl.say_to(player_name, self.menu_head)
        if self.shops == {}:
            self.game_ctrl.say_to(player_name, "§c没有商品上架。")
            return

        temp = []
        count = 1
        for k, v in self.shops.items():
            temp.append(k)
            self.game_ctrl.say_to(
                player_name,
                f"{count}. 出售玩家：{v['player_name']} 商品名字：{v['shopname']} 价格：{v['shopprice']} 商品描述：{v['shopdesc']} 商品包含内容：{v['item']}",
            )
            count += 1

        while True:
            self.game_ctrl.say_to(player_name, "§b请输入要购买的商品编号，输入q退出")
            choice = game_utils.waitMsg(player_name)
            if choice is None:
                self.game_ctrl.say_to(player_name, "§c超时退出。")
                return

            if choice == "q":
                self.game_ctrl.say_to(player_name, "§c退出交易所。")
                return

            if choice.isdigit() and int(choice) in range(1, count + 1):
                choice = int(choice)
                break

            else:
                self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入")

        self.buy_shop(player_name, player_uuid, temp[choice - 1])

    def buy_shop(self, player_name, player_uuid, target_player):
        self.game_ctrl.say_to(player_name, self.menu_head)
        try:
            score = game_utils.getScore(self.config["使用计分板"], player_name)
        except:
            score = 0

        if score < self.shops[target_player]["shopprice"]:  # 这里正确使用 target_player
            self.game_ctrl.say_to(
                player_name, f"§c你的{self.config['使用计分板']}不足，购买失败"
            )
            return
        pos = game_utils.getPosXYZ(player_name)
        pos = (int(pos[0]), int(pos[1]), int(pos[2]))

        # 修复点1：使用 target_player 访问商家结构
        self.game_ctrl.sendwocmd(
            f"/structure load {self.shops[target_player]['structure']} {int(pos[0])} {int(pos[1])} {int(pos[2])}"
        )  # 改为 target_player

        # 修复点2：使用 target_player 的商店价格
        self.game_ctrl.sendwocmd(
            f"/scoreboard players remove {player_name} {self.config['使用计分板']} {self.shops[target_player]['shopprice']}"
        )

        time.sleep(0.1)

        # 修复点3：删除商家结构时使用 target_player
        self.game_ctrl.sendwocmd(
            f"/structure delete {self.shops[target_player]['structure']}"
        )

        self.game_ctrl.say_to(player_name, f"§a购买成功")
        wait_add = load_data(os.path.join(self.data_path, "wait_add.json"))
        money = self.shops[target_player]["shopprice"]
        money *= 1 - self.config["交易手续费"]
        money = int(money)
        wait_add[target_player] = [player_name, money]
        save_data(os.path.join(self.data_path, "wait_add.json"), wait_add)

        # 修复点4：删除商家数据时使用 target_player
        del self.shops[target_player]
        save_data(self._data_path, self.shops)

    def sale_check(self):
        while True:
            players = self.game_ctrl.players_uuid
            wait_add = load_data(os.path.join(self.data_path, "wait_add.json"))
            if wait_add:
                for k, v in players.items():
                    if v in wait_add:
                        target_player, money = wait_add[v]
                        self.game_ctrl.say_to(
                            k,
                            f"{target_player} 购买了你的商品，扣除手续费后你获得 {money} {self.config['使用计分板']}",
                        )
                        self.game_ctrl.sendwocmd(
                            f"/scoreboard players add {k} {self.config['使用计分板']} {money}"
                        )
                        del wait_add[v]
                        save_data(
                            os.path.join(self.data_path, "wait_add.json"), wait_add
                        )
            time.sleep(3)

    def on_inject(self):
        utils.createThread(self.sale_check, (), usage="售卖检测")


entry = plugin_entry(NewPlugin)
