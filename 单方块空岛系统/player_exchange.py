from data_operation import load_data, save_data
from tooldelta import game_utils
import time, os  # noqa: E401
def shop_add_item(self, player_name, player_uuid):
    shop_path = os.path.join(self.data_path, "shops.json")
    shops = load_data(shop_path)
    if player_uuid in shops:
        self.game_ctrl.say_to(player_name, "§c你已经发布过商品，请先取消发布商品。")
        return

    island_pos = get_player_island_pos(self, player_uuid)
    if island_pos is None:
        self.game_ctrl.say_to(player_name, "§c你还没有空岛，请先创建。")
        return

    now_pos = game_utils.getPosXYZ(player_name)
    now_pos = (int(now_pos[0]), int(now_pos[1]), int(now_pos[2]))
    if abs(now_pos[0] - island_pos[0] > 500) or abs(now_pos[2] - island_pos[2] > 500):
        self.game_ctrl.say_to(player_name, "§c你当前不在空岛内，请先进入空岛。")
        return

    self.game_ctrl.say_to(player_name, "§b请输入商品名称：")
    while True:
        shop_name = game_utils.waitMsg(player_name)
        if shop_name is None:
            self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
            return

        self.game_ctrl.say_to(player_name, "§b请输入商品价格：")
        price = game_utils.waitMsg(player_name)
        if price is None:
            self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
            return

        if price.isdigit():
            price = int(price)
            if price < 0:
                self.game_ctrl.say_to(player_name, "§c价格不能为负数，请重新输入")
                continue

            self.game_ctrl.say_to(player_name, "§b请输入商品描述")
            shop_desc = game_utils.waitMsg(player_name)
            if shop_desc is None:
                self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
                return

        break
    self.game_ctrl.say_to(player_name, f"§b当前商品坐标为：{now_pos[0]}, {now_pos[1]}, {now_pos[2]} 使用此坐标请输入“y”，使用其他坐标请自定义输入，格式为 x y z,输入 q 退出。")
    while True:
        temp = game_utils.waitMsg(player_name)
        if temp is None:
            self.game_ctrl.say_to(player_name, "§c超时退出交易所。")
            return

        if temp.lower() == "y" or temp.lower() == "yes":
            break

        if temp.lower() =="q" or temp.lower() == "quit":
            self.game_ctrl.say_to(player_name, "§c已退出交易所。")
            return

        temp = temp.split()
        if len(temp) == 3:
            if temp[0].isdigit() and temp[1].isdigit() and temp[2].isdigit():
                if abs(int(temp[0]) - island_pos[0]) > 500 or  abs(int(temp[2]) - island_pos[2]) > 500: # type: ignore
                    temp = (int(temp[0]), int(temp[1]), int(temp[2]))
                    self.game_ctrl.say_to(player_name, "§c输入的坐标不在自己空岛内，请重新输入")
                    continue
                else:
                    now_pos = temp
                    break

            else:
                self.game_ctrl.say_to(player_name, "§c格式错误，请重新输入")
                continue

        self.game_ctrl.say_to(player_name, "§c请重新输入。")

    nbt = self.get_structure.get_structure(now_pos, (1, 1, 1)).get_block((0, 0, 0))
    block_name = nbt.name
    if block_name != "minecraft:air":
        self.game_ctrl.say_to(player_name, "§c选定的位置已经有方块")
        return

    self.game_ctrl.sendwocmd(f"/setblock {now_pos[0]} {now_pos[1]} {now_pos[2]} chest")
    self.game_ctrl.say_to(player_name, f"请在30秒内将商品位于放入{now_pos[0]} {now_pos[1]} {now_pos[2]} 的箱子内，然后发送 {self._cfg['提交商品']} ，输入q取消")
    while True:
        msg = game_utils.waitMsg(player_name, 30)
        if msg is None:
            self.game_ctrl.say_to(player_name, "§c超时，关闭交易所。")
            self.game_ctrl.sendwocmd(f"/setblock {now_pos[0]} {now_pos[1]} {now_pos[2]} air destroy")
            return

        if msg == "q":
            self.game_ctrl.say_to(player_name, "§c关闭交易所。")
            self.game_ctrl.sendwocmd(f"/setblock {now_pos[0]} {now_pos[1]} {now_pos[2]} air destroy")
            return

        if msg == self._cfg["提交商品"]:
            break

        else:
            self.game_ctrl.say_to(player_name, "§c输入错误，请重新输入。")

    structure_name = player_name
    self.game_ctrl.sendwocmd(f'/structure save "{structure_name}" {now_pos[0]} {now_pos[1]} {now_pos[2]} {now_pos[0]} {now_pos[1]} {now_pos[2]}')
    nbt = self.get_structure.get_structure(now_pos, (1, 1, 1)).get_block((0, 0, 0))
    block_name = nbt.name
    block_nbt = nbt.metadata["Items"]
    self.game_ctrl.sendwocmd(f"/setblock {now_pos[0]} {now_pos[1]} {now_pos[2]} air")
    if block_name != "minecraft:chest":
        self.game_ctrl.say_to(player_name, "§c错误的商品类型")
        return

    item_data = []
    for item in block_nbt:
        try:
            item_data.append([item["Block"]['name'].replace('minecraft:', ''), item['Count']])  # noqa: Q000

        except:  # noqa: E722
            item_data.append([item['Name'].replace('minecraft:', ''), item['Count']])  # noqa: Q000

    shops = load_data(shop_path)
    shops[player_uuid] = {
                            "player_name": player_name,
                            "shopname": shop_name,
                            "shopdesc": shop_desc,
                            "shopprice": price,
                            "structure": structure_name,
                            "item": item_data
                        }
    save_data(shop_path, shops)
    shop_list = "§b"
    for item in item_data:
        shop_list += f"§b{item[0]} §fx §e{item[1]}§f, "

    rawtext = "{\"rawtext\": [{\"text\": \"" + self.exchange_menu_head + "\"}]}"  # noqa: Q003
    self.game_ctrl.sendwocmd(f'/tellraw @a {rawtext}')  # noqa: Q000
    rawtext = "{\"rawtext\": [{\"text\": \"§b" + player_name + " §f发布了商品 §b" + shop_name + "§f，价格为 §b" + str(price) + " §f。其中包含物品：§b" + f"{shop_list}" + "\"}]}"  # noqa: Q003
    self.game_ctrl.sendwocmd(f'/tellraw @a {rawtext}')  # noqa: Q000
    return
