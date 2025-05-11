import math
import os
import uuid
from tooldelta import (
    Plugin,
    plugin_entry,
    Player,
    cfg,
    utils,
    TYPE_CHECKING,
)
from .shop_lib import Shop, Good, ShopPermission, ShopMember, ShopPlayerInfo


# 如果获取到的商店实例正在被另一个线程使用, 则优先返回正在被使用的商店的实例。
# 避免出现两个线程等在同时使用同一个商店的不同实例
# 而导致保存时数据被覆盖的问题。
class ShopGC:
    def __init__(self, shop: Shop):
        if shop.name in entry.active_shops:
            self.shop = entry.active_shops[shop.name]
            entry.active_shop_counter[shop.name] += 1
        else:
            self.shop = shop
            entry.active_shops[shop.name] = shop
            entry.active_shop_counter[shop.name] = 1

    def __enter__(self):
        return self.shop

    def __exit__(self, exc_type, exc_val, exc_tb):
        entry.active_shop_counter[self.shop.name] -= 1
        if entry.active_shop_counter[self.shop.name] == 0:
            del entry.active_shops[self.shop.name]
            del entry.active_shop_counter[self.shop.name]
        entry.save_shop_data(self.shop)


class BarrelShop(Plugin):
    name = "木桶玩家商店"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        os.makedirs(self.data_path / "商店数据", exist_ok=True)
        os.makedirs(self.data_path / "玩家数据", exist_ok=True)
        self.active_shops: dict[str, Shop] = {}
        self.active_shop_counter: dict[str, int] = {}
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        CFG_DEFAULT = {
            "货币计分板名": "金币",
            "货币称呼": "金币",
            "单商店最多可上架商品数": 40,
        }
        config, _ = cfg.get_plugin_config_and_version(
            self.name, cfg.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, self.version
        )
        self.money_scb_name = config["货币计分板名"]
        self.money_name = config["货币称呼"]
        self.max_slots = config["单商店最多可上架商品数"]

    def on_preload(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.style = self.GetPluginAPI("统一消息风格")
        self.intr = self.GetPluginAPI("前置-世界交互")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_统一消息风格 import OneStyleMsg
            from 前置_世界交互 import GameInteractive

            self.chatbar: ChatbarMenu
            self.style: OneStyleMsg
            self.intr: GameInteractive

    def on_active(self):
        self.chatbar.add_new_trigger(
            ["ps new"], [("店名", str, None)], "创建一个木桶商店", self.create_shop
        )
        self.chatbar.add_new_trigger(
            ["ps on"],
            [("商品", str, None), ("价格", int, None)],
            "将商品添加到商店",
            self.put_good,
        )
        self.chatbar.add_new_trigger(
            ["ps off"],
            [],
            "将商品从商店中移除",
            self.takeout_good,
        )
        self.chatbar.add_new_trigger(
            ["ps members"],
            [],
            "增减店员或设置店员权限",
            self.shop_set_permission,
        )
        self.chatbar.add_new_trigger(
            ["ps info"],
            [("商店名", str, None)],
            "查看商店信息",
            self.shop_check,
        )
        self.chatbar.add_new_trigger(
            ["ps take"],
            [],
            "从所属商店取走利润",
            self.shop_take_profit,
        )
        self.chatbar.add_new_trigger(
            ["ps buy"],
            [("商店名", str, "")],
            "进入商店并购买商品",
            self.shop_buy,
        )
        self.chatbar.add_new_trigger(
            ["ps logs"],
            [],
            "查看商店日志",
            self.shop_checklog,
        )

    def create_shop(self, player: Player, args):
        style = self.style(player)
        (shop_name,) = args
        if self.get_player_linked_shop_data(player) is not None:
            style.failed("你还没有创建一个商店")
            return
        elif self.shop_name_exists(shop_name):
            style.failed("商店名已存在")
            return
        elif not self.check_shopname(shop_name):
            style.failed("商店名不能包含特殊字符")
            return
        elif len(shop_name) not in range(2, 16):
            style.failed("商店名长度必须在 2-15 个字符之间")
            return
        shop_desc = ""
        while 1:
            shop_desc = style.input("请输入商店简介：")
            if shop_desc is None:
                style.failed("输入超时， 已取消创建商店")
                return
            if len(shop_desc) > 40:
                style.warn("简介不能超过 40 个字符")
                continue
            elif len(shop_desc) < 2:
                style.warn("简介不能低于 2 个字符")
                continue
            break
        shop = Shop.new(player, shop_name)
        shop.description = shop_desc
        self.save_player_linked_shop_data(
            player, ShopPlayerInfo(player.xuid, shop_name)
        )
        player.show(f"§a成功创建商店 {shop.name}")
        self.save_shop_data(shop)

    def put_good(self, player: Player, args):
        disp_name, price = args
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        with ShopGC(shop) as shop:
            if shop.player_permission(player) < ShopPermission.MEMBER:
                style.failed("你没有权限上架商品")
                return
            elif len(shop.goods) >= self.max_slots:
                style.failed(f"商店货架已满 （{self.max_slots} 个商品）")
                return
            if len(disp_name) > 20:
                style.failed("商品名字不能超过 20 个字符")
                return
            elif price < 0:
                style.failed("价格不能小于 0")
                return
            if shop.has_duplicated_name_good(disp_name):
                style.warn("商店内已有同名商品")
                style.warn("§6仍然确定上架吗 (§aY§7/§cN§6) ？请输入：")
                resp = player.input()
                if resp is not None and resp.upper() == "Y":
                    pass
                else:
                    style.info("已取消上架")
                    return
            dim, x, y, z = player.getPos()
            if dim != 0:
                style.failed("暂时无法其它维度上架商品")
                return
            x, y, z = int(x), int(y - 1), int(z)
            block = self.intr.get_block(x, y, z)
            if block.name != "minecraft:barrel":
                style.failed(f"请将商品放在脚底 （{x}, {y}, {z}） 的木桶内")
                return
            block_data = block.metadata["Items"]
            if not block_data:
                style.failed("木桶内至少需要有一件物品")
                return
            retries = 0
            while 1:
                try:
                    ud = uuid.uuid4().hex
                    is_suc = (
                        self.game_ctrl.sendwscmd_with_resp(
                            f"structure save {ud} {x} {y} {z} {x} {y} {z} false disk true",
                            timeout=5,
                        ).SuccessCount
                        > 0
                    )
                    if is_suc:
                        break
                except TimeoutError:
                    pass
                retries += 1
                style.warn(f"保存商品失败 （第 {retries} 次）")
                if retries > 5:
                    break
            if retries > 5:
                style.error("保存商品失败")
                return
            self.game_ctrl.sendwocmd(f"setblock {x} {y} {z} barrel 1")
            good = Good(disp_name, ud, price, block.metadata["Items"])
            shop += good
            shop.record_on(player, good)
            self.game_ctrl.sendwocmd(
                f"execute as {player.getSelector()} at @s run playsound random.levelup"
            )
            style.success("成功上架商品")

    def takeout_good(self, player: Player, _):
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        with ShopGC(shop) as shop:
            if shop.player_permission(player) < ShopPermission.MEMBER:
                style.failed("你没有权限下架商品")
                return
            dim, x, y, z = player.getPos()
            if dim != 0:
                style.failed("暂时无法其它维度下架商品")
                return
            x, y, z = int(x), int(y), int(z)
            block = self.intr.get_block(x, y - 1, z)
            if block.name != "minecraft:barrel":
                style.failed("请站在一个木桶上")
                return
            block_data = block.metadata
            if block_data["Items"]:
                style.failed("请先清空木桶内的物品")
                return
            if not shop.goods:
                style.failed("商店内没有商品")
                return
            section = style.select(
                "请选择需要下架的商品", shop.goods, lambda x: x.display_name
            )
            if section is None:
                style.failed("输入超时，已取消下架商品")
                return
            good = section
            # 防止在输入时 木桶发生变化
            block = self.intr.get_block(x, y - 1, z)
            if block.name != "minecraft:barrel":
                style.failed("请不要中途将木桶破坏掉")
                return
            res = self.game_ctrl.sendwscmd_with_resp(
                f"structure load {good.structure_id} {x} {y - 1} {z}"
            )
            if res.SuccessCount == 0:
                style.warn(
                    "下架商品失败： 商品结构名不存在， 有可能是因为租赁服被重置导致的"
                )
                style.warn("§6仍然确定下架吗 (§aY§7/§cN§6) ？请输入：")
                resp = player.input()
                if resp is not None and resp.lower() == "y":
                    pass
                else:
                    style.info("已取消下架该商品")
                    return
            self.game_ctrl.sendwocmd(f"structure delete {good.structure_id}")
            shop -= good
            shop.record_off(player, good)
            style.success("成功下架商品")

    def shop_take_profit(self, player: Player, _):
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        with ShopGC(shop) as shop:
            if shop.player_permission(player) < ShopPermission.ADMIN:
                style.failed("你没有权限收取商店利润")
                return
            if shop.profits < 1:
                style.info("没有利润可收取")
            else:
                getted_profits = math.ceil(shop.profits)
                self.game_ctrl.sendwocmd(
                    f"scoreboard players add {player.getSelector()} {self.money_scb_name} {getted_profits}"
                )
                shop -= getted_profits
                shop.record_profit_taken(player, getted_profits)
                style.success(f"§a已收取 §e{getted_profits} {self.money_name}")

    def shop_check(self, player: Player, _):
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        player.show("当前所在商店 §7>>>")
        player.show(f"  {shop.name} : {shop.disp_name}")
        player.show(f"  §7所有者： §f{shop.owner.name}")
        player.show(f"  §7掌柜： §f{'， '.join(admin.name for admin in shop.admins)}")
        player.show(
            f"  §7店员： §f{'， '.join(member.name for member in shop.members)}"
        )
        player.show(f"  §7利润： §e{shop.profits}")

    def shop_set_permission(self, player: Player, _):
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        with ShopGC(shop) as shop:
            sections = [(0, "邀请店员"), (1, "移除店员"), (2, "设置店员权限")]
            section = style.select("请选择需要操作的玩家", sections, lambda x: x[1])
            if section is None:
                style.failed("输入超时，已取消")
                return
            section = section[0]
            if section == 0:
                self.shop_invite(player)
            elif section == 1:
                self.shop_kick(player)
            elif section == 2:
                if shop.player_permission(player) < ShopPermission.ADMIN:
                    style.failed("你没有权限设置店员权限")
                    return
                members = shop.members + shop.admins
                if not members:
                    style.failed("商店内没有店员")
                    return
                section = style.select(
                    "请选择需要设置权限的店员",
                    members,
                    lambda x: f"{x.name} - {('店员', '管理员')[shop.player_permission(x) - 1]}",
                )
                if section is None:
                    style.failed("输入超时，已取消")
                    return
                section2 = style.select(
                    "请选择需要设置的权限",
                    [(ShopPermission.MEMBER, "店员"), (ShopPermission.ADMIN, "管理员")],
                    lambda x: x[1],
                )
                if section2 is None:
                    style.failed("输入超时，已取消")
                    return
                permission, permission_str = section2
                shop.change_permission(section, permission)
                style.success(f"成功设置店员 {section.name} 的权限为 {permission_str}")

    def shop_buy(self, player: Player, args):
        (shop_name,) = args
        style = self.style(player)
        if shop_name == "":
            avali_shop_names = self.get_all_shop_names()
            if not avali_shop_names:
                style.failed("市场上没有任何一家商店")
                return
            section = style.select("请选择商店", avali_shop_names, lambda x: x)
            if section is None:
                style.failed("输入超时，已取消")
                return
            shop_name = section
        while 1:
            shop = self.get_shop_data(shop_name)
            if shop is None:
                style.failed("商店不存在")
                return
            with ShopGC(shop) as shop:
                goods = shop.goods.copy()
                if not goods:
                    style.failed("商店内没有任何商品")
                    return
                section = style.select_meta(
                    "选择一个商品：",
                    goods,
                    lambda x: (x.display_name + " §r§7~ " + f"§e{x.price}"),
                    "输入 q 退出商店",
                    ("q",),
                )
                if section is None:
                    style.failed("输入超时，已取消")
                    return
                elif section == "q":
                    style.info(f"已离开商店 {shop_name}。")
                    return
                good = section
                price = section.price
                if price > (money := player.getScore(self.money_scb_name)):
                    style.failed(f"你的余额 ({money}{self.money_name}) 不足以购买该商品 ({price}{self.money_name})")
                    return
                del money
                dim, x, y, z = player.getPos()
                x, y, z = int(x), int(y) - 1, int(z)
                if dim != 0:
                    style.failed("请勿在非主世界区域使用本命令")
                    return
                block = self.intr.get_block(x, y, z)
                if block.name != "minecraft:barrel":
                    style.failed("请确保脚底是一个木桶")
                    return
                block_data = block.metadata
                if block_data["Items"]:
                    style.failed("木桶内已有物品，请先清空")
                    return
                self.remove_money_score(player, price)
                res = self.game_ctrl.sendwscmd_with_resp(
                    f"structure load {good.structure_id} {x} {y} {z}"
                )
                if res.SuccessCount == 0:
                    style.failed("商品购买失败 （结构不存在， 可能租赁服被重置）")
                    return
                shop -= good
                style.info(
                    "§b你有 2 分钟的时间检查商品， \n可在 2 分钟内输入 §6n§b 退货（请将商品归回原位）。\n输入 §ay §b确认购买。"
                )
                resp = player.input(timeout=120)
                if resp is None:
                    style.warn("2 分钟内仍未确认， 已视为确认购买。")
                    postback = False
                elif resp.lower() == "n":
                    block = self.intr.get_block(x, y, z)
                    slotsNBT = block.metadata["Items"]
                    if slotsNBT != good.slots_nbt:
                        style.failed("你未将商品正确归位， 视为确认购买。")
                        postback = False
                    else:
                        postback = True
                else:
                    postback = False
                    style.success(f"已购买 {good.display_name}。 交易愉快~")
                if postback:
                    self.game_ctrl.sendwocmd(f"setblock {x} {y} {z} barrel 1")
                    self.add_money_score(player, price)
                    style.success("已成功退货。")
                    shop += good
                else:
                    shop += price
                    self.game_ctrl.sendwocmd(f"structure delete {good.structure_id}")
                    shop.record_buy(player, good)

    def shop_invite(self, player: Player):
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        with ShopGC(shop) as shop:
            if shop.player_permission(player) < ShopPermission.ADMIN:
                style.failed("你没有权限邀店员")
            avail = [
                i
                for i in self.game_ctrl.players
                if shop.player_permission(i) < ShopPermission.MEMBER
            ]
            if not avail:
                style.failed("没有可邀请的玩家")
                return
            section = style.select(
                "请选择需要邀请的玩家",
                avail,
                lambda x: x.name,
            )
            if section is None:
                style.failed("输入超时，已取消")
                return
            elif (ld := self.get_player_linked_shop_data(section)) is not None:
                style.failed(f"该玩家已在另一个商店 {ld.in_shop_name} 中")
            shop += ShopMember.from_player(section)
            style.success(f"成功邀请店员 {section.name}")

    def shop_kick(self, player: Player):
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        with ShopGC(shop) as shop:
            if shop.player_permission(player) < ShopPermission.ADMIN:
                style.failed("你没有权限移除店员")
            avail = shop.admins + shop.members
            if not avail:
                style.failed("商店中没有店员")
                return
            section = style.select(
                "请选择需要踢出的店员",
                avail,
                lambda x: x.name,
            )
            if section is None:
                style.failed("输入超时，已取消")
                return
            elif shop.player_permission(section) >= shop.player_permission(player):
                style.failed("你没有权限移除该店员")
                return
            shop -= section
            style.success(f"成功移除店员 {section.name}")

    def shop_checklog(self, player: Player, _):
        style = self.style(player)
        shop = self.pretty_get_shop_data_from_player(player)
        if shop is None:
            return
        if shop.records == []:
            style.warn("商店没有日志")
            return
        style.info(f"商店 {shop.disp_name} 的日志：")
        records_r = list(reversed(shop.records))
        style.select_meta(
            "日志查看", records_r, lambda x: x.string(), "输入 q 退出", ("q",)
        )

    def get_player_linked_shop_data(self, player: Player):
        path = self.data_path / "玩家数据" / f"{player.xuid}.json"
        if not path.is_file():
            return None
        return ShopPlayerInfo.from_dict(utils.tempjson.load_and_read(str(path)))

    def save_player_linked_shop_data(self, player: Player, data: ShopPlayerInfo):
        path = str(self.data_path / "玩家数据" / f"{player.xuid}.json")
        utils.tempjson.load_and_write(
            path,
            data.to_dict(),
            need_file_exists=False,
        )
        utils.tempjson.flush(str(self.data_path / "玩家数据" / f"{player.xuid}.json"))

    def delete_player_linked_shop_data(self, player: Player, data: ShopPlayerInfo):
        path = str(self.data_path / "玩家数据" / f"{player.xuid}.json")
        utils.tempjson.unload_to_path(path)
        os.remove(path)

    def get_all_shop_names(self):
        return [
            i.removesuffix(".json") for i in os.listdir(self.data_path / "商店数据")
        ]

    def get_shop_data(self, shop_name: str):
        path = self.data_path / "商店数据" / f"{shop_name}.json"
        if not path.is_file():
            return None
        return Shop.from_dict(utils.tempjson.load_and_read(str(path)))

    def save_shop_data(self, shop: Shop):
        path = str(self.data_path / "商店数据" / shop.name) + ".json"
        utils.tempjson.load_and_write(
            path,
            shop.to_dict(),
            need_file_exists=False,
        )
        utils.tempjson.flush(path)

    def shop_name_exists(self, name: str):
        return name + ".json" in os.listdir(self.data_path / "商店数据")

    def pretty_get_shop_data_from_player(self, player: Player):
        ld = self.get_player_linked_shop_data(player)
        if ld is None:
            self.style.failed(player, "你还没有创建或加入一个商店")
            return None
        if not (sd := self.get_shop_data(ld.in_shop_name)):
            self.style.failed(player, "你所在的商店已被删除")
            return None
        return sd

    def check_shopname(self, name: str):
        for char in name:
            if char.isascii():
                if (
                    char
                    not in "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM1234567890"
                ):
                    return False
        return True

    def add_money_score(self, player: Player, money: int):
        self.game_ctrl.sendwocmd(
            f"scoreboard players add {player.getSelector()} {self.money_scb_name} {money}"
        )

    def remove_money_score(self, player: Player, money: int):
        self.game_ctrl.sendwocmd(
            f"scoreboard players remove {player.getSelector()} {self.money_scb_name} {money}"
        )


entry = plugin_entry(BarrelShop)
