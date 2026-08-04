"""写入命令方块"""

from typing import TYPE_CHECKING, Any

from ..common import command_loader as _common_command_loader

if TYPE_CHECKING:
    from ...__init__ import LyraSystem
    from ..common.dimensions import Dimension


class CommandLoader:
    def __init__(self, plugin: "LyraSystem") -> None:
        self.plugin = plugin

    def load_commands(
        self, command_data: list[dict[str, Any]], dimension: "Dimension"
    ) -> None:
        _common_command_loader.load_command_blocks(self.plugin, command_data, dimension)
