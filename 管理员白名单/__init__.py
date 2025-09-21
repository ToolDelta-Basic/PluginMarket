from tooldelta import Player, Plugin, plugin_entry
from tooldelta.utils import cfg_meta
from tooldelta.constants import PacketIDS


class WLConfig(cfg_meta.JsonSchema):
    enabled: bool = cfg_meta.field("是否启用", True)
    name_whitelist: list[str] = cfg_meta.field("管理员名白名单", [])
    ban_seconds: int = cfg_meta.field("封禁时长秒数(为0则仅踢出,-1则永久)", 864000000)


class OPWhiteList(Plugin):
    name = "管理员白名单"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.config, _ = cfg_meta.get_plugin_config_and_version(
            self.name, WLConfig, self.version
        )
        if not self.config.enabled:
            self.print("此插件为禁用模式")
            return
        if not self.config.name_whitelist:
            self.print_err("管理员白名单为空")
            raise SystemExit("管理员白名单插件: 至少在配置文件添加一名管理员！")
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPacket(PacketIDS.UpdateAbilities, self.on_ability_packet, priority=10000)

    def on_preload(self):
        self.ban = self.GetPluginAPI("封禁系统")
        if 0:
            from 封禁系统 import BanSystem

            self.ban: BanSystem

    def on_active(self):
        for player in self.game_ctrl.players:
            self.test_op(player)
            player.abilities

    def on_player_join(self, player: Player):
        self.test_op(player)

    def on_ability_packet(self, _):
        for player in self.game_ctrl.players:
            self.test_op(player)
        return False

    def test_op(self, player: Player):
        if player is self.game_ctrl.players.getBotInfo():
            return
        if player.is_op() and player.name not in self.config.name_whitelist:
            self.game_ctrl.sendwocmd(f'kick {player.safe_name} "§c不在管理员白名单"')
            self.game_ctrl.say_to("@a", f"§c不在管理员白名单： {player.name}， 已踢出")
            if self.config.ban_seconds != 0:
                self.ban.ban(player, self.config.ban_seconds)


entry = plugin_entry(OPWhiteList)