def shop_check(self, player_name, player_uuid):
    shop_path = os.path.join(self.data_path, "shops.json")
    shops = load_data(shop_path)
    uuids = list(shops.keys())
    if not uuids:
        self.game_ctrl.say_to(player_name, "§c没有商品。")
        return

    page_size = 5
    total_pages = (len(uuids) + page_size - 1) // page_size
    temp = [uuids[i*page_size : (i+1)*page_size] for i in range(total_pages)]
    current_page = 0
    while True:
        self.game_ctrl.say_to(player_name, f"§a=== 第 {current_page + 1}/{total_pages} 页商品 ===")
        for idx, shop_uuid in enumerate(temp[current_page], 1):
            shop_data = shops[shop_uuid]
            item_list = " ".join([f"§b{item[0]}§fx§e{item[1]}" for item in shop_data["item"]])
            self.game_ctrl.say_to(
                player_name,
                f"§6{idx}. {shop_data['shopname']}§f | 价格: §a{shop_data['shopprice']}§f | 描述: §7{shop_data['shopdesc']}§f\n包含物品: {item_list}"
            )
            self.game_ctrl.say_to(player_name, "§f")

        self.game_ctrl.say_to(player_name, "§e输入： '+'下一页，'-'上一页，'q'退出。输入商品序号可购买: ")
        choice = game_utils.waitMsg(player_name, 30)
        if choice is None:
            self.game_ctrl.say_to(player_name, "§c超时退出浏览。")
            return
        choice = choice.strip().lower()
        if choice == "+":
            current_page = min(current_page + 1, total_pages - 1)

        elif choice == "-":
            current_page = max(current_page - 1, 0)

        elif choice == "q":
            self.game_ctrl.say_to(player_name, "§a已退出商店浏览。")
            return

        elif choice.isdigit():
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(temp[current_page]):
                selected_uuid = temp[current_page][choice_idx]
                break

            else:
                self.game_ctrl.say_to(player_name, "§c请输入当前页的有效序号！")

        else:
            self.game_ctrl.say_to(player_name, "§c无效输入，请按提示操作！")

    shop = shops[selected_uuid]
    price = shop["shopprice"]
    structure = shop["structure"]
    self.game_ctrl.say_to(player_name, self.exchange_menu_head)
    try:
        money = game_utils.getScore(self._cfg["使用计分板"], player_name)

    except:  # noqa: E722
        money = 0

    if money < price:
        self.game_ctrl.say_to(player_name, f"§c你的{self._cfg['使用计分板']}不足，购买失败")
        return

    island_pos = get_player_island_pos(self, player_uuid)
    player_pos = game_utils.getPosXYZ(player_name)
    if not island_pos:
        self.game_ctrl.say_to(player_name, "§c你还没有空岛，无法购买")
        return

    if abs(island_pos[0] - player_pos[0]) > 500 or abs(island_pos[2] - player_pos[2]) > 500:
        self.game_ctrl.say_to(player_name, "§c请在自己的空岛上购买商品")
        return

    self.game_ctrl.say_to(player_name, f"§a你花费了{price}个{self._cfg['使用计分板']}，购买成功")
    self.game_ctrl.sendwocmd(f'/structure load "{structure}" {player_pos[0]} {player_pos[1]} {player_pos[2]}')
    self.game_ctrl.sendwocmd(f'/scoreboard players remove "{player_name}" {self._cfg["使用计分板"]} {price}')
    self.game_ctrl.sendwocmd(f'/structure delete "{structure}"')
    exchange_staus = load_data(os.path.join(self.data_path, "购买状态监测.json"))
    exchange_staus[selected_uuid] = [player_name, price]
    save_data(os.path.join(self.data_path, "购买状态监测.json"), exchange_staus)
    shop_data = load_data(shop_path)
    shop_data.pop(selected_uuid)
    save_data(shop_path, shop_data)
