from .define import AutoSubChunkRequestBase
from .api import AutoSubChunkRequestAPI
from .sub_chunk_classifier import sub_chunk_classifier
from tooldelta.constants.packets import PacketIDS
from tooldelta.mc_bytes_packet.base_bytes_packet import BaseBytesPacket
from tooldelta.utils import thread_func
from tooldelta.utils.tooldelta_thread import ToolDeltaThread
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
    SubChunk,
)
from tooldelta.internal.launch_cli.neo_libs.blob_hash.packet.define import (
    HashWithPosition,
    SubChunkPos,
)


class AutoSubChunkRequestSubChunkProcess:
    api: AutoSubChunkRequestAPI

    def __init__(self, api: AutoSubChunkRequestAPI):
        self.api = api

    def base(self) -> AutoSubChunkRequestBase:
        return self.api.base()

    def on_sub_chunk(self, pk: BaseBytesPacket) -> bool:
        self._on_sub_chunk(pk)
        return False

    @thread_func(
        usage="主动区块请求: 处理 Sub Chunk 数据包", thread_level=ToolDeltaThread.SYSTEM
    )
    def _on_sub_chunk(self, pk: BaseBytesPacket):
        assert type(pk) is SubChunk, "Should Nerver happened"

        # Note that it's possible for self.base().blob_hash is not exist,
        # maybe the plugin was executed before it was injected.
        if "blob_hash" not in self.base().__dict__:
            return

        if len(pk.Entries) == 0:
            return

        # sub_chunk_finish_states holds a list that for a sub chunk
        # entry in pk.Entries[i], this sub chunk entry is
        # finished or unfinished.
        #
        # Unfinished sub chunk entry means that the payload of
        # this entry need ask blob hash holder (server side) to get.
        sub_chunk_finish_states = [False for _ in range(len(pk.Entries))]

        # pending_blob_hash is the missing blob hash that need to
        # ask blob hash holder (server side) to get.
        pending_blob_hash: list[HashWithPosition] = []

        # unloaded_sub_chunk holds a list that contains some failed sub chunk
        # entries. These sub chunks failed due to  server has not loaded them,
        # and will be load in the future.
        # Therefore, we need to record these entires and resend packet.SubChunkRequest
        # to reget them.
        unloaded_sub_chunk: list[SubChunkPos] = []

        for index in range(len(pk.Entries)):
            entry = pk.Entries[index]

            if entry.Result == SUB_CHUNK_RESULT_SUCCESS_ALL_AIR:
                self.api.try_publish_chunk_data(
                    entry.Result,
                    pk.Dimension,
                    (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                    b"",
                    b"",
                )
                sub_chunk_finish_states[index] = True
                continue

            if entry.Result != SUB_CHUNK_RESULT_SUCCESS:
                # We compute if current sub chunk entry could reached by the bot
                is_include = False
                for _, value in self.base().multiple_pos.items():
                    if (
                        abs(entry.SubChunkPosX - value.pos.x)
                        <= self.base().request_radius
                        and abs(entry.SubChunkPosZ - value.pos.z)
                        <= self.base().request_radius
                        and pk.Dimension == value.pos.dim
                    ):
                        is_include = True
                        break
                # This sub chunk entry failed due to the bot is
                # moved to another place that can't reach this sub chunk.
                # Therefore, set result as failed immediately.
                if not is_include:
                    self.api.try_publish_chunk_data(
                        entry.Result,
                        pk.Dimension,
                        (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                        b"",
                        b"",
                    )
                # Or, this sub chunk is not loaded, and waiting server to load them.
                # Therefore, we add to unloaded sub chunk list, and them reget them
                # in a single packet.SubChunkRequest packet.
                else:
                    unloaded_sub_chunk.append(
                        SubChunkPos(
                            entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ
                        )
                    )
                # Although this sub chunk failed, due to we do the corresponding
                # process, so we can set them as finished safely.
                sub_chunk_finish_states[index] = True
                continue

            if pk.CacheEnabled:
                # Firstly, we check local blob hash list.
                # If blob hash not hit, ask blob hash holder (server side)
                # to get payload.
                payload = self.base().blob_hash.load_blob_cache(entry.BlobHash)
                # payload is empty bytes means that this blob hash needs
                # us to ask blob hash holder (server side) to get.
                if len(payload) == 0:
                    pending_blob_hash.append(
                        HashWithPosition(
                            entry.BlobHash,
                            SubChunkPos(
                                entry.SubChunkPosX,
                                entry.SubChunkPosY,
                                entry.SubChunkPosZ,
                            ),
                            pk.Dimension,
                        )
                    )
                    continue
                # When blob hash is enabled, the entry.RawPayload will
                # only holds the Block Entity NBT data of this sub chunk.
                sub_chunk_finish_states[index] = True
                self.api.try_publish_chunk_data(
                    entry.Result,
                    pk.Dimension,
                    (
                        entry.SubChunkPosX,
                        entry.SubChunkPosY,
                        entry.SubChunkPosZ,
                    ),
                    payload,
                    entry.NBTData.tobytes(),
                )

        # Request these failed sub chunks due to server is still loading them.
        if len(unloaded_sub_chunk) > 0:
            multiple_sub_chunks: list[tuple[int, tuple[int, int, int]]] = []
            for i in unloaded_sub_chunk:
                multiple_sub_chunks.append((pk.Dimension, (i.x, i.y, i.z)))
            for i in sub_chunk_classifier(multiple_sub_chunks):
                try:
                    self.base().game_ctrl.sendPacket(PacketIDS.IDSubChunkRequest, i)
                except Exception:
                    pass

        # Request missing blob hash from server-side blob hash holder.
        if len(pending_blob_hash) > 0:
            # Retry 3 times, due to blob hash holder may haven't started
            # processing on this sub chunk packet when here we have already
            # receive sub chunk packet.
            for _ in range(3):
                hit_hashes: dict[HashWithPosition, bool] = {}
                new_pending_blob_hash: list[HashWithPosition] = []

                resp = (
                    self.base()
                    .blob_hash.get_client_function()
                    .get_hash_payload(pending_blob_hash)
                )

                # hitHashes record how many blob
                # hash we get from blob hash holder
                # (server side)
                for key in resp:
                    hit_hashes[key] = True

                # new_pending_blob_hash holds the blob hash we still not have
                for i in pending_blob_hash:
                    if i not in hit_hashes:
                        new_pending_blob_hash.append(i)

                # set pending_blob_hash as new_pending_blob_hash.
                # And if len(pending_blob_hash) == 0,
                # then all blob hash we missing is hit and
                # here we should break retry
                pending_blob_hash = new_pending_blob_hash
                if len(pending_blob_hash) == 0:
                    break

        failed_sub_chunks: list[SubChunkPos] = []

        # Now we get most (hash, payload) for those
        # unfinished sub chunk entry.
        # Therefore, we start to finish those entries.
        for index in range(len(pk.Entries)):
            if sub_chunk_finish_states[index]:
                continue
            entry = pk.Entries[index]

            # We try to reload blob hash from local cache again.
            payload = self.base().blob_hash.load_blob_cache(entry.BlobHash)
            # payload is empty bytes refer to this sub chunk entry is still
            # missing its payload, and that means this sub chunk entry
            # is failed.
            # For those failed sub chunk entries, we send new
            # packet.SubChunkRequest to reget those entries.
            if len(payload) == 0:
                failed_sub_chunks.append(
                    SubChunkPos(
                        entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ
                    )
                )
                continue
            # When blob hash is enabled, the entry.RawPayload will
            # only holds the Block Entity NBT data of this sub chunk.
            sub_chunk_finish_states[index] = True
            self.api.try_publish_chunk_data(
                entry.Result,
                pk.Dimension,
                (entry.SubChunkPosX, entry.SubChunkPosY, entry.SubChunkPosZ),
                payload,
                entry.NBTData.tobytes(),
            )

        # There is some sub chunk entries failed,
        # and here we resent sub chunk request to
        # reget them.
        if len(failed_sub_chunks) > 0:
            multiple_sub_chunks: list[tuple[int, tuple[int, int, int]]] = []
            for i in failed_sub_chunks:
                multiple_sub_chunks.append((pk.Dimension, (i.x, i.y, i.z)))
            for i in sub_chunk_classifier(multiple_sub_chunks):
                try:
                    self.base().game_ctrl.sendPacket(PacketIDS.IDSubChunkRequest, i)
                except Exception:
                    pass

        return
