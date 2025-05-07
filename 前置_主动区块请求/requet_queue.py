import threading
import time
from tooldelta import InternalBroadcast
from tooldelta.constants.packets import PacketIDS
from tooldelta.mc_bytes_packet import sub_chunk_request
from tooldelta.utils import thread_func
from tooldelta.utils.tooldelta_thread import ToolDeltaThread

from 前置_主动区块请求.api import AutoSubChunkRequestAPI
from 前置_主动区块请求.define import (
    EMPTY_CHUNK_POS_WITH_DIMENSION,
    EMPTY_SINGLE_SUB_CHUNK,
    AutoSubChunkRequestBase,
    ChunkListener,
    ChunkPosWithDimension,
    DimChunkPosWithUnixTime,
)


class AutoSubChunkRequetQueue:
    api: AutoSubChunkRequestAPI

    def __init__(self, api: AutoSubChunkRequestAPI):
        self.api = api

    def base(self) -> AutoSubChunkRequestBase:
        return self.api.base()

    @thread_func(
        usage="主动区块请求: 自动请求区块", thread_level=ToolDeltaThread.SYSTEM
    )
    def send_request_queue(self):
        self.base().injected = True
        while True:
            self.base().mu.acquire()

            count = len(self.base().multiple_pos) * self.base().request_chunk_per_second
            key_to_delete: list[ChunkPosWithDimension] = []

            if self.base().should_close:
                for _, listener in self.base().chunk_listener.items():
                    listener.channel.set()
                self.base().requet_queue.clear()
                self.base().chunk_listener.clear()
                self.base().close_waiter.release()
                self.base().mu.release()
                return

            for key, value in self.base().requet_queue.items():
                if count <= 0:
                    break
                self.base().game_ctrl.sendPacket(PacketIDS.IDSubChunkRequest, value)
                key_to_delete.append(key)
                count -= 1

            for i in key_to_delete:
                del self.base().requet_queue[i]

            self.base().mu.release()

            if not self.base().should_close:
                time.sleep(1)

    def append_to_request_queue(self, dimension: int, center: tuple[int, int]):
        y_range = (-4, 19)
        if dimension == 1:
            y_range = (0, 7)
        if dimension == 2:
            y_range = (0, 15)

        all_chunks: list[tuple[int, int]] = [(center[0], center[1])]

        last_x = center[0]
        last_z = center[1]
        facing_round = 0
        facing = [(0, 1), (1, 0), (0, -1), (-1, 0)]

        for current_round in range(2 * self.base().request_radius + 1):
            idx = facing_round % 4
            idx2 = (facing_round + 1) % 4

            for step_forward in range(current_round + 1):
                zoom = step_forward + 1
                current_x = last_x + zoom * facing[idx][0]
                current_z = last_z + zoom * facing[idx][1]
                all_chunks.append((current_x, current_z))

            last_x = all_chunks[-1][0]
            last_z = all_chunks[-1][1]

            for step_forward in range(current_round + 1):
                zoom = step_forward + 1
                current_x = last_x + zoom * facing[idx2][0]
                current_z = last_z + zoom * facing[idx2][1]
                all_chunks.append((current_x, current_z))

            last_x = all_chunks[-1][0]
            last_z = all_chunks[-1][1]
            facing_round += 2

        all_chunks = all_chunks[: -2 - 2 * self.base().request_radius]

        self.base().mu.acquire()
        for chunk in all_chunks:
            chunk_pos_with_dim = ChunkPosWithDimension(chunk[0], chunk[1], dimension)

            if (
                chunk_pos_with_dim in self.base().chunk_listener
                or chunk_pos_with_dim in self.base().requet_queue
            ):
                continue

            pk = sub_chunk_request.SubChunkRequest(dimension, chunk[0], 0, chunk[1])
            pk.Offsets = [(0, y, 0) for y in range(y_range[0], y_range[1] + 1)]
            self.base().requet_queue[chunk_pos_with_dim] = pk

            self.base().chunk_listener[chunk_pos_with_dim] = ChunkListener(
                [EMPTY_SINGLE_SUB_CHUNK for _ in range(32)], False, threading.Event()
            )
        self.base().mu.release()

    def on_player_position(self, event: InternalBroadcast):
        if self.base().game_ctrl.bot_name not in event.data:
            return

        current_unix_time = int(time.time())

        # Clean to make memory happy
        bot_dimension: int = event.data[self.base().game_ctrl.bot_name]["dimension"]
        new_mapping: dict[str, DimChunkPosWithUnixTime] = {}
        for key in event.data:
            if event.data[key]["dimension"] != bot_dimension:
                continue
            if key in self.base().multiple_pos:
                new_mapping[key] = self.base().multiple_pos[key]
            else:
                new_mapping[key] = DimChunkPosWithUnixTime(
                    0, EMPTY_CHUNK_POS_WITH_DIMENSION
                )
        self.base().multiple_pos = new_mapping

        # We here try to cancel the chunks that beyond the reach of bot
        self.base().mu.acquire()
        cancel_list: list[ChunkPosWithDimension] = []
        for dim_chunk_pos in self.base().requet_queue:
            could_be_reach = False

            for _, pos in self.base().multiple_pos.items():
                if (
                    abs(pos.pos.x - dim_chunk_pos.x) <= self.base().request_radius
                    and abs(pos.pos.z - dim_chunk_pos.z) <= self.base().request_radius
                    and pos.pos.dim == dim_chunk_pos.dim
                ):
                    could_be_reach = True
                    break

            if not could_be_reach:
                cancel_list.append(dim_chunk_pos)

        for i in cancel_list:
            self.api.set_chunk_all_failed_and_publish(i.dim, (i.x, i.z))
        self.base().mu.release()

        if self.base().should_close:
            return

        # Actually speaking, by the way you read to here,
        # you may know our logic is not very common.
        # Note that this is a key point, don't let others known.
        for key, value in self.base().multiple_pos.items():
            if key not in event.data:
                continue

            current_data = event.data[key]
            current_dimension: int = current_data["dimension"]
            current_chunk_pos_x = int(current_data["x"]) >> 4
            current_chunk_pos_z = int(current_data["z"]) >> 4

            if (
                current_unix_time - value.last_update_unix_time
                >= self.base().force_update_time
                or current_dimension != value.pos.dim
                or current_chunk_pos_x != value.pos.x
                or current_chunk_pos_z != value.pos.z
            ):
                self.base().multiple_pos[key] = DimChunkPosWithUnixTime(
                    current_unix_time,
                    ChunkPosWithDimension(
                        current_chunk_pos_x, current_chunk_pos_z, current_dimension
                    ),
                )
                self.append_to_request_queue(
                    current_dimension, (current_chunk_pos_x, current_chunk_pos_z)
                )

        if not self.base().must_chunk_position_waiter.acquire(timeout=0):
            self.base().must_chunk_position_waiter.release()
        else:
            self.base().must_chunk_position_waiter.release()
