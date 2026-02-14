from .define import FlowersForMachineBase
from .server_running import FlowersForMachineServerRunning
from .chest_cache import ChestCache
from .place_nbt_block import PlaceNBTBlock
from .place_large_chest import PlaceLargeChest
from .get_nbt_block_hash import GetNBTBlockHash
from tooldelta import Plugin, Frame, plugin_entry


class FlowersForMachine(Plugin):
    name = "献给机械の花束"
    author = "2B, 9S and 6O"
    version = (1, 5, 0)

    _base: FlowersForMachineBase
    _server_running: FlowersForMachineServerRunning

    place_nbt_block: PlaceNBTBlock
    place_large_chest: PlaceLargeChest
    get_nbt_block_hash: GetNBTBlockHash

    def __init__(self, frame: Frame):
        super().__init__(frame)

        self._base = FlowersForMachineBase(self)
        self._server_running = FlowersForMachineServerRunning(self._base)

        self.place_nbt_block = PlaceNBTBlock(self._server_running)
        self.place_large_chest = PlaceLargeChest(self._server_running)
        self.get_nbt_block_hash = GetNBTBlockHash(self._server_running)

        self.ListenPreload(self._base.on_def)
        self.ListenActive(self._server_running.on_inject)
        self.ListenFrameExit(self._server_running.on_close)

    def get_chest_cache(self) -> ChestCache:
        return self._base.chest_cache


entry = plugin_entry(FlowersForMachine, "献给机械の花束")
