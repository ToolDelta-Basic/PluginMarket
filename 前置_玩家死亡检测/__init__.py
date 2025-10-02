from collections.abc import Callable
from tooldelta import Plugin, plugin_entry, Player
from tooldelta.constants import PacketIDS


class NewPlugin(Plugin):
    name = "anti"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._die_cbs: list[Callable[[Player], None]] = []
        self._respawn_cbs: list[Callable[[Player], None]] = []
        self.ListenPacket(PacketIDS.PyRpc, self.on_pyrpc)

    def on_pyrpc(self, pk: dict):
        self._test_die(pk)
        return False

    ############################# API #############################

    def listen_player_die(self, cb: Callable[[Player], None]):
        """
        注册玩家死亡事件监听器

        Args:
            cb (Callable[[Player], None]): 监听回调函数
        """
        self._die_cbs.append(cb)

    def listen_player_respawn(self, cb: Callable[[Player], None]):
        """
        注册玩家重生事件监听器监听器

        Args:
            cb (Callable[[Player], None]): 监听回调函数
        """
        self._respawn_cbs.append(cb)

    ################################################################

    def _test_die(self, pk: dict):
        values = pk["Value"]
        if len(values) != 3:
            return
        eventType, contents = values[0:2]
        if eventType != "ModEventS2C":
            return
        elif len(contents) != 4:
            return
        eventName, eventData = contents[2:4]
        if eventName != "OnPlayerDie":
            return
        die = eventData["die"]
        playerUniqueID = int(eventData["pid"])
        player = self.game_ctrl.players.getPlayerByUniqueID(playerUniqueID)
        if player is None:
            return
        if die:
            self._on_die(player)
        else:
            self._on_respawn(player)

    def _on_die(self, player: Player):
        for cb in self._die_cbs:
            cb(player)

    def _on_respawn(self, player: Player):
        for cb in self._respawn_cbs:
            cb(player)


entry = plugin_entry(NewPlugin, "玩家死亡检测")
