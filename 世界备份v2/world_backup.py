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
from tooldelta.utils import fmts, tempjson
from .define import WorldBackupBase
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pip模块支持 import PipSupport


class WorldBackupMain:
    world_backup_base: WorldBackupBase

    def __init__(self, world_backup_base: WorldBackupBase) -> None:
        self.world_backup_base = world_backup_base

    def base(self) -> WorldBackupBase:
        return self.world_backup_base

    def plugin(self) -> Plugin:
        return self.base().plugin

    def need_upgrade_chunkdiff(self) -> bool:
        version_path = self.plugin().format_data_path("depends_version.json")
        loaded_dict = tempjson.load_and_read(
            version_path, need_file_exists=False, default={}
        )
        if "bedrock-chunk-diff" not in loaded_dict:
            return True
        if loaded_dict["bedrock-chunk-diff"] != "0.2.1":
            return True
        return False

    def save_chunkdiff_version(self):
        version_path = self.plugin().format_data_path("depends_version.json")
        tempjson.write(
            version_path,
            {"bedrock-chunk-diff": "0.2.1"},
        )
        tempjson.flush(version_path)

    def on_def(self) -> None:
        global chunkdiff, bwo
        _ = self.plugin().GetPluginAPI("世界の记忆", (0, 1, 1))
        _ = self.plugin().GetPluginAPI("简单世界恢复", (0, 2, 1))

        pip = self.plugin().GetPluginAPI("pip")
        if 0:
            pip: PipSupport
        pip.require({"bedrock-chunk-diff": "bedrockchunkdiff"})
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        if self.need_upgrade_chunkdiff():
            pip.upgrade("bedrock-chunk-diff")
        self.save_chunkdiff_version()

        import bedrockchunkdiff as chunkdiff
        import bedrockworldoperator as bwo

    def on_inject(self) -> None:
        self.db = chunkdiff.new_timeline_database(
            self.plugin().format_data_path(self.base().db_name),
            self.base().no_grow_sync,
            self.base().no_sync,
        )
        if not self.db.is_valid():
            raise Exception(
                "世界备份第二世代: 打开数据库失败，请检查数据库是否被占用或是否已损坏"
            )

    def on_close(self, _: FrameExit) -> None:
        self.do_close()

    def do_close(self) -> None:
        self.base().running_mutex.acquire()
        self.base().should_close = True
        if "db" in self.__dict__ and self.db.is_valid():
            self.db.close_timeline_db()
        self.base().running_mutex.release()

    def check_sub_chunks_all_success(self, event: InternalBroadcast) -> bool:
        for i in event.data:
            code = i["result_code"]
            if code not in (SUB_CHUNK_RESULT_SUCCESS, SUB_CHUNK_RESULT_SUCCESS_ALL_AIR):
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

    def on_chunk_data(self, event: InternalBroadcast) -> None:
        self.base().running_mutex.acquire()
        if not self.base().should_close:
            self._on_chunk_data(event)
        self.base().running_mutex.release()

    def _on_chunk_data(self, event: InternalBroadcast) -> None:
        if "db" not in self.__dict__:
            return

        if not self.check_sub_chunks_all_success(event):
            return

        cp = chunkdiff.ChunkPos(
            event.data[0]["sub_chunk_pos_x"], event.data[0]["sub_chunk_pos_z"]
        )
        dim = chunkdiff.Dimension(event.data[0]["dimension"])

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
        tl = self.db.new_chunk_timeline(cp, read_only=False, dm=dim)
        if not tl.is_valid():
            fmts.print_war(f"世界备份第二世代: 处理 {dim} {cp} 时出现未知错误")
            return
        tl.set_max_limit(self.base().max_time_point_count)

        # Append time point to the timeline
        sub_chunks, nbts = self.get_sub_chunks_payload_and_nbts(event)
        tl.append_network_chunk(
            chunkdiff.ChunkData(sub_chunks, [nbts], dim.range()),
            self.base().no_change_when_no_change,
        )

        # Save timeline
        tl.save()
