"""红包插件配置加载与校验。"""

from __future__ import annotations

from typing import Any

from tooldelta import cfg

from .text_validation import has_invalid_characters


DEFAULT_CONFIG = {
    "经济计分板": "money",
    "货币名称": "星尘",
    "红包有效期秒数": 600,
}
CONFIG_STANDARD = {
    "经济计分板": str,
    "货币名称": str,
    "红包有效期秒数": cfg.PInt,
}


def load_configuration(
    plugin_name: str,
    plugin_version: tuple[int, int, int],
) -> tuple[dict[str, Any], str, str, int]:
    config, _ = cfg.get_plugin_config_and_version(
        plugin_name,
        CONFIG_STANDARD,
        DEFAULT_CONFIG,
        plugin_version,
    )
    scoreboard_name = str(config["经济计分板"]).strip()
    currency_name = str(config["货币名称"]).strip()
    expiry_seconds = int(config["红包有效期秒数"])
    if (
        not scoreboard_name
        or any(character.isspace() for character in scoreboard_name)
        or has_invalid_characters(scoreboard_name)
    ):
        raise ValueError("经济计分板不能为空、包含空格或无效字符")
    if not currency_name or has_invalid_characters(currency_name):
        raise ValueError("货币名称不能为空或包含无效字符")
    if expiry_seconds < 1:
        raise ValueError("红包有效期秒数必须大于 0")
    return config, scoreboard_name, currency_name, expiry_seconds
