"""Runtime config hot-reload helpers."""

from __future__ import annotations

import os
from typing import Any

from tooldelta import fmts

from guild_cloud_interop.config import CONFIG_FILE_DIR, Config
from guild_cloud_interop.matchers import ItemNameMatcher


def get_config_path(plugin_name: str) -> str:
    return os.path.join(CONFIG_FILE_DIR, f"{plugin_name}.json")


def get_file_state(path: str) -> tuple[int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def refresh_config_file_state(plugin: Any) -> None:
    config_path = get_config_path(plugin.name)
    plugin._config_file_state = get_file_state(config_path)


def apply_runtime_config(plugin: Any, *, announce: bool = False) -> None:
    plugin.config = Config.load(plugin.name, plugin.version)

    guild_manager = getattr(plugin, "guild_manager", None)
    if guild_manager is not None:
        guild_manager.cache_duration = Config.CACHE_DURATION

    plugin.item_matcher = ItemNameMatcher()
    plugin._effect_refresh_cache = {}

    sync_runtime_config_bindings = getattr(plugin, "sync_runtime_config_bindings", None)
    if callable(sync_runtime_config_bindings):
        sync_runtime_config_bindings()

    if announce:
        fmts.print_suc(f"{plugin.name} 配置文件已热更新")


def config_reload_task(plugin: Any) -> None:
    config_path = get_config_path(plugin.name)
    plugin._config_file_state = get_file_state(config_path)

    while not plugin._should_stop():
        interval = Config.dynamic_load_interval()
        if plugin._wait_or_stopped(interval):
            break

        if not Config.is_dynamic_load_enabled():
            plugin._config_file_state = get_file_state(config_path)
            continue

        current_state = get_file_state(config_path)
        if current_state == plugin._config_file_state:
            continue

        try:
            apply_runtime_config(plugin, announce=True)
            plugin._config_file_state = get_file_state(config_path)
        except Exception as err:
            plugin._config_file_state = current_state
            fmts.print_err(f"{plugin.name} 配置文件热更新失败: {err}")
