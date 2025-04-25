import json
from tooldelta import (
    Plugin,
    plugin_entry,
    Player,
    cfg,
    utils,
    fmts,
)
from file import read, write


class NewPlugin(Plugin):
    name = "兑换码"
    author = "机入"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        configa = {
            "兑换码": [
                {
                    "兑换码": "ABCDEFGH",
                    "指令": "say [player]成功使用兑换码",
                    "可以使用次数": 10,
                },
                {
                    "兑换码": "114514",
                    "指令": "kick [player] 快哉快哉",
                    "可以使用次数": 100,
                },
            ]
        }
        configs = {"兑换码": cfg.JsonList(dict, len_limit=-1)}
        config, version = cfg.get_plugin_config_and_version(
            "兑换码",
            configs,
            configa,
            (0, 0, 1),
        )
        self.data = config
        self.dh = ".存储兑换码记录.json"
        self.ListenPreload(self.core)

    def core(self):
        memu = self.GetPluginAPI("聊天栏菜单")
        memu.add_new_trigger(
            ["dh", "兑换码"], [("兑换码", str, None)], None, self.start, op_only=False
        )

    @utils.thread_func("兑换码")
    def start(self, player: Player, args: tuple):
        list = self.data["兑换码"]
        for key in list:
            if key["兑换码"] in args[0]:
                text = read(self.dh)
                if not text: #生成存储文件
                    fmts.print_err("已生成存储文件")
                    write(self.dh, "{}")
                    return
                data = json.loads(text)
                if data.get(args[0]) is None:
                    data[args[0]] = {"player": [player.uuid], "limit": 1}
                    write(self.dh, json.dumps(data))
                else:
                    if player.uuid in data.get(args[0]).get("player"):
                        player.show("§l§e你已使用过兑换码") #使用过提示
                        return
                    if data.get(args[0]).get("limit") >= key["可以使用次数"]:
                        player.show("§l§c兑换码已失效")#激活码使用总次数上限
                        return
                    a = data.get(args[0]).get("limit")
                    b = data.get(args[0]).get("player")
                    b.append(player.uuid)
                    data.get(args[0])["limit"] = a + 1
                    write(self.dh, json.dumps(data))
                c = key["指令"]
                d = c.replace("[player]", player.name)
                player.show("§l§a激活码使用成功")
                self.game_ctrl.sendwocmd(d)
                return
        else:
            player.show("§c兑换码错误")

entry = plugin_entry(NewPlugin)
