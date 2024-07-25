import anyio
import ujson as json
import os
from tooldelta.game_utils import getPos, getTarget
from tooldelta.plugin_load.injected_plugin import player_message, player_message_info
from tooldelta.game_utils import tellrawText
from 维度传送 import tp
from tooldelta import plugins
from tooldelta.frame import Config


__plugin_meta__ = {
    "name": "传送点",
    "version": "0.0.2",
    "author": "wling/7912",
}

STD_HOME_MAX_NUM = {"最大传送点数量": int}
DEFAULT_BAN_CFG = {
    "最大传送点数量": 3,
}


cfg, cfg_version = Config.getPluginConfigAndVersion(
    __plugin_meta__["name"],
    STD_HOME_MAX_NUM,
    DEFAULT_BAN_CFG,
    __plugin_meta__["version"].split("."),
)

HOME_MAX_NUM = cfg["最大传送点数量"]


plugin_path = r"插件数据文件/传送点"
data_path = plugin_path + r"/传送点.json"
os.makedirs(plugin_path, exist_ok=True)
if not os.path.isfile(data_path):
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4, ensure_ascii=False)

plugins.get_plugin_api("聊天栏菜单").add_trigger(
    ["home"], "", "查看传送点插件帮助", None, op_only=True
)


def translateDim(dimension):
    if dimension == 0:
        return "主世界"
    if dimension == 1:
        return "地狱"
    if dimension == 2:
        return "末地"
    raise ValueError("维度只能是0, 1或2.")


@player_message()
async def _(playermessage: player_message_info):
    msg = playermessage.message
    playername = playermessage.playername
    if msg.startswith(".home"):
        tellrawText(
            playername,
            text="""\
.home tp <传送点名称> §o§7- 传送到传送点.§r
.home add <传送点名称> §o§7- 在当前位置新建传送点.§r
.home del <传送点名称> §o§7- 删除传送点.§r
.home list §o§7- 列出传送点.§r""",
        )
    elif msg.startswith(".home add "):
        homeName = msg.split(" ", 2)[2]
        if (len(homeName) < 1) or (len(homeName) > 6):
            tellrawText(
                f'@a[name="{playername}"]',
                "§l§4ERROR§r",
                "§c传送点名称应为 §l1~6§r§c 个字符.",
            )
            return
        async with await anyio.open_file(data_path) as f:
            homedata = json.loads(await f.read())
        # 查找玩家数据

        # 检查字典中是否有玩家数据
        if playername not in homedata:
            homedata[playername] = []

        if playername in getTarget("@a[m=2]"):
            tellrawText(f'@a[name="{playername}"]', "§l传送点§r", "冒险模式禁止使用！")
            return
        if HOME_MAX_NUM > -1:
            if len(homedata[playername]) >= HOME_MAX_NUM:
                tellrawText(
                    f'@a[name="{playername}"]',
                    "§l§4ERROR§r",
                    "§c传送点数量达到上限. (§l%d§r§c 个)." % HOME_MAX_NUM,
                )
                return
        for home in homedata[playername]:
            if home["name"] == homeName:
                tellrawText(f'@a[name="{playername}"]', "§l§4ERROR§r", "§c传送点重名.")
                return

        playerPos = getPos(playername)
        homedata[playername].append(
            {
                "name": homeName,
                "dim": playerPos["dimension"],
                "pos": f'{playerPos["position"]["x"]} {playerPos["position"]["y"]} {playerPos["position"]["z"]}',
            }
        )
        tellrawText(
            f'@a[name="{playername}"]',
            "§l传送点§r",
            f'已设置传送点 §l{homeName}§r [§l{translateDim(playerPos["dimension"])}§r, (§l{playerPos["position"]["x"]}§r, §l{playerPos["position"]["y"]}§r, §l{playerPos["position"]["z"]}§r)].',
        )
        async with await anyio.open_file(data_path, "w") as f:
            await f.write(json.dumps(homedata, ensure_ascii=False, indent=4))

    elif msg.startswith(".home del "):
        homeName = msg.split(" ", 2)[2]
        async with await anyio.open_file(data_path, "r") as f:
            homedata = json.loads(await f.read())
        # 查找玩家数据
        if playername not in homedata:
            tellrawText(
                f'@a[name="{playername}"]', "§l§4ERROR§r", "§c你似乎没有传送点数据."
            )
            return
        for home in homedata[playername]:
            if home["name"] == homeName:
                homedata[playername].remove(home)
                homeX, homeY, homeZ = home["pos"].split(" ", 2)
                async with await anyio.open_file(data_path, "w") as f:
                    await f.write(json.dumps(homedata, ensure_ascii=False, indent=4))
                tellrawText(
                    f'@a[name="{playername}"]',
                    "§l传送点§r",
                    f'已删除传送点 §l{homeName}§r [§l{translateDim(home["dim"])}§r, (§l{homeX}§r, §l{homeY}§r, §l{homeZ}§r)].',
                )
                return
        tellrawText(f'@a[name="{playername}"]', "§l§4ERROR§r", "§c未找到传送点.")

    elif msg.startswith(".home tp "):
        homeName = msg.split(" ", 2)[2]
        async with await anyio.open_file(data_path) as f:
            homedata = json.loads(await f.read())
        # 查找玩家数据
        if playername not in homedata:
            tellrawText(
                f'@a[name="{playername}"]', "§l§4ERROR§r", "§c你似乎没有传送点数据."
            )
            return
        for home in homedata[playername]:
            if home["name"] == homeName:
                homeX, homeY, homeZ = home["pos"].split(" ", 2)
                tp(
                    f'@a[name="{playername}"]',
                    x=homeX,
                    y=homeY,
                    z=homeZ,
                    dimension=home["dim"],
                )
                tellrawText(
                    f'@a[name="{playername}"]',
                    "§l传送点§r",
                    f'已传送到传送点 §l{homeName}§r [§l{translateDim(home["dim"])}§r, (§l{homeX}§r, §l{homeY}§r, §l{homeZ}§r)].',
                )
                return
        tellrawText(f'@a[name="{playername}"]', "§l§4ERROR§r", "§c未找到传送点.")

    elif msg == ".home list":
        async with await anyio.open_file(data_path) as f:
            homedata = json.loads(await f.read())
        # 查找玩家数据
        if playername not in homedata:
            tellrawText(
                f'@a[name="{playername}"]', "§l§4ERROR§r", "§c你似乎没有传送点数据."
            )
            return
        tellrawText(playername, "§l传送点§r", "传送点列表: ")
        # enumerate 函数是将列表前面加上序号, 这样就可以便捷显示序号了. 这里序号存在了 index 中.
        for index, home in enumerate(homedata[playername]):
            homeX, homeY, homeZ = home["pos"].split(" ", 2)
            tellrawText(
                playername,
                "§l%d§r: §l%s§r [§l%s§r, (§l%s§r, §l%s§r, §l%s§r)]"
                % (
                    index + 1,
                    home["name"],
                    translateDim(home["dim"]),
                    homeX,
                    homeY,
                    homeZ,
                ),
            )
    return None
