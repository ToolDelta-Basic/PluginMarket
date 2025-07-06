from io import BytesIO
from .define import AntiInfiniteBlockBase
from .moving_block_analysis import MovingBlockAnalysis
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta import (
    GameCtrl,
    InternalBroadcast,
)


class OnSubChunk:
    base: AntiInfiniteBlockBase

    def __init__(self, analysis: MovingBlockAnalysis):
        self.base = analysis.base
        self.analysis = analysis

    def game_ctrl(self) -> GameCtrl:
        return self.base.plugin.game_ctrl

    def check_sub_chunks_all_success(self, event: InternalBroadcast) -> bool:
        if not isinstance(event.data, list):
            return False

        for i in event.data:
            code = i["result_code"]
            if (
                code != SUB_CHUNK_RESULT_SUCCESS
                and code != SUB_CHUNK_RESULT_SUCCESS_ALL_AIR
            ):
                return False

        return True

    def on_chunk_data(self, event: InternalBroadcast):
        nbts: list[dict] = []

        if self.base.nbt_unmarshal is None:
            return
        if not self.check_sub_chunks_all_success(event):
            return

        for i in event.data:
            current_nbt_data = i["nbts"]
            length = len(current_nbt_data)
            buf = BytesIO(current_nbt_data)

            while buf.seek(0, 1) != length:
                nbts.append(self.base.nbt_unmarshal(buf)[0])

        for i in nbts:
            if str(i["id"]) != "MovingBlock":
                continue

            block_pos = (int(i["x"]), int(i["y"]), int(i["z"]))
            piston_pos = (
                int(i["pistonPosX"]),
                int(i["pistonPosY"]),
                int(i["pistonPosZ"]),
            )

            self.analysis.append_to_pending_list(block_pos, piston_pos)
