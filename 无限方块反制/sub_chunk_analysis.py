from io import BytesIO
from .define import AntiInfiniteBlockBase
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta import (
    GameCtrl,
    InternalBroadcast,
)


class SubChunkAnalysis:
    base: AntiInfiniteBlockBase

    _vector: list[tuple[int, int, int]] = [
        (1, 0, 0),
        (2, 0, 0),
        (-1, 0, 0),
        (-2, 0, 0),
        (0, 1, 0),
        (0, 2, 0),
        (0, -1, 0),
        (0, -2, 0),
        (0, 0, 1),
        (0, 0, 2),
        (0, 0, -1),
        (0, 0, -2),
    ]

    def __init__(self, base: AntiInfiniteBlockBase):
        self.base = base

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

    def is_valid_moving_block(
        self, moving_block_pos: tuple[int, int, int], piston_pos: tuple[int, int, int]
    ) -> bool:
        piston_expected_pos: list[tuple[int, int, int]] = []
        for i in self._vector:
            piston_expected_pos.append(
                (
                    moving_block_pos[0] + i[0],
                    moving_block_pos[1] + i[1],
                    moving_block_pos[2] + i[2],
                ),
            )
        return piston_pos in piston_expected_pos

    def on_chunk_data(self, event: InternalBroadcast):
        nbts: list[dict] = []
        problem_blocks: list[tuple[int, int, int]] = []
        bot_name = self.game_ctrl().bot_name

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

            if not self.is_valid_moving_block(block_pos, piston_pos):
                problem_blocks.append(block_pos)

        for i in problem_blocks:
            x, y, z = i[0], i[1], i[2]

            self.game_ctrl().sendwocmd(
                f'execute as @a[name="{bot_name}"] at @s run setblock {x} {y} {z} cherry_wall_sign'
            )
            self.game_ctrl().sendwscmd_with_resp("")
            self.game_ctrl().sendwscmd_with_resp("")

            self.game_ctrl().sendwocmd(
                f'execute as @a[name="{bot_name}"] at @s run setblock {x} {y} {z} air'
            )
            self.game_ctrl().sendwscmd_with_resp("")
            self.game_ctrl().sendwscmd_with_resp("")

            for command_line in self.base.command_line:
                self.game_ctrl().sendwocmd(
                    f'execute as @a[name="{bot_name}"] at @s positioned {x} {y} {z} run {command_line}'
                )
