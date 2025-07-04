from .sub_chunk_analysis import SubChunkAnalysis
from .auto_request import AutoRequest
from .define import AntiInfiniteBlockBase
from tooldelta import Plugin, Frame, plugin_entry
from tooldelta.constants import PacketIDS


class AntiInfiniteBlock(Plugin):
    name = "无限方块反制"
    author = "哈尼卡"
    version = (0, 0, 2)

    def __init__(self, frame: Frame) -> None:
        super().__init__(frame)

        self.anti_infinite_block_base = AntiInfiniteBlockBase(self)
        self.auto_request = AutoRequest(self.anti_infinite_block_base)
        self.sub_chunk_analysis = SubChunkAnalysis(self.anti_infinite_block_base)

        self.ListenPreload(self.anti_infinite_block_base.on_def)
        self.ListenFrameExit(self.auto_request.on_close)
        self.ListenActive(self.auto_request.on_inject)
        self.ListenPacket(
            PacketIDS.BlockActorData, self.auto_request.on_block_actor_data
        )
        self.ListenInternalBroadcast(
            "ggpp:publish_player_position", self.auto_request.on_player_pos
        )
        self.ListenInternalBroadcast(
            "scq:publish_chunk_data", self.sub_chunk_analysis.on_chunk_data
        )


entry = plugin_entry(AntiInfiniteBlock, "无限方块反制")
