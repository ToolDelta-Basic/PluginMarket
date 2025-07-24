import os

from tooldelta import plugin_entry, Plugin, ToolDelta, Player, TYPE_CHECKING, game_utils
from tooldelta.utils import tempjson
from tooldelta.constants import PacketIDS

class GuildPlugin(Plugin):
    name = "公会系统"
    author = "星林"
    version = (0, 0, 1)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.guilds_file = self.format_data_path("guilds.json")
        tempjson.load_and_read(self.guilds_file, need_file_exists=False, default={})

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.xuidm = self.GetPluginAPI("XUID获取")

        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_玩家XUID获取 import XUIDGetter

            self.chatbar: ChatbarMenu
            self.xuidm: XUIDGetter
            

    def on_inject(self):
        self.chatbar.add_new_trigger(
            ["公会"],
            [("", str, "")],
            "公会系统指令",
            self.guild_menu_cb
        )

    def guild_menu_cb(self, player: Player, args: tuple):
        player.show("§r========== §a公会系统§r ==========§r§d")
        menu_items = [
            ("1", "创建", "创建自己的公会"),
            ("2", "列表", "查看所有公会"),
            ("3", "查看", "查看我加入的公会"),
            ("4", "加入", "加入一个公会"),
            ("5", "退出", "退出当前公会"),
            ("6", "解散", "解散自己创建的公会"),
            ("7", "踢出", "踢出公会中的成员"),
        ]

        for num, cmd, desc in menu_items:
            player.show(f"§e§l{num}. §r{cmd} §f[§6{desc}§r]")


        subcommand = game_utils.waitMsg(player.name)
        param = args[1] if len(args) > 1 else ""
        
        guilds = tempjson.load_and_read(self.guilds_file, need_file_exists=False, default={})
        
        player_xuid = self.xuidm.get_xuid_by_name(player.name, allow_offline=True)

        if subcommand == "创建":
            if player_xuid in guilds:
                player.show("§l§a公会 §d>> §r你已经有公会了")
                return True

            # 检查钻石数量
            diamond_count = player.getItem(player.name,"minecraft:diamond")
            if diamond_count < 10:
                player.show("§l§a公会 §d>> §r创建公会需要10个钻石")
                return True

            player.show("§l§a公会 §d>> §r请输入公会名字:")
            guild_name = game_utils.waitMsg(player.name)

            if guild_name in [g["name"] for g in guilds.values()]:
                player.show("§l§a公会 §d>> §r该公会名已存在")
                return True

            # 扣除10个钻石
            self.game_ctrl.sendwocmd(f"clear {player.name} minecraft:diamond 0 10")

            guilds[player_xuid] = {
                "name": guild_name,
                "owner": player.name,
                "members": [player.name]
            }
            tempjson.write(self.guilds_file, guilds)
            player.show(f"§l§a公会 §d>> §r已创建公会 §e{guild_name}")

        elif subcommand == "列表":
            guild_list = list(guilds.values())
            if not guild_list:
                player.show("§l§a公会 §d>> §r当前没有公会")
                return True

            per_page = 6
            page = int(param) if param.isdigit() else 1
            max_page = (len(guild_list) + per_page - 1) // per_page

            while True:
                page = max(1, min(page, max_page))
                start = (page - 1) * per_page
                end = start + per_page

                msg = f"§r========== §a公会系统§r ==========§r§d\n§r第{page}/{max_page}页\n"
                for i, g in enumerate(guild_list[start:end], start=1):
                    msg += f"§e{start + i}. §r{g['name']} §7(会长:{g['owner']})\n"
                msg += "§r§7>> 输入 + 下一页，- 上一页，q 退出"
                player.show(msg)

                choice = game_utils.waitMsg(player.name, timeout=20)
                if choice is None:
                    player.show("§r§c操作超时，已退出公会列表")
                    break
                if choice == "+":
                    if page < max_page:
                        page += 1
                    else:
                        player.show("§r§c已经是最后一页")
                elif choice == "-":
                    if page > 1:
                        page -= 1
                    else:
                        player.show("§r§c已经是第一页")
                elif choice == "q":
                    player.show("§r§a已退出公会列表")
                    break
                else:
                    player.show("§r§c无效输入，请输入 + / - / q")


        elif subcommand == "查看":
            found = None
            # 查找玩家自己所在的公会
            for g in guilds.values():
                if player.name in g["members"]:
                    found = g
                    break

            if not found:
                player.show("§l§a公会 §d>> §r你尚未加入任何公会")
                return True

            msg = f"§l§a{found['name']}§r§f§o(会长: {found['owner']})\n"

            for idx, m in enumerate(found["members"], start=1):
                try:
                    pos_data = game_utils.getPos(m)
                    dim_id = pos_data["dimension"]
                    if dim_id == 0:
                        dim = "主世界"
                    elif dim_id == 1:
                        dim = "地狱"
                    elif dim_id == 2:
                        dim = "末地"
                    else:
                        dim = f"维度ID:{dim_id}"

                    x = pos_data["position"]["x"]
                    y = pos_data["position"]["y"]
                    z = pos_data["position"]["z"]

                    msg += f"\n§l§e{idx}.§r {m} | §o§7{dim} ({x:.1f},{y:.1f},{z:.1f})"

                except Exception as e:
                    msg += f"\n§l§e{idx}.§r §7{m}§o§g离线"

            player.show(msg)

        elif subcommand == "加入":
            # 判断自己是否已加入公会
            already_in_guild = False
            for g in guilds.values():
                if player.name in g["members"]:
                    already_in_guild = True
                    break
            if already_in_guild:
                player.show("§l§a公会 §d>> §r你已经加入了一个公会，无法再次加入")
                return True

            player.show("§l§a公会 §d>> §r请输入公会名字")
            target_guild = None
            search_guild_name = game_utils.waitMsg(player.name)

            if search_guild_name == "":
                player.show("§l§a公会 §d>> §r公会名字不可以为空")
                return True

            matched_guilds = []
            for g in guilds.values():
                if search_guild_name in g["name"]:
                    matched_guilds.append(g)

            if not matched_guilds:
                player.show("§l§a公会 §d>> §r未找到包含该名字的公会")
                return True

            if len(matched_guilds) == 1:
                target_guild = matched_guilds[0]
            else:
                # 多个匹配，列出选择
                msg = "§a匹配到多个公会，请选择：\n"
                for idx, g in enumerate(matched_guilds, start=1):
                    msg += f"{idx}. {g['name']} (会长:{g['owner']})\n"
                player.show(msg)
                choice = game_utils.waitMsg(playerf.name)
                if choice is None or not choice.isdigit() or int(choice) < 1 or int(choice) > len(matched_guilds):
                    player.show("§c选择无效，已取消")
                    return True
                target_guild = matched_guilds[int(choice) - 1]

            # 判断会长是否在线
            owner_name = target_guild["owner"]
            online_players = self.game_ctrl.allplayers
            if owner_name not in online_players:
                player.show("§l§a公会 §d>> §r会长当前不在线，请稍后再申请")
                return True

            # 发送申请
            self.game_ctrl.sendcmd(
                f"/tellraw {owner_name} {{\"rawtext\":[{{\"text\":\"§l§a公会 §d>> §r§e{player.name} §f申请加入公会 §e{target_guild['name']}\\n§f输入 §a同意 §f或 §c拒绝\"}}]}}"
            )
            player.show(f"已向 {owner_name} 发送加入申请，等待会长同意")

            reply = game_utils.waitMsg(owner_name, timeout=180)
            if reply is None:
                player.show("§l§a公会 §d>> §r会长未回复，申请超时")
                return True
            if reply == f"同意":
                target_guild["members"].append(player.name)
                tempjson.write(self.guilds_file, guilds)
                player.show(f"§l§a公会 §d>> §r会长已同意，你已加入公会 {target_guild['name']}")
                self.game_ctrl.sendcmd(
                    f"/tellraw {owner_name} {{\"rawtext\":[{{\"text\":\"§l§a公会 §d>> §r已同意 {player.name} 加入公会\"}}]}}"
                )
                return True
            if reply == f"拒绝":
                player.show("§l§a公会 §d>> §r会长已拒绝你的申请")
                self.game_ctrl.sendcmd(
                    f"/tellraw {owner_name} {{\"rawtext\":[{{\"text\":\"§l§a公会 §d>> §r已拒绝 {player.name} 加入公会\"}}]}}"
                )
                return True

        elif subcommand == "退出":
            for gid, g in list(guilds.items()):
                if player.name in g["members"]:
                    if g["owner"] == player.name:
                        player.show("§l§a公会 §d>> §r你是会长，请使用 解散 公会")
                        return True
                    g["members"].remove(player.name)
                    tempjson.write(self.guilds_file, guilds)
                    player.show("§l§a公会 §d>> §r已退出公会")
                    return True
            player.show("§l§a公会 §d>> §r你未加入任何公会")

        elif subcommand == "解散":
            is_owner = False
            for gid, g in list(guilds.items()):
                if g["owner"] == player.name:
                    is_owner = True
                    player.show(f"§l§a公会 §d>> §r你确定要解散公会 §e{g['name']} §r吗？输入“确认”以继续")
                    confirm = game_utils.waitMsg(player.name)
                    if confirm != "确认":
                        player.show("§l§a公会 §d>> §r操作已取消")
                        return True
                    del guilds[gid]
                    tempjson.write(self.guilds_file, guilds)
                    player.show(f"§l§a公会 §d>> §r已解散公会 §e{g['name']}")
                    return True
            if not is_owner:
                player.show("§l§a公会 §d>> §r你不是任何公会的会长")

        elif subcommand == "踢出":
            # 查找玩家所在公会且为会长
            guild_found = None
            for g in guilds.values():
                if g["owner"] == player.name:
                    guild_found = g
                    break

            if not guild_found:
                player.show("§l§a公会 §d>> §r你不是任何公会的会长")
                return True

            members = guild_found["members"]
            if len(members) <= 1:
                player.show("§l§a公会 §d>> §r没有可踢出的成员")
                return True

            per_page = 6
            page = 1
            max_page = (len(members) + per_page - 1) // per_page

            while True:
                page = max(1, min(page, max_page))
                start = (page - 1) * per_page
                end = start + per_page

                msg = f"§r========== §a公会踢出成员§r ==========§r§d\n§r第{page}/{max_page}页\n"
                idx_map = []
                for i, m in enumerate(members[start:end], start=1):
                    if m != player.name:  # 不显示会长自己
                        msg += f"§e{i - 1}. §r{m}\n"
                        idx_map.append(m)
                msg += "§r§7>> 输入成员序号踢出，+ 下一页，- 上一页，q 退出"
                player.show(msg)

                choice = game_utils.waitMsg(player.name)
                if choice == "+":
                    if page < max_page:
                        page += 1
                    else:
                        player.show("§r§c已经是最后一页")
                elif choice == "-":
                    if page > 1:
                        page -= 1
                    else:
                        player.show("§r§c已经是第一页")
                elif choice == "q":
                    player.show("§r§a已退出踢出菜单")
                    break
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if idx < 0 or idx >= len(idx_map):
                        player.show("§r§c无效序号")
                    else:
                        target = idx_map[idx]
                        guild_found["members"].remove(target)
                        tempjson.write(self.guilds_file, guilds)
                        player.show(f"§l§a公会 §d>> §r已将 §r{target}§f 踢出公会")
                        break
                else:
                    player.show("§r§c无效输入，请输入序号 / + / - / q")


        else:
            player.show("§l§a公会 §d>> §r你在发什么东西？")

        return True


entry = plugin_entry(GuildPlugin)
