import os, threading, time  # noqa: E401
from tooldelta import (
    Plugin,
    cfg as config,
    game_utils,
    utils,
    TYPE_CHECKING,
    plugin_entry,
    Player,
)
from tooldelta.constants import PacketIDS

IS_CREATE_LOCK = threading.RLock()


class SkyBlock(Plugin):
    name = "空岛系统"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        CFGPOS = config.JsonList(int, 3)
        CFG_STD = {
            "是否启用入侵功能": bool,
            "入侵条件判断指令": str,
            "入侵持续时间": int,
            "空岛生成坐标原点(生效后请勿更改)": CFGPOS,
            "空岛间距(生效后请勿更改)": config.PInt,
            "可选空岛结构": config.AnyKeyValue(
                {"结构名": str, "介绍": str, "结构生成偏移": CFGPOS}
            ),
        }
        CFG_DEFAULT = {
            "是否启用入侵功能": False,
            "入侵条件判断指令": "/clear @a[name=[玩家名],hasitem={item=paper,data=1000,quantity=1..,location=slot.weapon.mainhand}] paper 1000 1",
            "入侵持续时间": 120,
            "空岛生成坐标原点(生效后请勿更改)": [0, 100, 200],
            "空岛间距(生效后请勿更改)": 160,
            "可选空岛结构": {
                "L型空岛": {
                    "结构名": "空岛1",
                    "介绍": "普通的L型空岛",
                    "结构生成偏移": [-9, -6, -4],
                },
                "微缩地形空岛": {
                    "结构名": "空岛2",
                    "介绍": "有着微缩地形的空岛",
                    "结构生成偏移": [-7, -6, -7],
                },
                "微缩矿区空岛": {
                    "结构名": "空岛3",
                    "介绍": "有着微缩矿区的空岛",
                    "结构生成偏移": [-7, -6, -7],
                },
            },
        }
        cfg, _ = config.get_plugin_config_and_version(
            self.name, CFG_STD, CFG_DEFAULT, self.version
        )
        self.ISLAND_DZ = cfg["空岛间距(生效后请勿更改)"]
        self.ORIG_X, self.ORIG_Y, self.ORIG_Z = cfg["空岛生成坐标原点(生效后请勿更改)"]
        self.island_structures = cfg["可选空岛结构"]
        self.Invasion_Enable = cfg["是否启用入侵功能"]
        self.Invasion_Cmd = cfg["入侵条件判断指令"]
        self.Invasion_Time = cfg["入侵持续时间"]
        self.Invasion_List = {}
        self.make_data_path()
        self.players = self.frame.get_players()
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.IDText, self.on_player_death)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.intr = self.GetPluginAPI("前置-世界交互")
        self.funclib = self.GetPluginAPI("基本插件功能库")
        if TYPE_CHECKING:
            from 前置_聊天栏菜单 import ChatbarMenu
            from 前置_世界交互 import GameInteractive
            from 前置_基本插件功能库 import BasicFunctionLib

            self.chatbar = self.get_typecheck_plugin_api(ChatbarMenu)
            self.intr = self.get_typecheck_plugin_api(GameInteractive)
            self.funclib = self.get_typecheck_plugin_api(BasicFunctionLib)
        self.chatbar.add_trigger(
            ["is", "空岛"], None, "返回空岛或 .is help 查看空岛帮助", self.island_menu
        )
        for path in (
            "玩家记录.json",
            "空岛记录.json",
        ):
            path = os.path.join(self.data_path, path)
            obj = utils.TMPJson.read_as_tmp(path, False)
            if obj is None:
                utils.TMPJson.write(path, {})

    def on_inject(self):
        self.game_ctrl.sendwocmd("scoreboard objectives add is:data dummy 空岛主信息")
        self.game_ctrl.sendwocmd("scoreboard objectives add is:visit dummy 空岛访问uid")
        self.game_ctrl.sendwocmd("scoreboard objectives add is:invasion dummy 入侵计时")
        self.game_ctrl.sendwocmd("scoreboard players add uid is:data 0")
        self.game_ctrl.sendwocmd("scoreboard players add posx is:data 0")
        self.game_ctrl.sendwocmd("scoreboard players add posy is:data 0")
        self.game_ctrl.sendwocmd("scoreboard players add posz is:data 0")
        self.on_second_event()

    @utils.timer_event(1, "空岛每秒事件")
    def on_second_event(self):
        self.game_ctrl.sendwocmd(
            "scoreboard player remove @a[scores={is:invasion=1..}] is:invasion 1"
        )
        self.game_ctrl.sendwocmd(
            "execute as @a[tag=is.visitor,scores={is:invasion=0}] run w @a[tag=robot] .is leave"
        )

    def on_player_death(self, packet):
        if packet["TextType"] != 2:
            return
        if packet["Message"][:12] != "death.attack":
            return
        name = packet["Parameters"][1]
        is_online = self.game_ctrl.sendcmd_with_resp(
            f"/querytarget @a[name={name}]"
        ).SuccessCount
        is_death = self.game_ctrl.sendcmd_with_resp(
            f"/querytarget @e[name={name},family=player]"
        ).SuccessCount
        if is_online and not is_death:
            Intruder = self.Invasion_List.get(name)
            if Intruder is None:
                return
            self.Invasion_List.pop(name)
            self.make_player_exit(Intruder)

    def on_player_leave(self, player: Player):
        name = player.name
        Intruder = self.Invasion_List.get(name)
        if Intruder is None:
            return
        self.Invasion_List.pop(name)
        self.make_player_exit(Intruder)

    def show_inf(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§f!§7] §f{msg}")

    def show_suc(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§a√§7] §a{msg}")

    def show_war(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§6!§7] §6{msg}")

    def show_err(self, player: str, msg: str):
        self.game_ctrl.say_to(player, f"§7[§cx§7] §c{msg}")

    def get_player_island_uid(self, player: str) -> int | None:
        player_path = self.data_path + "/" + "玩家记录.json"
        player_obj = utils.TMPJson.read_as_tmp(player_path, False)
        res = player_obj.get(player)
        if res is None:
            return None
        else:
            return res["own_island"] or res["main_island"]

    def get_isdata_by_uid(self, uid: int | str):
        island_path = os.path.join(self.data_path, "空岛记录.json")
        islands_obj = utils.TMPJson.read_as_tmp(island_path, False) or {}
        return islands_obj.get(str(uid))

    def set_island_data_by_uid(self, uid: int, datas, tmp=True):
        island_path = os.path.join(self.data_path, "空岛记录.json")
        former = utils.TMPJson.read_as_tmp(island_path, False) or {}
        former[str(uid)] = datas
        utils.TMPJson.write_as_tmp(island_path, former, False)
        if not tmp:
            utils.TMPJson.flush(island_path)

    def island_menu(self, player: str, args: list[str]):
        gc = self.game_ctrl
        if args == []:
            self.island_back(player)
            return
        match args[0]:
            case "help":
                helps = [
                    ".is create §2<空岛类型> §7§o此命令仅供命令方块使用",
                    ".is back §7§o返回自己的空岛",
                    ".is merge §7§o申请共用空岛",
                    ".is settings §7§o对空岛访问系统进行设置",
                    ".is visit §2<空岛ID> §7§o访问其他人的空岛",
                    ".is leave §7§o退出其他人的空岛",
                    ".is kick §7§o从自己的空岛踢出成员",
                    ".is invade §2<玩家名> §7§o使用道具对其他玩家的空岛入侵",
                ]
                gc.say_to(player, "\n§r".join(helps))
            case "create":
                if len(args) != 2:
                    self.show_err(
                        player,
                        "请不要使用菜单命令发起该功能， 如果你是管理员， 那么请阅读一下该插件的手册",
                    )
                    self.show_err(
                        player, "手册阅读方法：插件管理器->选中该插件->查看手册"
                    )
                    return
                self.is_create(player, args[1:])
            case "back" | "返回":
                self.island_back(player)
            case "merge" | "合岛":
                self.island_l2j(player)
            case "kick" | "踢人":
                self.island_kick(player)
            case "settings" | "设置":
                self.island_visit_settings(player)
            case "visit" | "参观":
                if len(args) != 2:
                    self.show_inf(player, "请输入需要访问的空岛的UID：")
                    resp = game_utils.waitMsg(player)
                    if resp is None:
                        self.show_war(player, "无效输入")
                        return
                    self.island_visit(player, [resp])
                else:
                    self.island_visit(player, args[1:])
            case "invasion" | "入侵":
                if len(args) != 2:
                    self.show_inf(player, "请输入需要入侵的空岛岛主名称：")
                    resp = game_utils.waitMsg(player)
                    if resp is None:
                        self.show_war(player, "无效输入")
                        return
                    self.island_invasion(player, [resp])
                else:
                    self.island_invasion(player, args[1:])
            case "leave" | "离开":
                self.island_unvisit(player)
            case _:
                self.show_err(player, "没有这条命令， 输入 .is help 查看帮助")

    def is_create(self, player: str, args: list[str]):
        if args[0] not in self.island_structures.keys():
            self.show_war(player, "无效的空岛结构")
            return
        is_struct = self.island_structures[args[0]]
        player_path = os.path.join(self.data_path, "玩家记录.json")
        island_path = os.path.join(self.data_path, "空岛记录.json")
        player_obj = utils.TMPJson.read_as_tmp(player_path, False)
        island_obj = utils.TMPJson.read_as_tmp(island_path, False)
        if player_obj.get(player) is not None:
            self.show_war(player, "你已经认领过空岛")
            return
        is_uid_now = game_utils.getScore("is:data", "uid")
        this_island_pos_z = game_utils.getScore("is:data", "posz")
        if this_island_pos_z == 0:
            this_island_pos_x = self.ORIG_X
            this_island_pos_y = self.ORIG_Y
            this_island_pos_z = self.ORIG_Z + self.ISLAND_DZ
            self.game_ctrl.sendwocmd(
                f"scoreboard players set posx is:data {this_island_pos_x}"
            )
            self.game_ctrl.sendwocmd(
                f"scoreboard players set posy is:data {this_island_pos_y}"
            )
            self.game_ctrl.sendwocmd(
                f"scoreboard players set posz is:data {this_island_pos_z}"
            )
        else:
            this_island_pos_x = game_utils.getScore("is:data", "posx")
            this_island_pos_y = game_utils.getScore("is:data", "posy")
        TOTAL = 5
        self.game_ctrl.player_actionbar(
            player, f"空岛生成中 (1/{TOTAL}) §7加载空岛区块.."
        )
        with IS_CREATE_LOCK:
            try:
                resp = self.game_ctrl.sendcmd_with_resp(
                    f"/tickingarea add {this_island_pos_x - 20} 0 {this_island_pos_z - 20} {this_island_pos_x + 20} 0 {this_island_pos_z + 20} island_cache"
                )
                if resp.SuccessCount == 0:
                    self.show_err(player, "无法创建常加载区生成空岛， 请告知管理员")
                    return
                px, py, pz = is_struct["结构生成偏移"]
                self.game_ctrl.player_actionbar(
                    player, f"空岛生成中 (2/{TOTAL}) §7生成空岛结构.."
                )
                resp = self.game_ctrl.sendcmd_with_resp(
                    f"structure load {is_struct['结构名']} {this_island_pos_x + px} {this_island_pos_y + py} {this_island_pos_z + pz}"
                )
                if resp.SuccessCount == 0:
                    self.show_err(
                        player,
                        f"空岛结构 {is_struct['结构名']} 不存在， 请联系管理员设置结构方块",
                    )
                    return
                self.game_ctrl.sendwocmd(
                    f"tp @a[name={player}] {this_island_pos_x} {this_island_pos_y + 2} {this_island_pos_z}"
                )
                self.game_ctrl.player_actionbar(
                    player, f"空岛生成中 (3/{TOTAL}) §7设置保护.."
                )
                self.game_ctrl.sendwocmd(f"effect {player} resistance 10 20 true")
                self.game_ctrl.sendwocmd(
                    f"summon cow §9§l{player}的牛 {this_island_pos_x + 1} {this_island_pos_y + 2} {this_island_pos_z + 1}"
                )
                cb_data = self.intr.make_packet_command_block_update(
                    (this_island_pos_x, -63, this_island_pos_z),
                    f"/tag @a[x=~-{self.ISLAND_DZ // 2},y=-63,z=~-{self.ISLAND_DZ // 2},dx={self.ISLAND_DZ},"
                    f"dy=384,dz={self.ISLAND_DZ},name=!{player},tag=!robot,m=!1,tag=!is.visitor] add is.kick",
                    1,
                    tick_delay=5,
                    name="空岛保护",
                )
                self.game_ctrl.sendcmd(
                    f"tp {this_island_pos_x} -63 {this_island_pos_z}"
                )
                for _ in range(20):
                    if (
                        self.game_ctrl.sendcmd_with_resp(
                            f"setblock {this_island_pos_x} -63 {this_island_pos_z} bedrock"
                        ).SuccessCount
                        == 0
                    ):
                        self.game_ctrl.player_actionbar(
                            player, f"空岛生成中 (4/{TOTAL}) §6放置方块失败， 重试中.."
                        )
                        self.game_ctrl.sendcmd_with_resp(
                            f"setblock {this_island_pos_x} -63 {this_island_pos_z} air"
                        )
                    else:
                        break
                else:
                    self.game_ctrl.say_to(player, "§c完蛋， 你该寻求管理员的帮助了")
                    return
                self.intr.place_command_block(cb_data, limit_seconds=0)
                self.game_ctrl.sendwocmd(
                    f"execute as @a[name={player}] at @s run spreadplayers ~ ~ 1 3 @s"
                )
                self.game_ctrl.player_actionbar(
                    player, f"空岛生成中 (4/{TOTAL}) §7初始化数据库.."
                )
                player_obj[player] = self.init_skyblock_player_data(is_uid_now)
                island_obj[str(is_uid_now)] = self.init_skyblock_island_data(
                    is_uid_now,
                    player,
                    [this_island_pos_x, this_island_pos_y, this_island_pos_z],
                )
                utils.TMPJson.write(player_path, player_obj)
                utils.TMPJson.write(island_path, island_obj)
                utils.TMPJson.flush(player_path)
                utils.TMPJson.flush(island_path)
                self.game_ctrl.sendwocmd("scoreboard players add uid is:data 1")
                self.game_ctrl.sendwocmd(
                    f"scoreboard players add posz is:data {self.ISLAND_DZ}"
                )
                self.game_ctrl.sendwocmd(
                    f"execute as @a[name={player}] at @s run spawnpoint"
                )
                self.game_ctrl.sendwocmd(f"gamemode 0 @a[name={player}]")
                self.game_ctrl.player_actionbar(
                    player, f"空岛生成中 (5/{TOTAL}) §7完成！"
                )
                self.show_suc(player, "空岛已成功创建")
                self.show_suc("@a", f"{player} 创建了一个空岛")
            finally:
                self.game_ctrl.sendcmd("/tickingarea remove island_cache")

    def island_kick(self, player: str):
        player_path = self.data_path + "/" + "玩家记录.json"
        players_obj = utils.TMPJson.read_as_tmp(player_path, False)
        player_data = players_obj.get(player)
        if player_data is None:
            self.show_war(player, "你还没有创建一个空岛")
            return
        own_island = player_data["own_island"]
        if own_island is None:
            self.show_war(player, "你目前的身份不是岛主")
            return
        island_obj = self.get_isdata_by_uid(player_data["own_island"])
        assert island_obj
        members = island_obj["members"]
        self.show_inf(player, "§6选择一个玩家以踢出空岛：")
        for i, j in enumerate(members):
            self.game_ctrl.say_to(player, f" §a{i + 1}§7 - §f{j}")
        self.show_inf(player, "§7输入玩家名前的§6序号§7：")
        resp = utils.try_int(game_utils.waitMsg(player))
        if resp is None:
            self.show_err(player, "序号错误， 已退出")
            return
        if resp not in range(1, len(members) + 1):
            self.show_err(player, "序号不在范围内， 已退出")
            return
        selected = members[resp - 1]
        members.remove(selected)
        island_obj["members"] = members
        selector = "".join(
            f"name=!{i}," for i in island_obj["members"] + [island_obj["owner"]]
        )
        cmd = (
            f"/tag @a[x=~-{self.ISLAND_DZ // 2},y=-63,z=~-{self.ISLAND_DZ // 2},dx={self.ISLAND_DZ},"
            f"dy=384,dz={self.ISLAND_DZ},{selector}tag=!robot,m=!1] add is.kick"
        )
        is_posx, _, is_posz = island_obj["pos"]
        self.intr.place_command_block(
            self.intr.make_packet_command_block_update(
                (is_posx, -63, is_posz),
                cmd,
                1,
                tick_delay=5,
                name="空岛保护",
                should_track_output=False,
            )
        )
        sdata = players_obj[selected]
        sdata["own_island"] = sdata["backup_island"]
        players_obj[selected] = sdata
        utils.TMPJson.write_as_tmp(player_path, players_obj)
        self.set_island_data_by_uid(player_data["own_island"], island_obj, False)
        self.show_suc(player, f"已踢出 {selected}.")

    def island_back(self, player: str):
        player_path = self.data_path + "/" + "玩家记录.json"
        island_path = self.data_path + "/" + "空岛记录.json"
        player_obj = utils.TMPJson.read_as_tmp(player_path, False)
        island_obj = utils.TMPJson.read_as_tmp(island_path, False)
        player_data = player_obj.get(player)
        if player_data is None:
            self.show_war(player, "你还没有创建一个空岛")
            return
        is_uid = player_data["own_island"]
        if is_uid is None:
            is_uid = player_data["main_island"]
        is_data = island_obj.get(str(is_uid))
        if is_data is None:
            self.show_err(player, f"空岛UID: {is_uid} 未找到， 请截图告知管理员")
            return
        tp_pos = is_data["pos"]
        self.game_ctrl.sendwocmd(
            f"tp @a[name={player}] {' '.join(str(i) for i in tp_pos)}"
        )
        self.game_ctrl.sendwocmd(f"gamemode 0 @a[m=!1,name={player}]")
        self.game_ctrl.say_to(player, "§f[§a岛屿酱§f] §a欢迎回来， Master~")

    def island_l2j(self, player: str):
        player_path = self.data_path + "/" + "玩家记录.json"
        island_path = self.data_path + "/" + "空岛记录.json"
        players_obj = utils.TMPJson.read_as_tmp(player_path, False)
        islands_obj = utils.TMPJson.read_as_tmp(island_path, False)
        onlines = self.game_ctrl.allplayers.copy()
        onlines.remove(player)
        onlines.remove(self.game_ctrl.bot_name)
        if not onlines:
            self.show_war(player, "目前没有玩家可供选择")
            return
        for i in onlines.copy():
            if (
                players_obj.get(i) is None
                or players_obj.get(i) is None
                or players_obj[i]["own_island"] is None
            ):
                onlines.remove(i)
        self.show_inf(player, "§6选择一个玩家以申请加入他的空岛：")
        for i, j in enumerate(onlines):
            self.game_ctrl.say_to(player, f" §a{i + 1}§7 - §f{j}")
        self.show_inf(player, "§7输入玩家名前的§6序号§7：")
        resp = utils.try_int(game_utils.waitMsg(player))
        if resp is None:
            self.show_err(player, "序号错误， 已退出")
            return
        if resp not in range(1, len(onlines) + 1):
            self.show_err(player, "序号不在范围内， 已退出")
            return
        target = onlines[resp - 1]
        self.show_inf(player, "请求已发出， 等待对方回复..")
        self.show_inf(target, f"{player} §6想和您共用空岛")
        self.show_inf(target, "输入 §ay§f=同意， §cn§f=拒绝")
        if (resp := game_utils.waitMsg(target)) is None or resp.lower() != "y":
            self.show_inf(target, f"§6已拒绝 §f{player} §6的请求")
            self.show_war(player, "你的请求已被拒绝")
            return
        self.show_inf(target, f"§a已同意 §f{player} §6的请求")
        self.show_inf(player, "对方已同意！")
        self.show_war(player, "这样做， 你将失去你先前的岛屿！")
        self.show_inf(player, "输入 y 继续， 其他退出")
        if game_utils.waitMsg(player) != "y":
            self.show_war(player, "已退出.")
            return
        # Accept
        his_island = players_obj[target]["own_island"]
        is_data = islands_obj[str(his_island)]
        if player in is_data["members"]:
            self.show_war(player, "你已经是他空岛的成员了")
            return
        is_posx, _, is_posz = is_data["pos"]
        self.game_ctrl.sendcmd(f"/tp {is_posx} -63 {is_posz}")
        for i in range(20):
            if (
                self.game_ctrl.sendcmd_with_resp(
                    f"setblock {is_posx} -63 {is_posz} bedrock"
                ).SuccessCount
                == 0
            ):
                time.sleep(0.2)
            else:
                break
        else:
            self.game_ctrl.say_to(player, "§c完蛋， 你该寻求管理员的帮助了")
            return
        is_data["members"].append(player)
        selector = "".join(f"name=!{i}," for i in is_data["members"] + [target])
        cmd = (
            f"/tag @a[x=~-{self.ISLAND_DZ // 2},y=-63,z=~-{self.ISLAND_DZ // 2},dx={self.ISLAND_DZ},"
            f"dy=384,dz={self.ISLAND_DZ},{selector}tag=!robot,m=!1,scores={{is:visit=!{his_island}}}] add is.kick"
        )
        cb_data = self.intr.make_packet_command_block_update(
            (is_posx, -63, is_posz),
            cmd,
            1,
            tick_delay=5,
            name="空岛保护",
        )
        self.intr.place_command_block(cb_data, limit_seconds=0, limit_seconds2=0.5)
        players_obj[player]["backup_island"] = players_obj[player]["own_island"]
        players_obj[player]["own_island"] = None
        players_obj[player]["main_island"] = is_data["uid"]
        islands_obj[str(is_data["uid"])] = is_data
        utils.TMPJson.write(player_path, players_obj)
        utils.TMPJson.write(island_path, islands_obj)
        utils.TMPJson.flush(island_path)
        utils.TMPJson.flush(player_path)
        self.show_suc(player, f"加入 {target} 的空岛成功")
        self.show_suc(target, f"同意 {player} 加入空岛成功")

    def island_visit_settings(self, player: str):
        gc = self.game_ctrl
        island_uid = self.get_player_island_uid(player)
        if island_uid is None:
            gc.say_to(player, "§c你还没有拥有一个空岛")
            return
        island_dat = self.get_isdata_by_uid(island_uid)
        if island_dat is None:
            gc.say_to(player, "§c空岛信息获取错误， 请联系管理员")
            return
        dx, _, dz = game_utils.getPosXYZ(player)
        ix, _, iz = island_dat["pos"]
        if ((dx - ix) ** 2 + (dz - iz) ** 2) ** 0.55 > 240:
            gc.say_to(player, "§c你需要在自己空岛上设置")
            return
        visit_perms = island_dat.get("visit_permissions")
        if visit_perms is None:
            visit_perms = {
                "container": 0,
                "switch": 0,
                "attack_mob": 0,
                "attack_player": 0,
                "name": None,
                "tp_pos": None,
            }
            selector = "".join(
                f"name=!{i}," for i in island_dat["members"] + [island_dat["owner"]]
            )
            cmd = (
                f"/tag @a[x=~-{self.ISLAND_DZ // 2},y=-63,z=~-{self.ISLAND_DZ // 2},dx={self.ISLAND_DZ},"
                f"dy=384,dz={self.ISLAND_DZ},{selector}tag=!robot,m=!1,scores={{is:visit=!{island_uid}}}] add is.kick"
            )
            is_posx, _, is_posz = island_dat["pos"]
            self.intr.place_command_block(
                self.intr.make_packet_command_block_update(
                    (is_posx, -63, is_posz),
                    cmd,
                    1,
                    tick_delay=5,
                    name="空岛保护",
                    should_track_output=False,
                )
            )
            gc.say_to(player, "§a已初始化访客命令方块")
        while 1:
            gc.say_to(player, f"§6空岛访客设置界面 §a(UID={island_uid}) §7>>>")
            gc.say_to(
                player,
                "  1. 设置空岛名： "
                + ("暂未设置" if visit_perms["name"] is None else visit_perms["name"]),
            )
            gc.say_to(
                player,
                "  2. 设置传送点： "
                + (
                    "未设置"
                    if visit_perms["tp_pos"] is None
                    else ", ".join(str(i) for i in visit_perms["tp_pos"])
                ),
            )
            gc.say_to(
                player,
                "  3. 容器交互 §7[" + ("§cx", "§a√")[visit_perms["container"]] + "§7]",
            )
            gc.say_to(
                player,
                "  4. 门和开关交互 §7[" + ("§cx", "§a√")[visit_perms["switch"]] + "§7]",
            )
            gc.say_to(
                player,
                "  5. 攻击生物 §7[" + ("§cx", "§a√")[visit_perms["attack_mob"]] + "§7]",
            )
            gc.say_to(
                player,
                "  6. 攻击玩家 §7["
                + ("§cx", "§a√")[visit_perms["attack_player"]]
                + "§7]",
            )
            gc.say_to(player, "  其他： §6以保存并退出")
            gc.say_to(player, "§6输入选项以开启/关闭权限：")
            match game_utils.waitMsg(player):
                case "1":
                    gc.say_to(player, "§6请输入空岛展示名：")
                    resp = game_utils.waitMsg(player)
                    if resp is not None:
                        visit_perms["name"] = resp
                    else:
                        gc.say_to(player, "§c设置超时.")
                case "2":
                    visit_perms["tp_pos"] = [
                        int(i) for i in game_utils.getPosXYZ(player)
                    ]
                case "3":
                    visit_perms["container"] = 1 - visit_perms["container"]
                case "4":
                    visit_perms["switch"] = 1 - visit_perms["switch"]
                case "5":
                    visit_perms["attack_mob"] = 1 - visit_perms["attack_mob"]
                case "6":
                    visit_perms["attack_player"] = 1 - visit_perms["attack_player"]
                case _:
                    break
        island_dat["visit_permissions"] = visit_perms
        self.set_island_data_by_uid(island_uid, island_dat)
        gc.say_to(player, "§a已保存设置并退出.")
        return

    def island_visit(self, player: str, args: list[str]):
        uid = args[0]
        island_data = self.get_isdata_by_uid(uid)
        if island_data is None:
            self.show_war(player, "该空岛UID不存在")
            return
        if (perms := island_data.get("visit_permissions")) is None:
            self.show_war(player, "该空岛不支持访问， 请联系岛主进行空岛参观设置")
            return
        if island_data["visit_permissions"]["tp_pos"] is None:
            self.show_err(player, "这个空岛还没有设置参观传送点..")
            return
        if not self.replace_all_hotbars(player):
            self.show_war(player, "你的物品栏需要全空才能访问其他空岛")
            return
        self.make_player_ready_to_visit(player, perms)
        self.game_ctrl.sendwocmd(f"scoreboard players set {player} is:visit {uid}")
        if self.frame.launcher.omega.get_player_by_name(player).can_build:  # type: ignore
            self.show_err(player, "空岛访问出现异常")
            self.make_player_exit(player)
        is_pos = " ".join(str(i) for i in island_data["visit_permissions"]["tp_pos"])
        self.game_ctrl.sendwocmd(f"tp {player} {is_pos}")
        self.show_suc(player, f"已传送到 {island_data['owner']} 的岛屿.")
        self.show_suc(player, "输入 .is leave 可以离开此岛屿")

    def island_unvisit(self, player: str):
        self.island_back(player)
        self.game_ctrl.sendwocmd(f"scoreboard players set {player} is:visit 0")
        self.make_player_exit(player)
        self.game_ctrl.sendwocmd(f"clear @a[name={player}] stick 25535")

    def island_invasion(self, player: str, args: list[str]):
        if not self.Invasion_Enable:
            self.show_err(player, "当前服务器未开启入侵功能")
            return
        is_invasion = bool(
            self.game_ctrl.sendcmd_with_resp(
                utils.simple_fmt({"[玩家名]": player}, self.Invasion_Cmd)
            ).SuccessCount
        )
        if not is_invasion:
            self.show_war(player, "你没有足够的道具, 无法入侵空岛")
            return
        data = self.get_player_island_uid(player)
        if data is None:
            self.show_err(player, "你还未创建空岛, 无法入侵")
        name = args[0]
        uid = self.get_player_island_uid(name)
        if uid is None:
            self.show_war(player, "该玩家不存在")
            return
        island_data = self.get_isdata_by_uid(uid)
        if island_data is None:
            self.show_war(player, "该玩家还未创建空岛")
            return
        is_online = bool(
            self.game_ctrl.sendcmd_with_resp(f"querytarget {name}", 1).SuccessCount
        )
        if not is_online:
            self.show_war(player, "该玩家不在线, 无法入侵空岛")
            return
        perms = island_data.get("visit_permissions")
        self.show_war(name, f"空岛被 §f{player} §6入侵, 已传送回空岛")
        self.show_war(name, "死亡, 退出游戏, 离开空岛都将视为放弃空岛")
        self.island_back(name)
        self.make_player_ready_to_Invasion(player, perms)
        self.game_ctrl.sendwocmd(f"scoreboard players set {player} is:visit {uid}")
        self.game_ctrl.sendwocmd(
            f"scoreboard players set {player} is:invasion {self.Invasion_Time}"
        )
        self.game_ctrl.sendwocmd(f"tp {player} {name}")
        self.Invasion_List[name] = player

    def replace_all_hotbars(self, player: str):
        resp = self.funclib.multi_sendcmd_and_wait_resp(
            [
                (
                    f"replaceitem entity @a[name={player}] slot.hotbar {i} keep stick"
                    r' 1 25535 {"item_lock":{"mode":"lock_in_slot"}}'
                )
                for i in range(9)
            ],
            30,
        )
        if not all(i.SuccessCount for i in resp.values()):
            self.game_ctrl.sendwocmd(f"clear @a[name={player},m=!2] stick 25535")
            return False
        else:
            return True

    def make_player_ready_to_visit(self, player: str, perms):
        omg = self.frame.launcher.omega
        playerdat = omg.get_player_by_name(player)
        assert playerdat
        playerdat.set_attack_mobs_permission(bool(perms["attack_mob"]))
        playerdat.set_build_permission(False)
        playerdat.set_mine_permission(False)
        playerdat.set_containers_permission(bool(perms["container"]))
        playerdat.set_attack_players_permission(bool(perms["attack_player"]))
        playerdat.set_doors_and_switches_permission(bool(perms["switch"]))
        self.game_ctrl.sendwocmd(f"/gamemode 2 @a[name={player},m=!1]")
        self.game_ctrl.sendwocmd(f"/tag @a[name={player},m=!1] add is.visitor")
        if not perms["attack_mob"]:
            self.game_ctrl.sendwocmd(f"effect @a[name={player}] weakness 9999 245 true")
            self.game_ctrl.sendwocmd(f"tag @a[name={player}] add weakness255")

    def make_player_ready_to_Invasion(self, player: str, perms):
        omg = self.frame.launcher.omega
        playerdat = omg.get_player_by_name(player)
        assert playerdat
        playerdat.set_attack_players_permission(True)
        playerdat.set_build_permission(False)
        playerdat.set_mine_permission(False)
        playerdat.set_attack_mobs_permission(bool(perms["attack_mob"]))
        playerdat.set_containers_permission(bool(perms["container"]))
        playerdat.set_doors_and_switches_permission(bool(perms["switch"]))
        self.game_ctrl.sendwocmd(f"/gamemode 2 @a[name={player},m=!1]")
        self.game_ctrl.sendwocmd(f"/tag @a[name={player},m=!1] add is.visitor")

    def make_player_exit(self, player: str):
        omg = self.frame.launcher.omega
        playerdat = omg.get_player_by_name(player)
        assert playerdat
        playerdat.set_attack_mobs_permission(True)
        playerdat.set_build_permission(True)
        playerdat.set_mine_permission(True)
        playerdat.set_containers_permission(True)
        playerdat.set_doors_and_switches_permission(True)
        playerdat.set_attack_players_permission(True)
        self.game_ctrl.sendwocmd(f"/gamemode 0 @a[name={player},m=!1]")
        self.game_ctrl.sendwocmd(f"/tag @a[name={player},m=!1] remove is.visitor")
        self.game_ctrl.sendwocmd(f"effect @a[name={player}] weakness 0 0")
        self.game_ctrl.sendwocmd(f"tag @a[name={player}] remove weakness255")

    def init_skyblock_player_data(self, uid: int):
        return {
            "own_island": uid,
            "main_island": None,
            "member_island": [],
            "backup_island": None,
        }

    def init_skyblock_island_data(self, uid: int, owner: str, c_pos: list[int]):
        return {"uid": uid, "pos": c_pos, "owner": owner, "members": []}


entry = plugin_entry(SkyBlock, "空岛系统")
