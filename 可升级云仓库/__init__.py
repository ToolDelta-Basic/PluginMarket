from tooldelta import Plugin, game_utils, utils, plugin_entry, Chat, cfg, Player
from tooldelta.utils import tempjson
import os
import shutil

class NewPlugin(Plugin):
    name = "玩家仓库系统"
    author = "Ka3mora"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.storage_file = os.path.join(self.data_path, "player_storage.json")
        self.allowed_items_file = os.path.join(self.data_path, "data.json")
        self.storage = self.load_storage()
        self.allowed_items = self.load_allowed_items()
        self.warehouse_levels = [1000, 2500, 5000, 8000, 15000, 30000, 60000, 100000] #仓库等级对应的容量
        self.upgrade_costs = [500, 1000, 2000, 8000, 14000, 50000, 100000] #升级仓库所需的费用
        self.ListenChat(self.on_chat)
        plugin_folder = os.path.dirname(__file__)
        source_file = os.path.join(plugin_folder, "data.json")
        destination_folder = self.data_path
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)
        destination_file = os.path.join(destination_folder, os.path.basename(source_file))
        shutil.copy(source_file, destination_file)
        config = {
            "储存触发词": "。储存",
            "查库存触发词": "。仓库清单",
            "取物品触发词": "。取出",
            "升级仓库触发词": "。升级仓库",
            "链接货币计分板": "货币",
            "货币名称": "U币"
        }
        self.config, version = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(config), config, self.version
        )
        if version != self.version:
            cfg.upgrade_plugin_config(self.name, self.config, self.version)

    def load_storage(self):
        return tempjson.load_and_read(self.storage_file, need_file_exists=False, default={})
    
    def load_allowed_items(self):
        return tempjson.load_and_read(self.allowed_items_file, need_file_exists=False, default={})

    def save_storage(self):
        tempjson.load_and_write(self.storage_file, self.storage)
        tempjson.flush(self.storage_file)

    def on_chat(self, chat: Chat):
        player_name = chat.player.name
        message = chat.msg
        save_item = self.config["储存触发词"]
        item_list = self.config["查库存触发词"]
        take_off_item = self.config["取物品触发词"]
        upgrade_with_coin = self.config["升级仓库触发词"]

        if message == save_item:
            self.store_item(player_name)
        elif message == item_list:
            self.show_warehouse(player_name)
        elif message == take_off_item:
            self.withdraw_item(player_name)
        elif message == upgrade_with_coin:
            self.upgrade_warehouse(player_name)

    def store_item(self, player_name):
        if player_name not in self.storage:
            self.storage[player_name] = {"level": 1, "items": {}}

        self.game_ctrl.say_to(player_name, "§4§l·§a§l请输入要储存的物品名称：")
        item_name = game_utils.waitMsg(player_name, timeout=20)
        if not item_name:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l操作超时，取消储存")
            return

        item_name = item_name.strip()
        if item_name not in self.allowed_items:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l该物品未支持和禁止储存")
            return

        item_id = self.allowed_items[item_name]
        self.game_ctrl.say_to(player_name, f"§4§l·§a§l请输入要储存的 {item_name} 的数量：")
        item_count = game_utils.waitMsg(player_name, timeout=20)
        if not item_count or not item_count.isdigit() or int(item_count) <= 0:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l无效的数量，取消储存")
            return

        item_count = int(item_count)
        player_storage = self.storage[player_name]
        storage_key = f"{item_name}"

        player_item_count = game_utils.getItem(player_name, item_id, 0) #检查玩家背包物品够不够
        if player_item_count < item_count:
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l您背包中的 {item_name} 数量不足，无法储存 {item_count} 个。您当前有 {player_item_count} 个。")
            return

        current_capacity = sum(player_storage["items"].values()) #检查是否超出最大容量
        new_capacity = current_capacity + item_count
        max_capacity = self.warehouse_levels[player_storage["level"] - 1]

        if new_capacity > max_capacity:
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l您的仓库容量已满，无法储存更多物品！当前容量：{current_capacity}/{max_capacity}")
            return

        if storage_key in player_storage["items"]:
            player_storage["items"][storage_key] += item_count
        else:
            player_storage["items"][storage_key] = item_count

        self.save_storage()
        self.game_ctrl.sendwocmd(f"clear {player_name} {item_id} 0 {item_count} ")
        self.game_ctrl.say_to(player_name, f"§4§l·§a§l已储存 {item_count} 个 {item_name}")


    def show_warehouse(self, player_name):
        if player_name not in self.storage:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l您的仓库为空")
            return

        player_storage = self.storage[player_name]
        level = player_storage["level"]
        items = player_storage["items"]
        max_capacity = self.warehouse_levels[level - 1]
        current_capacity = sum(items.values())

        self.game_ctrl.say_to(player_name, f"§4§l·§a§l您的仓库等级为 {level}，当前容量：{current_capacity}/{max_capacity}")
        self.game_ctrl.say_to(player_name, "§4§l·§a§l仓库中的物品：")
        for idx, (item_name, item_count) in enumerate(items.items(), start=1):
            self.game_ctrl.say_to(player_name, f"{idx}. {item_name} x{item_count}")

    def withdraw_item(self, player_name):
        if player_name not in self.storage or not self.storage[player_name]["items"]:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l您的仓库为空")
            return

        player_storage = self.storage[player_name]
        items = player_storage["items"]

        self.game_ctrl.say_to(player_name, "§4§l·§a§l请选择要取出的物品序号：")
        for idx, (item_name, item_count) in enumerate(items.items(), start=1):
            self.game_ctrl.say_to(player_name, f"{idx}. {item_name} x{item_count}")

        choice = game_utils.waitMsg(player_name, timeout=20)
        if not choice or not choice.isdigit() or int(choice) < 1 or int(choice) > len(items):
            self.game_ctrl.say_to(player_name, "§4§l·§a§l无效的序号，操作取消")
            return

        item_name = list(items.keys())[int(choice) - 1]
        item_count = items[item_name]

        self.game_ctrl.say_to(player_name, f"§4§l·§a§l您选择了 {item_name}，请输入要取出的数量：")
        amount = game_utils.waitMsg(player_name, timeout=20)
        if not amount or not amount.isdigit() or int(amount) < 1 or int(amount) > item_count:
            self.game_ctrl.say_to(player_name, "§4§l·§a§l无效的数量，操作取消")
            return

        amount = int(amount)
        items[item_name] -= amount
        if items[item_name] <= 0:
            del items[item_name]

        self.save_storage()
        item_id = self.allowed_items[item_name]
        self.game_ctrl.sendwocmd(f"give {player_name} {item_id} {amount}")
        self.game_ctrl.say_to(player_name, f"§4§l·§a§l已取出 {amount} 个 {item_name}")

    def upgrade_warehouse(self, player_name):
        if player_name not in self.storage:
            self.storage[player_name] = {"level": 1, "items": {}}
            self.save_storage()

        player_storage = self.storage[player_name]
        current_level = player_storage["level"]
        if current_level >= len(self.warehouse_levels):
            self.game_ctrl.say_to(player_name, "§4§l·§a§l您的仓库已经是最高级")
            return

        next_level = current_level + 1
        cost = self.upgrade_costs[current_level - 1]
        scoreboard_name = self.config["链接货币计分板"]
        current_money = game_utils.getScore(scoreboard_name, player_name)
        currency_name = self.config["货币名称"]

        self.game_ctrl.say_to(player_name, f"§4§l·§a§l升级仓库 {current_level} → {next_level} 需要 {cost} {currency_name}，您现有 {current_money} {currency_name}。输入 'y' 确认，'q' 取消")
        response = game_utils.waitMsg(player_name, timeout=20)
        if response.lower() != "y":
            self.game_ctrl.say_to(player_name, "§4§l·§a§l操作已取消")
            return

        if current_money < cost:
            self.game_ctrl.say_to(player_name, f"§4§l·§a§l您的 {currency_name} 不足，无法完成升级")
            return

        self.game_ctrl.sendwocmd(f"scoreboard players remove {player_name} {scoreboard_name} {cost}")
        player_storage["level"] = next_level
        self.save_storage()
        self.game_ctrl.say_to(player_name, f"§4§l·§a§l您的仓库已升级至 {next_level} 级，容量为 {self.warehouse_levels[next_level - 1]}")

entry = plugin_entry(NewPlugin)