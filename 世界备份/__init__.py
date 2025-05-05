import struct
import threading
import time
import datetime
from io import BytesIO
from tooldelta import FrameExit, InternalBroadcast, Plugin, Frame, plugin_entry
from tooldelta import cfg as config
from tooldelta.mc_bytes_packet.sub_chunk import (
    SUB_CHUNK_RESULT_SUCCESS,
    SUB_CHUNK_RESULT_SUCCESS_ALL_AIR,
)
from tooldelta.utils import fmts


class WorldBackup(Plugin):
    name = "世界备份"
    author = "YoRHa and RATH"
    version = (0, 0, 2)

    def __init__(self, frame: Frame):
        CFG_DEFAULT = {
            "存档名字": "World Backup",
            "世界种子号": 96,
            "显示坐标": True,
            "启用调试": False,
            "要保留多少秒前的存档": 86400,
        }
        cfg, _ = config.get_plugin_config_and_version(
            "世界备份", config.auto_to_std(CFG_DEFAULT), CFG_DEFAULT, (0, 0, 2)
        )

        self.enable_debug = bool(cfg["启用调试"])
        self.world_seed = int(cfg["世界种子号"])
        self.world_dir_name = str(cfg["存档名字"])
        self.show_coordinates = bool(cfg["显示坐标"])
        self.sync_delta_time = int(cfg["要保留多少秒前的存档"])

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.frame = frame
        self.game_ctrl = self.frame.get_game_control()
        self.make_data_path()

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.ListenInternalBroadcast("scq:publish_chunk_data", self.on_chunk_data)

    def on_def(self):
        global bwo, bsdiff4, xxhash
        _ = self.GetPluginAPI("世界の记忆", (0, 0, 4))

        pip = self.GetPluginAPI("pip")
        if 0:
            from pip模块支持 import PipSupport

            pip: PipSupport
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})
        pip.require({"bsdiff4": "bsdiff4"})
        pip.require({"xxhash": "xxhash"})

        import bedrockworldoperator as bwo
        import bsdiff4
        import xxhash

    def on_inject(self):
        self.world = bwo.new_world(self.format_data_path(self.world_dir_name))
        if not self.world.is_valid():
            raise Exception(
                "世界备份: 打开存档失败，请检查存档是否被占用或 level.dat 正确"
            )

        ldt = self.world.get_level_dat()
        if ldt is not None:
            ldt.level_name = self.world_dir_name
            ldt.random_seed = self.world_seed
            ldt.show_coordinates = self.show_coordinates
            self.world.modify_level_dat(ldt)

    def on_close(self, _: FrameExit):
        self.running_mutex.acquire()
        self.should_close = True
        if "world" in self.__dict__ and self.world.is_valid():
            self.world.close_world()
        self.running_mutex.release()

    def encode_delta_update(self, sub_chunks_bytes: list[bytes], nbt: bytes) -> bytes:
        writer = BytesIO()

        writer.write(struct.pack("<I", len(nbt)))
        writer.write(nbt)

        for i in sub_chunks_bytes:
            writer.write(struct.pack("<I", len(i)))
            writer.write(i)

        return writer.getvalue()

    def decode_delta_update(self, delta_update: bytes) -> tuple[list[bytes], bytes]:
        reader = BytesIO(delta_update)

        length = struct.unpack("<I", reader.read(4))[0]
        nbt = reader.read(length)

        sub_chunks_bytes: list[bytes] = []
        while True:
            length_bytes = reader.read(4)
            if len(length_bytes) != 4:
                break
            length = struct.unpack("<I", length_bytes)[0]
            sub_chunks_bytes.append(reader.read(length))

        return sub_chunks_bytes, nbt

    def diff(self, old: bytes, new: bytes) -> bytes:
        buf = BytesIO()

        old_hash = xxhash.xxh64(old, 0).intdigest()
        new_hash = xxhash.xxh64(new, 0).intdigest()

        diff = bsdiff4.diff(old, new)

        buf.write(struct.pack("<QQ", old_hash, new_hash))
        buf.write(diff)

        return buf.getvalue()

    def patch(self, old: bytes, diff: bytes) -> tuple[bytes, bool]:
        if len(diff) < 16:
            return (b"", False)

        hit1, hit2 = struct.unpack("<QQ", diff[:16])
        new = bsdiff4.patch(old, diff[16:])

        old_hash = xxhash.xxh64(old, 0).intdigest()
        new_hash = xxhash.xxh64(new, 0).intdigest()

        if old_hash != hit1 or new_hash != hit2:
            return (b"", False)

        return new, True

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
                payload = bwo.sub_chunk_disk_payload(s, index, r)
                sub_chunks_data.append(payload)
            else:
                sub_chunk_with_index = bwo.from_sub_chunk_network_payload(
                    data["blocks"], r
                )
                sub_chunks_data.append(
                    bwo.sub_chunk_disk_payload(
                        sub_chunk_with_index.sub_chunk, sub_chunk_with_index.index, r
                    )
                )
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
        self.running_mutex.acquire()
        if not self.should_close:
            self._on_chunk_data(event)
        self.running_mutex.release()

    def _on_chunk_data(self, event: InternalBroadcast):
        if not self.check_sub_chunks_all_success(event):
            return

        cp = bwo.ChunkPos(
            event.data[0]["sub_chunk_pos_x"], event.data[0]["sub_chunk_pos_z"]
        )
        dim = bwo.Dimension(event.data[0]["dimension"])

        current_unix_time = int(time.time())
        before_unix_time = self.world.load_delta_time_stamp(cp, dim)

        # This day, DELTA(No change), Day ago(Overwrite to this day)
        if before_unix_time == 0:
            if self.enable_debug:
                fmts.print_inf(f"{dim} {cp} 不存在时间, 直接同步到前一天存档")

            sub_chunks_data, nbts = self.get_sub_chunks_payload_and_nbts(event)
            self.world.save_chunk_payload_only(cp, sub_chunks_data, dim)
            self.world.save_nbt_payload_only(cp, nbts, dim)
            self.world.save_time_stamp(cp, current_unix_time, dim)

            temp = self.encode_delta_update(sub_chunks_data, nbts)
            delta = self.diff(temp, temp)

            self.world.save_delta_update(cp, delta, dim)
            self.world.save_delta_time_stamp(cp, current_unix_time, dim)

            return

        if current_unix_time - before_unix_time < self.sync_delta_time:
            if self.enable_debug:
                fmts.print_inf(
                    f"{dim} {cp} 距离现在时间 {self.get_time_diff_str(before_unix_time, current_unix_time)}, 不写入"
                )
                return
        elif self.enable_debug:
            fmts.print_inf(
                f"{dim} {cp} 距离现在时间 {self.get_time_diff_str(before_unix_time, current_unix_time)}, 移动并写入"
            )

        # This day(A), Delta(B), Day ago(C)
        c = b""

        b_older = self.world.load_delta_update(cp, dim)
        c_raw = self.world.load_chunk_payload_only(cp, dim)

        if len(c_raw) == 0:
            fmts.print_war(f"世界备份: 处理 {dim} {cp} 时出现未知错误")
        else:
            c = self.encode_delta_update(
                c_raw, self.world.load_nbt_payload_only(cp, dim)
            )

        a_older, success = self.patch(c, b_older)
        if not success:
            self.world.save_delta_update(cp, b"", dim)
            self.world.save_delta_time_stamp(cp, 0, dim)
            fmts.print_war("世界备份: Data changed")
            return

        a_older_sub_chunk, a_older_nbt_data = self.decode_delta_update(a_older)
        self.world.save_chunk_payload_only(cp, a_older_sub_chunk, dim)
        self.world.save_nbt_payload_only(cp, a_older_nbt_data, dim)
        self.world.save_time_stamp(cp, current_unix_time, dim)

        a_newer_sub_chunk, a_newer_nbt_data = self.get_sub_chunks_payload_and_nbts(
            event
        )
        b_newer = self.diff(
            a_older, self.encode_delta_update(a_newer_sub_chunk, a_newer_nbt_data)
        )

        self.world.save_delta_update(cp, b_newer, dim)
        self.world.save_delta_time_stamp(cp, current_unix_time, dim)


entry = plugin_entry(WorldBackup, "世界备份")