def shop_remove_item(self, player_name, player_uuid):
    shop_path = os.path.join(self.data_path, "shops.json")
    shop = load_data(shop_path)
    if not shop[player_uuid]:
        self.game_ctrl.say_to(player_name, "§c你还没有发布商品。")
        return

    player_pos = game_utils.getPosXYZ(player_name)
    island_pos = get_player_island_pos(self, player_uuid)
    if not island_pos:
        self.game_ctrl.say_to(player_name, "§c你还没有空岛，无法下架商品")
        return

    if abs(island_pos[0] - player_pos[0]) > 500 or abs(island_pos[2] - player_pos[2]) > 500:
        self.game_ctrl.say_to(player_name, "§c你只能在自己的空岛上下架商品")
        return

    structure = shop[player_uuid]["structure"]
    self.game_ctrl.sendwocmd(f'/structure load "{structure}" {player_pos[0]} {player_pos[1]} {player_pos[2]}')
    self.game_ctrl.sendwocmd(f'/structure delete "{structure}"')
    self.game_ctrl.sendwocmd(f"/setblock {int(player_pos[0])} {int(player_pos[1])} {int(player_pos[2])} air destroy")
    shop.pop(player_uuid)
    save_data(shop_path, shop)
    self.game_ctrl.say_to(player_name, "§a已成功下架商品。")
def get_player_island_pos(self, player_uuid):
    for island in self.Sky_Island_data:
        if (island["是否分配"] and island["玩家信息"]["player_uuid"] == player_uuid):
            return (island["x"] + self._cfg["玩家传送坐标偏移"][0], island["y"] + self._cfg["玩家传送坐标偏移"][1], island["z"] + self._cfg["玩家传送坐标偏移"][2])

    return None

def sale_check(self):
    while True:
        players = self.game_ctrl.players_uuid
        wait_add = load_data(os.path.join(self.data_path, "购买状态监测.json"))
        if wait_add:
            for k, v in players.items():
                if v in wait_add:
                    target_player, money = wait_add[v]
                    money = int(money - money * self._cfg["交易手续费"])
                    while True:
                        flag = game_utils.isCmdSuccess(f'/testfor "{k}"')
                        if flag:
                            break
                        else:
                            time.sleep(1)

                    self.game_ctrl.say_to(k, f"{target_player} 购买了你的商品，扣除手续费后你获得 {money} {self._cfg['使用计分板']}")
                    self.game_ctrl.sendwocmd(f'/scoreboard players add "{k}" {self._cfg["使用计分板"]} {money}')
                    del wait_add[v]
                    save_data(os.path.join(self.data_path, "购买状态监测.json"), wait_add)

        time.sleep(5)
