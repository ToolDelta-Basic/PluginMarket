from .on_sub_chunk import OnSubChunk
from .auto_request import AutoRequest
from .moving_block_analysis import MovingBlockAnalysis
from .define import AntiInfiniteBlockBase
from tooldelta import Plugin, Frame, plugin_entry
from tooldelta.constants import PacketIDS


class AntiInfiniteBlock(Plugin):
    name = "无限方块反制"
    author = "哈尼卡"
    version = (0, 1, 0)

    def __init__(self, frame: Frame) -> None:
        super().__init__(frame)

        self.anti_infinite_block_base = AntiInfiniteBlockBase(self)
        self.auto_request = AutoRequest(self.anti_infinite_block_base)
        self.moving_block_analysis = MovingBlockAnalysis(self.anti_infinite_block_base)
        self.sub_chunk_analysis = OnSubChunk(self.moving_block_analysis)

        self.ListenPreload(self.anti_infinite_block_base.on_def)
        self.ListenFrameExit(self.auto_request.on_close)
        self.ListenFrameExit(self.moving_block_analysis.on_close)
        self.ListenActive(self.auto_request.on_inject)
        self.ListenActive(self.moving_block_analysis.on_inject)
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
