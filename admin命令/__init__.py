from tooldelta.cfg import Config
from tooldelta.plugin_load.injected_plugin import player_message, player_message_info

from tooldelta.game_utils import (
    is_op,
    sendwscmd,
    rawText,
)

__plugin_meta__ = {
    "name": "admin命令",
    "version": "0.0.2",
    "author": "wling/Hadwin",
}

cmdarea = {"指令区坐标": dict}
DEFAULT_CFG = {"指令区坐标": {"x": 0, "y": 0, "z": 0}}

cfg, cfg_version = Config.get_plugin_config_and_version(
    __plugin_meta__["name"],
    cmdarea,
    DEFAULT_CFG,
    __plugin_meta__["version"].split("."),
)


@player_message()
async def _(playermessage: player_message_info):
    msg = playermessage.message
    playername = playermessage.playername
    if not is_op(playername):
        return
    match msg:
        case ".admin" | ".admin ":  # 管理员可以使用的命令的帮助.
            rawText(
                playername,
                """§r输入§l§b.gm1§r改为创造模式\n输入§l§b.cmdarea§r前往指令区\n§r输入§l§b.inv§r获得隐身\n输入§l§b.nv§r获得夜视\n§r输入§l§b.ec§r清除药水""",
            )
            rawText(
                playername,
                """§r输入§l§b.clear§r清空背包\n§r输入§l§b.adminbag§r获取管理员物品\n§r输入§l§a.wt§r天气与时间控制菜单(§o§a开放§r)""",
            )
        case ".gm1" | ".gmc" | ".cz":  # 改创造模式
            sendwscmd("/gamemode 1 " + playername)
            rawText(playername, "您的状态已刷新")
        case ".cmdarea" | ".cmdArea":  # 前往指令区
            sendwscmd(
                f"/tp {playername} {cmdarea.get('x')} {cmdarea.get('y')} {cmdarea.get('z')}"
            )
            rawText(playername, "§b已将您传送至指令区.")
        case ".inv" | ".INV":  # 改为隐身
            sendwscmd(f"effect {playername} invisibility 99999 1 true")
            rawText(playername, "您的状态已刷新")
        case ".nv" | ".NV":  # 改为夜视
            sendwscmd(f"effect {playername} night_vision 99999 1 true")
            rawText(playername, "您的状态已刷新")
        case ".ec" | ".EC":  # 清除药水效果
            sendwscmd("/effect " + playername + " clear")
            rawText(playername, "您的状态已刷新")
        case ".clear" | ".CLEAR":  # 清空背包
            sendwscmd("/clear " + playername + "")
            rawText(playername, "您的背包已清空")
        case ".adminbag" | ".adminbag":  # 获取管理员物品
            sendwscmd("/give " + playername + " chain_command_block")
            sendwscmd("/give " + playername + " deny")
            sendwscmd("/give " + playername + " allow")
            sendwscmd("/give " + playername + " border_block")
            sendwscmd("/give " + playername + " barrier")
            sendwscmd("/give " + playername + " structure_block")
            rawText(
                playername,
                "§b已给予:链命令方块|拒绝方块|允许方块|边界方块|屏障|结构方块",
            )
        case ".wt" | ".WT":  # 天气与时间控制菜单.
            rawText(
                playername,
                "§r§l§b天气与时间 帮助菜单\n§r========§l§e天气§r========\n输入§l§e.wclear晴天\n§r输入§l§b.wrain雨天\n§r输入§l§7.wtdr雷暴",
            )
            rawText(
                playername,
                "========§l§b时间§r========\n输入§l§6.tsr日出\n§r输入§l§e.tday白日\n§r输入§l§e.tn中午\n§r输入§l§6.tss日落\n§r输入§l§b.tnt夜晚\n§r输入§l§7.tmn深夜",
            )
        case ".wclear" | ".WCLEAR":  # 晴天
            sendwscmd("/weather clear")
            rawText(
                "@a",
                "已将天气设为§e晴天",
            )

        case ".wrain" | ".WRAIN":  # 雨天
            sendwscmd("/weather rain")
            rawText(
                "@a",
                "已将天气设为§b雨天",
            )
        case ".wtdr" | ".WTDR":  # 雷暴
            sendwscmd("/weather thunder")
            rawText(
                "@a",
                "已将天气设为§7雷暴.",
            )
        case ".tsr" | ".TSR":  # 日出
            sendwscmd("/time set sunrise")
            rawText(
                "@a",
                "已将时间设为§6日出.",
            )
        case ".tday" | ".TDAY":  # 白日
            sendwscmd("/time set day")
            rawText(
                "@a",
                "已将时间设为§e白日.",
            )
        case ".tn" | ".TN":  # 中午
            sendwscmd("/time set noon")
            rawText(
                "@a",
                "已将时间设为§e中午.",
            )
        case ".tss" | ".TSS":  # 日落
            sendwscmd("/time set sunset")
            rawText(
                "@a",
                "已将时间设为§6日落.",
            )
        case ".tnt" | ".TNT":  # 夜晚
            sendwscmd("/time set night")
            rawText(
                "@a",
                "已将时间设为§b夜晚.",
            )
        case ".tmn" | ".TMN":  # 深夜
            sendwscmd("/time set midnight")
            rawText(
                "@a",
                "已将时间设为§7深夜.",
            )
