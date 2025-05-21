import time
import datetime
from io import BytesIO
from tooldelta import (
    FrameExit,
    InternalBroadcast,
    Plugin,
)
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta.utils import fmts
from .define import WorldBackupBase


class WorldBackupMain:
    world_backup_base: WorldBackupBase

    def __init__(self, world_backup_base: WorldBackupBase):
        self.world_backup_base = world_backup_base

    def base(self) -> WorldBackupBase:
        return self.world_backup_base

    def plugin(self) -> Plugin:
        return self.base().plugin

    def on_def(self):
        global chunkdiff, bwo
        _ = self.plugin().GetPluginAPI("世界の记忆", (0, 0, 4))
        _ = self.plugin().GetPluginAPI("简单世界恢复", (0, 0, 4))

        pip = self.plugin().GetPluginAPI("pip")
        if 0:
            from pip模块支持 import PipSupport

            pip: PipSupport
        pip.require({"bedrock-chunk-diff": "bedrockchunkdiff"})
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        import bedrockchunkdiff as chunkdiff
        import bedrockworldoperator as bwo

    def on_inject(self):
        self.db = chunkdiff.new_timeline_database(
            self.plugin().format_data_path(self.base().db_name),
            self.base().no_grow_sync,
            self.base().no_sync,
        )
        if not self.db.is_valid():
            raise Exception(
                "世界备份第二世代: 打开数据库失败，请检查数据库是否被占用或是否已损坏"
            )

    def on_close(self, _: FrameExit):
        self.do_close()

    def do_close(self):
        self.base().running_mutex.acquire()
        self.base().should_close = True
        if "db" in self.__dict__ and self.db.is_valid():
            self.db.close_timeline_db()
        self.base().running_mutex.release()

    def check_sub_chunks_all_success(self, event: InternalBroadcast) -> bool:
        for i in event.data:
            code = i["result_code"]
            if (
                code != SUB_CHUNK_RESULT_SUCCESS
                and code != SUB_CHUNK_RESULT_SUCCESS_ALL_AIR
            ):
                return False
        return True

    def get_sub_chunks_payload_and_nbts(
        self, event: InternalBroadcast
    ) -> tuple[list[bytes], bytes]:
        sub_chunks_data: list[bytes] = []
        nbts = BytesIO()

        r = bwo.Dimension(event.data[0]["dimension"]).range()

        for index in range(len(event.data)):
            data = event.data[index]
            if data["result_code"] == SUB_CHUNK_RESULT_SUCCESS_ALL_AIR:
                s = bwo.new_sub_chunk()
                payload = bwo.sub_chunk_network_payload(s, index, r)
                sub_chunks_data.append(payload)
            else:
                sub_chunks_data.append(data["blocks"])
                nbts.write(data["nbts"])

        return sub_chunks_data, nbts.getvalue()

    def get_time_diff_str(self, start_time: int, end_time: int) -> str:
        s = datetime.datetime.fromtimestamp(start_time)
        e = datetime.datetime.fromtimestamp(end_time)
        diff = e - s

        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return f"{days}天{hours}时{minutes}分{seconds}秒"

    def on_chunk_data(self, event: InternalBroadcast):
        self.base().running_mutex.acquire()
        if not self.base().should_close:
            self._on_chunk_data(event)
        self.base().running_mutex.release()

    def _on_chunk_data(self, event: InternalBroadcast):
        if "db" not in self.__dict__:
            return

        if not self.check_sub_chunks_all_success(event):
            return

        cp = bwo.ChunkPos(
            event.data[0]["sub_chunk_pos_x"], event.data[0]["sub_chunk_pos_z"]
        )
        dim = bwo.Dimension(event.data[0]["dimension"])

        current_unix_time = int(time.time())
        before_unix_time = self.db.load_latest_time_point_unix_time(cp, dim)

        if (
            before_unix_time == 0
            or current_unix_time - before_unix_time >= self.base().sync_delta_time
        ):
            if self.base().enable_debug:
                if before_unix_time == 0:
                    fmts.print_inf(f"{dim} {cp} 不存在时间, 直接同步到前一天存档")
                else:
                    fmts.print_inf(
                        f"{dim} {cp} 距离现在时间 {self.get_time_diff_str(before_unix_time, current_unix_time)}, 移动并写入"
                    )
        else:
            if self.base().enable_debug:
                fmts.print_inf(
                    f"{dim} {cp} 距离现在时间 {self.get_time_diff_str(before_unix_time, current_unix_time)}, 不写入"
                )
            return

        # Get chunk timeline
        tl = self.db.new_chunk_timeline(cp, False, dim)
        if not tl.is_valid():
            fmts.print_war(f"世界备份第二世代: 处理 {dim} {cp} 时出现未知错误")
            return
        tl.set_max_limit(self.base().max_time_point_count)

        # Append time point to the timeline
        sub_chunks, nbts = self.get_sub_chunks_payload_and_nbts(event)
        tl.append_network_chunk(chunkdiff.ChunkData(sub_chunks, [nbts], dim.range()))

        # Save timeline
        tl.save()
