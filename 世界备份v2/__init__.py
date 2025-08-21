from tooldelta import (
    Plugin,
    Frame,
    plugin_entry,
)
from .world_backup import WorldBackupMain
from .define import WorldBackupBase
from .on_chat import WorldBackupOnChat
from .recover import WorldBackupRecover


class WorldBackupNextGen(Plugin):
    name = "世界备份第二世代"
    author = "YoRHa and RATH"
    version = (1, 4, 3)

    def __init__(self, frame: Frame) -> None:
        super().__init__(frame)

        self.world_backup_base = WorldBackupBase(self)
        self.world_backup_main = WorldBackupMain(self.world_backup_base)
        self.world_backup_recover = WorldBackupRecover(self.world_backup_base)
        self.world_backup_on_chat = WorldBackupOnChat(
            self.world_backup_main, self.world_backup_recover
        )

        self.ListenPreload(self.on_def)
        self.ListenActive(self.world_backup_main.on_inject)
        self.ListenFrameExit(self.world_backup_main.on_close)
        self.ListenInternalBroadcast(
            "scq:publish_chunk_data", self.world_backup_main.on_chunk_data
        )
        self.ListenChat(self.world_backup_on_chat.on_chat)

    def on_def(self) -> None:
        self.world_backup_recover.recover()
        self.world_backup_main.on_def()


entry = plugin_entry(WorldBackupNextGen, "世界备份第二世代")
