from tooldelta import plugin_entry, Plugin, ToolDelta, Player, Chat, Print,cfg
from tooldelta.utils import tempjson
from time import time
class PlayerJoinverify(Plugin):
    name = "进服验证"
    author = "大庆油田" 
    version = (0, 0, 1) 

    def __init__(self,frame:ToolDelta):
        super().__init__(frame)
        self.ListenPlayerJoin(self.PlayerJoin)
        self.make_data_path()
        self.path = self.format_data_path("验证数据.json")
        self.ListenPreload(self.on_preload)
        CFG_DEFAULT = {
            "用于接收验证的群": 194838530
        }
        cfg_std = cfg.auto_to_std(CFG_DEFAULT)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg_std, CFG_DEFAULT, self.version
        )
        self.group = self.cfg["用于接收验证的群"]

    def on_preload(self):
        self.qfht = self.GetPluginAPI("群服互通")
        self.qfht.plugin.append("进服验证")

    def get(self) -> dict:
        return tempjson.load_and_read(
                self.path,
                need_file_exists=False,
                default={"白名单":[]}
            )

    def set(self,data):
        tempjson.load_and_write(self.path,data)

    def QQLinker_message(self,data):
        # Print.print(f"{data}")
        if data.get('group_id') == self.group and data.get('message'):
            if data['message'].startswith("#验证"):
                id = data['message'].split()[1]
                a = self.get()
                if (b := a.get(id,False)):
                    a["白名单"].append(b)
                    self.qfht.sendmsg(self.group,"验证成功")
                    self.set(a)
    
    def PlayerJoin(self, player:Player):
        a = self.get()

        if not player.xuid:
            self.game_ctrl.sendwocmd(f'/kick "{player.name}" 您已被踢出游戏：系统内部出现问题，请稍后再试')
            self.game_ctrl.sendwocmd(f'/kick "{player.name}"')
        if not player.xuid in a["白名单"]:
            id = int(time())
            a[id] = player.xuid
            self.game_ctrl.sendwocmd(f'/kick "{player.name}" 您已被踢出游戏：在 {self.group} 发送 #验证 {id}')
            self.game_ctrl.sendwocmd(f'/kick "{player.name}"')
        self.set(a)
        return 0

entry = plugin_entry(PlayerJoinverify,"进服验证")