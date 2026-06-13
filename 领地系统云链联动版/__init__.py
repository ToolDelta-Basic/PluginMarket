"""Land protection cloud interop ToolDelta plugin."""

import copy
import json
import time
import threading
import os
import re
import random
import math
import shutil
import uuid
from typing import Dict, List, Optional, Tuple, Any
from tooldelta import Plugin, cfg, fmts, Player, Chat, plugin_entry, utils, game_utils

from .config import (
    CONFIG_FILE_DIR,
    DYNAMIC_LOAD_DEFAULT_INTERVAL,
    DYNAMIC_LOAD_ENABLED_KEY,
    DYNAMIC_LOAD_INTERVAL_KEY,
    DYNAMIC_LOAD_SETTINGS_KEY,
    NO_CREATE_REGIONS_FILE,
    default_config,
    default_no_create_regions,
)
from .geometry import (
    box_radius_for_size,
    bounds_from_center_size,
    boxes_intersect,
    distance_to_land,
    land_overlaps_candidate,
    sphere_intersects_box,
)
from .models import LandData, LandMember, LandRank


PLUGIN_NAME = "领地系统云链联动版"
LEGACY_PLUGIN_NAME = "领地系统"


class ConsoleMenuExit(Exception):
    """Signal that the console menu should exit."""


class LandPlugin(Plugin):
    """ToolDelta plugin entrypoint for land protection cloud interop."""

    name = PLUGIN_NAME
    author = "小石潭记qwq/小六神"
    version = (0, 1, 18)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self._stop_event = threading.Event()
        self._config_file_state = None
        self._no_create_regions_file_state = None
        self._cfg_default = default_config()
        self._cfg_std = cfg.auto_to_std(self._cfg_default)
        self.make_data_path()
        self._migrate_legacy_data_path()
        self.no_create_regions_file = self.format_data_path(
            NO_CREATE_REGIONS_FILE)
        self.cfg = self._load_config(self._cfg_default, self._cfg_std)
        self.data_file = self.format_data_path(str(self.cfg["数据文件"]))
        self._apply_runtime_config_fields(reload_data_file=False)
        self.no_create_regions_raw = self._load_no_create_regions()
        self.no_create_regions = self._normalize_no_create_regions(
            self.no_create_regions_raw)

        # 数据
        self.lands: Dict[str, LandData] = {}      # land_id -> LandData
        # xuid -> list of land_id
        self.player_land_cache: Dict[str, List[str]] = {}
        self.xuid_getter = None

        self.coords: Dict[str, Tuple[float, float, float]] = {}
        self.coords_lock = threading.Lock()
        self.recent_tp: Dict[str, float] = {}      # xuid -> last tp time
        self.tp_cooldown = 5
        self._detection_started = False

        self._ensure_dirs()
        self._load_data()

        # 事件监听
        self.ListenChat(self.on_chat)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)
        self.refresh_config_file_state()
        self.config_thread = utils.createThread(
            self.config_reload_task,
            usage="领地系统配置热更新任务",
        )

        # 控制台测试指令
        self.frame.add_console_cmd_trigger(
            ["领地云链测试", "领地测试"], "[玩家]", "测试领地系统云链联动版", self.console_test)
        self.frame.add_console_cmd_trigger(
            ["领地系统云链联动版", "领地系统"], None, "打开领地系统云链联动版控制台管理菜单", self.console_manage)

    def on_preload(self):
        """Implement the on preload operation."""
        self.xuid_getter = self.GetPluginAPI("XUID获取", (0, 0, 7))

    def on_active(self):
        """Implement the on active operation."""
        if self.enabled:
            self._start_detection()

    def on_frame_exit(self, _):
        """Implement the on frame exit operation."""
        self._stop_event.set()

    @staticmethod
    def _ui_border() -> str:
        """Implement the ui border operation."""
        return "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"

    @staticmethod
    def _ui_title(title: str) -> str:
        """Implement the ui title operation."""
        return f"§l§d❐§f 『§6领地系统云链联动版§f』 §b{title}"

    def _ui_menu(self,
                 title: str,
                 options: List[str],
                 hints: Optional[List[str]] = None) -> str:
        """Implement the ui menu operation."""
        lines = [self._ui_border(), self._ui_title(title)]
        lines.extend(f"§l§b[ §e{i}§b ] §r§e{option}" for i,
                     option in enumerate(options, 1))
        lines.append(self._ui_border())
        for hint in hints or []:
            lines.append(f"§a❀ §b{hint}")
        return "\n".join(lines)

    def _ui_card(self,
                 title: str,
                 lines: List[str],
                 hints: Optional[List[str]] = None) -> str:
        """Implement the ui card operation."""
        body = [self._ui_border(), self._ui_title(title)]
        body.extend(f"§a❀ §b{line}" for line in lines)
        body.append(self._ui_border())
        for hint in hints or []:
            body.append(f"§a❀ §b{hint}")
        return "\n".join(body)

    @staticmethod
    def _success(text: str) -> str:
        """Implement the success operation."""
        return f"§a❀ §b{text}"

    @staticmethod
    def _error(text: str) -> str:
        """Implement the error operation."""
        return f"§c❀ §e{text}"

    @staticmethod
    def _warn(text: str) -> str:
        """Implement the warn operation."""
        return f"§6❀ §e{text}"

    @staticmethod
    def _notice(text: str) -> str:
        """Implement the notice operation."""
        return f"§a❀ §b{text}"

    @staticmethod
    def _normalize_wake_words(raw: Any) -> List[str]:
        """Normalize wake words values."""
        if isinstance(raw, str):
            words = [raw]
        elif isinstance(raw, list):
            words = [str(item) for item in raw if isinstance(item, str)]
        else:
            words = []
        cleaned = []
        for word in words:
            word = word.strip()
            if word and word not in cleaned:
                cleaned.append(word)
        return cleaned or [".领地"]

    @classmethod
    def _merge_config_with_default(cls, raw: Any, default: Any):
        """Implement the merge config with default operation."""
        if isinstance(default, dict):
            result = {
                key: cls._merge_config_with_default(
                    raw.get(key) if isinstance(raw, dict) else None,
                    value,
                )
                for key, value in default.items()
            }
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key not in result:
                        result[key] = copy.deepcopy(value)
            return result
        return copy.deepcopy(
            raw) if raw is not None else copy.deepcopy(default)

    @staticmethod
    def _trim_fixed_keys(raw: Any, default: Dict[str, Any]) -> Dict[str, Any]:
        """Implement the trim fixed keys operation."""
        raw = raw if isinstance(raw, dict) else {}
        return {
            key: copy.deepcopy(raw.get(key, value))
            for key, value in default.items()
        }

    @staticmethod
    def _normalize_config_bool(value: Any, fallback: bool) -> bool:
        """Normalize config bool values."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("true", "1", "yes", "y", "on", "启用", "是", "真"):
                return True
            if text in ("false", "0", "no", "n", "off", "禁用", "否", "假"):
                return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return bool(value)
        return bool(fallback)

    @staticmethod
    def _normalize_config_positive_int(value: Any, fallback: int) -> int:
        """Normalize config positive int values."""
        if isinstance(value, bool):
            return fallback
        try:
            result = int(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    @staticmethod
    def _normalize_config_non_negative_int(value: Any, fallback: int) -> int:
        """Normalize config non negative int values."""
        if isinstance(value, bool):
            return fallback
        try:
            result = int(value)
        except (TypeError, ValueError):
            return fallback
        return result if result >= 0 else fallback

    @staticmethod
    def _normalize_config_str(
            value: Any,
            fallback: str,
            *,
            allow_empty: bool = False) -> str:
        """Normalize config str values."""
        if value is None:
            return fallback
        text = str(value)
        if text or allow_empty:
            return text
        return fallback

    @classmethod
    def _normalize_config_string_list(
        cls,
        value: Any,
        fallback: List[str],
        *,
        allow_empty: bool = False,
    ) -> List[str]:
        """Normalize config string list values."""
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            return copy.deepcopy(fallback)

        result: List[str] = []
        for item in candidates:
            text = cls._normalize_config_str(
                item, "", allow_empty=True).strip()
            if text and text not in result:
                result.append(text)
        if result or allow_empty:
            return result
        return copy.deepcopy(fallback)

    @classmethod
    def _normalize_runtime_config(
            cls, raw_cfg: Any, default_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize runtime config values."""
        merged_cfg = cls._merge_config_with_default(raw_cfg, default_cfg)
        normalized = cls._trim_fixed_keys(merged_cfg, default_cfg)

        dynamic_default = default_cfg[DYNAMIC_LOAD_SETTINGS_KEY]
        dynamic = cls._trim_fixed_keys(
            normalized.get(DYNAMIC_LOAD_SETTINGS_KEY),
            dynamic_default,
        )
        dynamic[DYNAMIC_LOAD_ENABLED_KEY] = cls._normalize_config_bool(
            dynamic.get(DYNAMIC_LOAD_ENABLED_KEY),
            dynamic_default[DYNAMIC_LOAD_ENABLED_KEY],
        )
        dynamic[DYNAMIC_LOAD_INTERVAL_KEY] = cls._normalize_config_positive_int(
            dynamic.get(DYNAMIC_LOAD_INTERVAL_KEY),
            dynamic_default[DYNAMIC_LOAD_INTERVAL_KEY],
        )
        normalized[DYNAMIC_LOAD_SETTINGS_KEY] = dynamic

        normalized["是否启用"] = cls._normalize_config_bool(
            normalized.get("是否启用"),
            default_cfg["是否启用"],
        )
        normalized["唤醒词"] = cls._normalize_config_string_list(
            normalized.get("唤醒词"),
            default_cfg["唤醒词"],
        )
        normalized["数据文件"] = cls._normalize_config_str(
            normalized.get("数据文件"),
            default_cfg["数据文件"],
        )
        for key in (
            "检测间隔",
            "传送半径",
            "最大领地半径",
            "最大领地长",
            "最大领地高",
            "最大领地宽",
            "最大领地数量",
        ):
            normalized[key] = cls._normalize_config_positive_int(
                normalized.get(key),
                default_cfg[key],
            )
        normalized["缓冲区距离"] = cls._normalize_config_non_negative_int(
            normalized.get("缓冲区距离"),
            default_cfg["缓冲区距离"],
        )
        normalized["白名单"] = cls._normalize_config_string_list(
            normalized.get("白名单"),
            default_cfg["白名单"],
            allow_empty=True,
        )
        return normalized

    def _load_config(
            self, default_cfg: Dict[str, Any], cfg_std: Any) -> Dict[str, Any]:
        """Load config data."""
        try:
            raw_cfg, _ = cfg.get_plugin_config_and_version(
                self.name,
                {},
                default_cfg,
                self.version,
            )
            merged_cfg = self._normalize_runtime_config(raw_cfg, default_cfg)
            cfg.check_auto(cfg_std, merged_cfg)
        except Exception as err:
            fmts.print_err(f"领地系统云链联动版配置文件自动更新失败，已使用默认配置: {err}")
            merged_cfg = self._normalize_runtime_config({}, default_cfg)
            cfg.check_auto(cfg_std, merged_cfg)
        cfg.upgrade_plugin_config(self.name, merged_cfg, self.version)
        return merged_cfg

    def _apply_runtime_config_fields(self, reload_data_file: bool = False):
        """Implement the apply runtime config fields operation."""
        self.enabled = bool(self.cfg["是否启用"])
        self.wake_words = self._normalize_wake_words(self.cfg["唤醒词"])
        new_data_file = self.format_data_path(str(self.cfg["数据文件"]))
        data_file_changed = getattr(self, "data_file", None) != new_data_file
        self.data_file = new_data_file
        self.check_interval = self._positive_float(self.cfg["检测间隔"], 2.0)
        self.buffer_dist = self._non_negative_float(self.cfg["缓冲区距离"], 5.0)
        self.tp_radius = self._positive_float(self.cfg["传送半径"], 5000.0)
        self.max_radius = self._positive_int(self.cfg["最大领地半径"], 200)
        self.max_length = self._positive_int(self.cfg["最大领地长"], 200)
        self.max_height = self._positive_int(self.cfg["最大领地高"], 200)
        self.max_width = self._positive_int(self.cfg["最大领地宽"], 200)
        self.max_lands_per_player = self._positive_int(self.cfg["最大领地数量"], 4)
        self.whitelist = {str(name).lower() for name in self.cfg["白名单"]}
        if reload_data_file and data_file_changed:
            self.lands.clear()
            self.player_land_cache.clear()
            self._ensure_dirs()
            self._load_data()

    @staticmethod
    def _positive_int(value: Any, fallback: int) -> int:
        """Implement the positive int operation."""
        try:
            result = int(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    @staticmethod
    def _positive_float(value: Any, fallback: float) -> float:
        """Implement the positive float operation."""
        try:
            result = float(value)
        except (TypeError, ValueError):
            return fallback
        return result if result > 0 else fallback

    @staticmethod
    def _non_negative_float(value: Any, fallback: float) -> float:
        """Implement the non negative float operation."""
        try:
            result = float(value)
        except (TypeError, ValueError):
            return fallback
        return result if result >= 0 else fallback

    def config_file_path(self) -> str:
        """Implement the config file path operation."""
        return os.path.join(CONFIG_FILE_DIR, f"{self.name}.json")

    @staticmethod
    def file_state(path: str) -> tuple[int, int] | None:
        """Implement the file state operation."""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def refresh_config_file_state(self):
        """Implement the refresh config file state operation."""
        self._config_file_state = self.file_state(self.config_file_path())
        self._no_create_regions_file_state = self.file_state(
            self.no_create_regions_file)

    def is_dynamic_config_reload_enabled(self) -> bool:
        """Implement the is dynamic config reload enabled operation."""
        settings = self.cfg.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return True
        return bool(settings.get(DYNAMIC_LOAD_ENABLED_KEY, True))

    def dynamic_config_reload_interval(self) -> int:
        """Implement the dynamic config reload interval operation."""
        settings = self.cfg.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return DYNAMIC_LOAD_DEFAULT_INTERVAL
        try:
            interval = int(settings.get(DYNAMIC_LOAD_INTERVAL_KEY,
                           DYNAMIC_LOAD_DEFAULT_INTERVAL))
        except (TypeError, ValueError):
            return DYNAMIC_LOAD_DEFAULT_INTERVAL
        return interval if interval > 0 else DYNAMIC_LOAD_DEFAULT_INTERVAL

    def apply_runtime_config(self, config_items: Dict[str, Any]) -> None:
        """Apply already parsed config-center data to this plugin."""
        self.cfg = self._normalize_runtime_config(
            config_items, self._cfg_default)
        cfg.check_auto(self._cfg_std, self.cfg)
        self._apply_runtime_config_fields(reload_data_file=True)
        if self.enabled:
            self._start_detection()
        self.refresh_config_file_state()

    def reload_runtime_config(self, announce: bool = False):
        """Implement the reload runtime config operation."""
        self.cfg = self._load_config(self._cfg_default, self._cfg_std)
        self._apply_runtime_config_fields(reload_data_file=True)
        if self.enabled:
            self._start_detection()
        if announce:
            fmts.print_suc(f"{self.name} 配置文件已热更新")

    def reload_no_create_regions_config(self, announce: bool = False):
        """Implement the reload no create regions config operation."""
        self.no_create_regions_raw = self._load_no_create_regions()
        self._reload_no_create_regions()
        if announce:
            fmts.print_suc(f"{self.name} 不可创建领地区域配置已热更新")

    def config_reload_task(self):
        """Implement the config reload task operation."""
        while not self._stop_event.wait(self.dynamic_config_reload_interval()):
            if not self.is_dynamic_config_reload_enabled():
                self.refresh_config_file_state()
                continue
            current_config_state = self.file_state(self.config_file_path())
            current_regions_state = self.file_state(
                self.no_create_regions_file)
            if (
                current_config_state == self._config_file_state
                and current_regions_state == self._no_create_regions_file_state
            ):
                continue
            try:
                if current_config_state != self._config_file_state:
                    self.reload_runtime_config(announce=True)
                if current_regions_state != self._no_create_regions_file_state:
                    self.reload_no_create_regions_config(announce=True)
                self.refresh_config_file_state()
            except Exception as err:
                self._config_file_state = current_config_state
                self._no_create_regions_file_state = current_regions_state
                fmts.print_err(f"{self.name} 配置文件热更新失败: {err}")

    def api_reload_land_config(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Expose the api reload land config API operation."""
        try:
            self.reload_runtime_config(announce=False)
            self.reload_no_create_regions_config(announce=False)
            self.refresh_config_file_state()
        except Exception as err:
            return False, f"领地系统配置重载失败: {err}", self.api_get_runtime_status()
        return True, "领地系统配置已重载", self.api_get_runtime_status()

    def api_get_runtime_status(self) -> Dict[str, Any]:
        """Expose the api get runtime status API operation."""
        return {
            "enabled": self.enabled,
            "wake_words": list(self.wake_words),
            "data_file": self.data_file,
            "check_interval": self.check_interval,
            "land_count": len(self.lands),
            "no_create_region_count": len(self.no_create_regions),
            "dynamic_reload_enabled": self.is_dynamic_config_reload_enabled(),
            "dynamic_reload_interval": self.dynamic_config_reload_interval(),
        }

    def _load_no_create_regions(self) -> List[Dict[str, Any]]:
        """Load no create regions data."""
        if not os.path.exists(self.no_create_regions_file):
            regions = default_no_create_regions()
            self._save_no_create_regions(regions)
            return regions
        try:
            with open(self.no_create_regions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as err:
            fmts.print_err(f"读取不可创建领地区域数据失败: {err}")
        regions = default_no_create_regions()
        self._save_no_create_regions(regions)
        return regions

    def _save_no_create_regions(
            self, regions: Optional[List[Dict[str, Any]]] = None):
        """Save no create regions data."""
        data = self.no_create_regions_raw if regions is None else regions
        os.makedirs(
            os.path.dirname(
                self.no_create_regions_file),
            exist_ok=True)
        with open(self.no_create_regions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _reload_no_create_regions(self):
        """Implement the reload no create regions operation."""
        self.no_create_regions = self._normalize_no_create_regions(
            self.no_create_regions_raw)

    @staticmethod
    def _as_float_pos(raw: Any) -> Optional[Tuple[float, float, float]]:
        """Implement the as float pos operation."""
        if not isinstance(raw, list) or len(raw) != 3:
            return None
        try:
            return (float(raw[0]), float(raw[1]), float(raw[2]))
        except (TypeError, ValueError):
            return None

    def _normalize_no_create_regions(self, raw: Any) -> List[Dict[str, Any]]:
        """Normalize no create regions values."""
        regions: List[Dict[str, Any]] = []
        if not isinstance(raw, list):
            return regions
        for index, item in enumerate(raw, 1):
            if not isinstance(item, dict) or not item.get("启用", True):
                continue
            region_type = str(item.get("类型", "")).strip().lower()
            name = str(item.get("名称", f"区域{index}")).strip() or f"区域{index}"
            if region_type in ("圆形", "circle", "round"):
                center = self._as_float_pos(item.get("中心"))
                try:
                    radius = float(item.get("半径", 0))
                except (TypeError, ValueError):
                    radius = 0
                if center is None or radius <= 0:
                    fmts.print_war(f"领地系统云链联动版: 不可创建领地区域 {name} 配置无效，已忽略")
                    continue
                regions.append({
                    "名称": name,
                    "类型": "圆形",
                    "中心": center,
                    "半径": radius,
                })
            elif region_type in ("方形", "矩形", "长方形", "square", "box", "立方体", "长方体"):
                start = self._as_float_pos(item.get("起点"))
                end = self._as_float_pos(item.get("终点"))
                if start is None or end is None:
                    fmts.print_war(f"领地系统云链联动版: 不可创建领地区域 {name} 配置无效，已忽略")
                    continue
                min_pos = tuple(min(start[i], end[i]) for i in range(3))
                max_pos = tuple(max(start[i], end[i]) for i in range(3))
                regions.append({
                    "名称": name,
                    "类型": "方形",
                    "起点": min_pos,
                    "终点": max_pos,
                })
            else:
                fmts.print_war(f"领地系统云链联动版: 不可创建领地区域 {name} 类型未知，已忽略")
        return regions

    def _get_no_create_overlap_reason(
        self,
        center: Tuple[float, float, float],
        radius: int,
        shape: str = "圆形",
        size: Optional[Tuple[int, int, int]] = None,
    ) -> Optional[str]:
        """Return no create overlap reason data."""
        shape = LandData.normalize_shape(shape)
        box_bounds = None
        if shape == "方形":
            box_bounds = bounds_from_center_size(
                center, LandData.normalize_size(size, radius))
        x, y, z = center
        for region in self.no_create_regions:
            if shape == "方形" and box_bounds is not None:
                if region["类型"] == "圆形":
                    if sphere_intersects_box(
                            region["中心"],
                            region["半径"],
                            box_bounds[0],
                            box_bounds[1]):
                        return region["名称"]
                elif region["类型"] == "方形":
                    if boxes_intersect(
                            box_bounds[0],
                            box_bounds[1],
                            region["起点"],
                            region["终点"]):
                        return region["名称"]
            elif region["类型"] == "圆形":
                rx, ry, rz = region["中心"]
                if math.sqrt((x - rx) ** 2 + (y - ry) ** 2 +
                             (z - rz) ** 2) <= radius + region["半径"]:
                    return region["名称"]
            elif region["类型"] == "方形":
                if sphere_intersects_box(
                        center, radius, region["起点"], region["终点"]):
                    return region["名称"]
        return None

    @staticmethod
    def _is_exit_input(text: str) -> bool:
        """Implement the is exit input operation."""
        return text.strip().lower() in (".", "。", "q", "quit", "退出")

    def _wait_menu_input(
            self,
            player: Player,
            timeout: int = 60) -> Optional[str]:
        """Implement the wait menu input operation."""
        msg = game_utils.waitMsg(player.name, timeout)
        if msg is None:
            player.show(self._error("回复超时，已退出菜单"))
            return None
        msg = msg.strip()
        if self._is_exit_input(msg):
            player.show(self._success("已退出领地菜单"))
            return None
        return msg

    def _select_menu(
            self,
            player: Player,
            title: str,
            options: List[str],
            timeout: int = 60) -> Optional[int]:
        """Implement the select menu operation."""
        while True:
            hints = [
                f"输入 §e[1-{len(options)}]§b 之间的数字以选择功能",
                "输入 §c.§b 退出",
            ]
            player.show(self._ui_menu(
                title,
                options,
            ))
            player.show("\n".join(f"§a❀ §b{hint}" for hint in hints))
            msg = self._wait_menu_input(player, timeout)
            if msg is None:
                return None
            choice = utils.try_int(msg.strip().strip("[]"))
            if choice is None or choice not in range(1, len(options) + 1):
                player.show(self._error("您的输入有误"))
                continue
            return choice

    def _prompt_text(
            self,
            player: Player,
            title: str,
            prompt: str,
            timeout: int = 60) -> Optional[str]:
        """Implement the prompt text operation."""
        player.show(self._ui_card(title, [prompt], ["输入 §c.§b 退出"]))
        return self._wait_menu_input(player, timeout)

    def _parse_box_size_input(
            self, raw: str) -> Tuple[Optional[Tuple[int, int, int]], Optional[str]]:
        """Implement the parse box size input operation."""
        parts = raw.replace(",", " ").replace("，", " ").split()
        if len(parts) != 3:
            return None, "格式错误，需要输入 长 高 宽 三个整数"
        try:
            length, height, width = (
                int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None, "长、高、宽必须为整数"
        if length <= 0 or height <= 0 or width <= 0:
            return None, "长、高、宽必须大于 0"
        if length > self.max_length:
            return None, f"长不能超过 {self.max_length}"
        if height > self.max_height:
            return None, f"高不能超过 {self.max_height}"
        if width > self.max_width:
            return None, f"宽不能超过 {self.max_width}"
        return (length, height, width), None

    def _get_xuid_by_name(
            self,
            playername: str,
            allow_offline: bool = False) -> Optional[str]:
        """Return xuid by name data."""
        try:
            return str(
                self.xuid_getter.get_xuid_by_name(
                    playername,
                    allow_offline=allow_offline))
        except Exception as err:
            self.print_war(f"无法获取玩家 {playername} 的 XUID: {err}")
            return None

    def _get_player_xuid(self, player: Player) -> Optional[str]:
        """Return player xuid data."""
        xuid = getattr(player, "xuid", None)
        if xuid:
            return str(xuid)
        return self._get_xuid_by_name(player.name)

    def _make_member(self, playername: str, rank: LandRank,
                     allow_offline: bool = False) -> Optional[LandMember]:
        """Implement the make member operation."""
        xuid = self._get_xuid_by_name(playername, allow_offline=allow_offline)
        if xuid is None:
            return None
        return LandMember(name=playername, xuid=xuid, rank=rank)

    def _select_land(
            self,
            player: Player,
            title: str,
            lands: List[LandData]) -> Optional[LandData]:
        """Implement the select land operation."""
        if not lands:
            player.show(self._error("没有可选择的领地"))
            return None
        choice = self._select_menu(
            player,
            title,
            [
                f"{land.name} §7- 领主: {land.owner}, {land.range_text()}"
                for land in lands
            ],
        )
        if choice is None:
            return None
        return lands[choice - 1]

    def _land_summary(self, land: LandData) -> Dict[str, Any]:
        """Implement the land summary operation."""
        _ = self
        admins = [m.name for m in land.members if m.rank == LandRank.ADMIN]
        members = [m.name for m in land.members if m.rank == LandRank.MEMBER]
        return {
            "land_id": land.land_id,
            "name": land.name,
            "owner": land.owner,
            "owner_xuid": land.owner_xuid,
            "center": land.center,
            "radius": land.radius,
            "shape": land.shape,
            "size": land.get_size() if land.is_box() else None,
            "dimension": land.dimension,
            "range_text": land.range_text(),
            "admins": admins,
            "members": members,
            "member_count": len(land.members),
        }

    def _find_land_by_name_or_id(self, query: str) -> Optional[LandData]:
        """Implement the find land by name or id operation."""
        query = str(query).strip()
        if not query:
            return None
        if query in self.lands:
            return self.lands[query]
        return next((land for land in self.lands.values()
                    if land.name == query), None)

    def _migrate_legacy_data_path(self):
        """Implement the migrate legacy data path operation."""
        legacy_path = os.path.join(
            os.path.dirname(
                self.data_path),
            LEGACY_PLUGIN_NAME)
        if not os.path.isdir(legacy_path) or os.path.abspath(
                legacy_path) == os.path.abspath(self.data_path):
            return
        os.makedirs(self.data_path, exist_ok=True)
        for filename in ("领地数据.json", "不可创建领地区域.json"):
            old_file = os.path.join(legacy_path, filename)
            new_file = self.format_data_path(filename)
            if os.path.isfile(old_file) and not os.path.exists(new_file):
                try:
                    shutil.copy2(old_file, new_file)
                except Exception as err:
                    self.print_war(f"迁移旧版领地系统数据文件 {filename} 失败: {err}")

    def _ensure_dirs(self):
        """Implement the ensure dirs operation."""
        os.makedirs(os.path.dirname(self.data_file) or ".", exist_ok=True)

    # ---------- 玩家-领地 缓存维护 ----------
    def _add_player_land(self, xuid: str, land_id: str):
        """Implement the add player land operation."""
        if xuid not in self.player_land_cache:
            self.player_land_cache[xuid] = []
        if land_id not in self.player_land_cache[xuid]:
            self.player_land_cache[xuid].append(land_id)

    def _remove_player_land(self, xuid: str, land_id: str):
        """Implement the remove player land operation."""
        if xuid in self.player_land_cache:
            lst = self.player_land_cache[xuid]
            if land_id in lst:
                lst.remove(land_id)
            if not lst:
                del self.player_land_cache[xuid]

    def _rebuild_player_land_cache(self):
        """Implement the rebuild player land cache operation."""
        self.player_land_cache.clear()
        for land_id, land in self.lands.items():
            for member in land.members:
                self._add_player_land(member.xuid, land_id)

    # ---------- 数据加载/保存 ----------
    def _load_data(self):
        """Load data data."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.player_land_cache.clear()
                for land_id, data in raw.items():
                    try:
                        land = LandData.from_dict(data)
                        self.lands[land_id] = land
                        for m in land.members:
                            self._add_player_land(m.xuid, land_id)
                    except Exception as e:
                        fmts.print_err(f"解析领地 {land_id} 失败: {e}")
        except Exception as e:
            fmts.print_err(f"加载数据失败: {e}")

    def _save_data(self):
        """Save data data."""
        try:
            raw = {lid: land.to_dict() for lid, land in self.lands.items()}
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
        except Exception as e:
            fmts.print_err(f"保存数据失败: {e}")

    # ---------- 坐标获取 ----------
    def _get_player_coord(
            self, player: str) -> Optional[Tuple[float, float, float]]:
        """Return player coord data."""
        try:
            pos_dict = game_utils.getPos(player)
            if pos_dict and "position" in pos_dict:
                p = pos_dict["position"]
                return (p.get("x", 0), p.get("y", 0), p.get("z", 0))
        except Exception:
            pass
        cmd = f"/data get entity {player} Pos"
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(cmd, timeout=2)
            if resp.SuccessCount:
                for out in resp.OutputMessages:
                    msg = out.Message
                    nums = re.findall(r"[-+]?\d*\.?\d+[df]?", msg)
                    if len(nums) >= 3:
                        x = float(nums[0].replace('d', '').replace('f', ''))
                        y = float(nums[1].replace('d', '').replace('f', ''))
                        z = float(nums[2].replace('d', '').replace('f', ''))
                        return (x, y, z)
        except Exception:
            pass
        return None

    def _manual_coord(
            self, player: Player) -> Optional[Tuple[float, float, float]]:
        """Implement the manual coord operation."""
        player.show(self._ui_card(
            "手动坐标输入",
            [
                "请输入你的当前坐标",
                "格式：x y z，例如 100 64 200",
                "请在聊天栏直接输入数字，用空格分隔",
            ],
            ["30 秒内回复有效"],
        ))
        msg = game_utils.waitMsg(player.name, 30)
        if not msg:
            player.show(self._error("输入超时"))
            return None
        parts = msg.strip().split()
        if len(parts) != 3:
            player.show(self._error("格式错误，需要三个数字"))
            return None
        try:
            x = float(parts[0])
            y = float(parts[1])
            z = float(parts[2])
            return (x, y, z)
        except ValueError:
            player.show(self._error("请输入有效的数字"))
            return None

    # ---------- 领地查找辅助 ----------
    def _find_land_at(self,
                      pos: Tuple[float,
                                 float,
                                 float],
                      dimension: int = 0) -> Optional[LandData]:
        """Implement the find land at operation."""
        x, y, z = pos
        for land in self.lands.values():
            if land.dimension != dimension:
                continue
            if land.contains_pos((x, y, z)):
                return land
        return None

    def _find_land_at_player(self, player: str) -> Optional[LandData]:
        """Implement the find land at player operation."""
        pos = self._get_player_coord(player)
        if pos:
            return self._find_land_at(pos)
        return None

    # ---------- 检测线程 ----------
    def _start_detection(self):
        """Implement the start detection operation."""
        if self._detection_started:
            return
        self._detection_started = True

        def loop():
            """Implement the loop operation."""
            while not self._stop_event.wait(self.check_interval):
                try:
                    self._update_coords()
                    self._check_lands()
                except Exception as e:
                    fmts.print_err(f"检测异常: {e}")
        threading.Thread(target=loop, daemon=True).start()

    def _update_coords(self):
        """Implement the update coords operation."""
        if not self.enabled:
            return
        players = self.game_ctrl.allplayers
        new_coords = {}
        for name in players:
            pos = self._get_player_coord(name)
            if pos:
                new_coords[name] = pos
        with self.coords_lock:
            self.coords = new_coords

    def _check_lands(self):
        """Implement the check lands operation."""
        if not self.enabled:
            return
        with self.coords_lock:
            players = dict(self.coords)

        now = time.time()
        expired = [
            p for p,
            t in self.recent_tp.items() if now -
            t > self.tp_cooldown]
        for p in expired:
            del self.recent_tp[p]

        for name, (x, y, z) in players.items():
            if name.lower() in self.whitelist:
                continue
            xuid = self._get_xuid_by_name(name)
            if xuid is None:
                continue

            in_land = self._find_land_at((x, y, z))

            if in_land:
                if in_land.get_member(xuid):
                    continue
                if xuid in self.recent_tp:
                    continue
                self._tp_random(name, x, y, z)
                self.recent_tp[xuid] = now
                self.game_ctrl.say_to(name, self._error(
                    f"你闯入了 {in_land.owner} 的领地，已被传送离开"))
            else:
                for land in self.lands.values():
                    if land.dimension != 0:
                        continue
                    dist = distance_to_land((x, y, z), land)
                    if 0 <= dist <= self.buffer_dist:
                        if land.get_member(xuid):
                            continue
                        self.game_ctrl.sendwocmd(f"/gamemode adventure {name}")
                        self.game_ctrl.say_to(name, self._warn(
                            f"你正在靠近 {land.owner} 的领地，请勿进入"))
                        break

    def _tp_random(self, player: str, x: float, y: float, z: float):
        """Implement the tp random operation."""
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(10, self.tp_radius)
        nx = x + dist * math.cos(angle)
        nz = z + dist * math.sin(angle)
        ny = y
        cmd = f"/tp {player} {nx} {ny} {nz}"
        self.game_ctrl.sendwocmd(cmd)

    # ---------- 实体标记（可选） ----------
    def _spawn_entity(self, land: LandData):
        """Implement the spawn entity operation."""
        try:
            x, y, z = land.center
            self._remove_entity(land)
            nbt = (
                "{"
                "Duration:2147483647,WaitTime:2147483647,Tags:[\"land_"
                + land.land_id
                + "\"]"
                "}"
            )
            cmd = f"summon area_effect_cloud {x} {y} {z} {nbt}"
            self.game_ctrl.sendwocmd(cmd)
        except Exception:
            pass

    def _remove_entity(self, land: LandData):
        """Implement the remove entity operation."""
        try:
            cmd = f"kill @e[type=area_effect_cloud,tag=land_{land.land_id}]"
            self.game_ctrl.sendwocmd(cmd)
        except Exception:
            pass

    # ---------- 命令处理 ----------
    def on_chat(self, chat: Chat):
        """Implement the on chat operation."""
        if not self.enabled:
            return
        msg = chat.msg.strip()
        if msg not in self.wake_words:
            return
        self._main_menu(chat.player)

    def _main_menu(self, player: Player):
        """Implement the main menu operation."""
        choice = self._select_menu(
            player,
            "功能菜单",
            [
                "创建领地",
                "删除领地",
                "查看领地信息",
                "成员管理",
                "管理员管理",
                "传送到领地",
                "查看领地列表",
                "测试当前位置",
            ],
            timeout=90,
        )
        if choice is None:
            return
        if choice == 1:
            self._menu_create(player)
        elif choice == 2:
            self._menu_delete(player)
        elif choice == 3:
            self._menu_info(player)
        elif choice == 4:
            self._menu_member(player)
        elif choice == 5:
            self._menu_admin(player)
        elif choice == 6:
            self._menu_tp(player)
        elif choice == 7:
            self._list(player)
        elif choice == 8:
            self._test(player)

    def _menu_create(self, player: Player):
        """Implement the menu create operation."""
        name = self._prompt_text(player, "创建领地", "请输入领地名称")
        if name is None:
            return
        shape_choice = self._select_menu(player, "创建领地类型", ["圆形领地", "方形领地"])
        if shape_choice is None:
            return
        if shape_choice == 1:
            radius = self._prompt_text(
                player, "创建圆形领地", f"请输入领地半径，范围 1~{self.max_radius}")
            if radius is None:
                return
            self._create(player, [name, "圆形", radius])
        else:
            size_text = self._prompt_text(
                player,
                "创建方形领地",
                f"请输入 长 高 宽，最大 {self.max_length} {self.max_height} {self.max_width}",
            )
            if size_text is None:
                return
            size, err = self._parse_box_size_input(size_text)
            if size is None:
                player.show(self._error(err or "方形领地尺寸无效"))
                return
            self._create(
                player, [
                    name, "方形", str(
                        size[0]), str(
                        size[1]), str(
                        size[2])])

    def _menu_delete(self, player: Player):
        """Implement the menu delete operation."""
        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        owned = [land for land in self.lands.values(
        ) if land.owner_xuid == player_xuid]
        land = self._select_land(player, "删除领地", owned)
        if land is None:
            return
        self._delete(player, [land.name])

    def _menu_info(self, player: Player):
        """Implement the menu info operation."""
        choice = self._select_menu(
            player,
            "查看领地信息",
            ["查看当前所在领地", "从我的领地中选择", "从全部领地中选择", "输入领地名称"],
        )
        if choice is None:
            return
        if choice == 1:
            self._info(player, [])
        elif choice == 2:
            player_xuid = self._get_player_xuid(player)
            if player_xuid is None:
                player.show(self._error("无法获取你的 XUID"))
                return
            lands = [land for land in self.lands.values() if land.owner_xuid ==
                     player_xuid]
            land = self._select_land(player, "我的领地", lands)
            if land:
                self._info(player, [land.name])
        elif choice == 3:
            land = self._select_land(player, "全部领地", list(self.lands.values()))
            if land:
                self._info(player, [land.name])
        elif choice == 4:
            name = self._prompt_text(player, "查看领地信息", "请输入领地名称")
            if name:
                self._info(player, [name])

    def _menu_member(self, player: Player):
        """Implement the menu member operation."""
        choice = self._select_menu(player, "成员管理", ["添加成员", "移除成员", "查看成员列表"])
        if choice is None:
            return
        if choice == 3:
            self._member(player, ["列表"])
            return
        target = self._prompt_text(
            player,
            "成员管理",
            "请输入玩家名",
        )
        if target is None:
            return
        self._member(player, [["添加", "移除"][choice - 1], target])

    def _menu_admin(self, player: Player):
        """Implement the menu admin operation."""
        choice = self._select_menu(player, "管理员管理", ["添加管理员", "移除管理员"])
        if choice is None:
            return
        target = self._prompt_text(player, "管理员管理", "请输入玩家名")
        if target is None:
            return
        self._admin(player, [["添加", "移除"][choice - 1], target])

    def _menu_tp(self, player: Player):
        """Implement the menu tp operation."""
        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        lands = [land for land in self.lands.values(
        ) if land.has_permission(player_xuid, "tp")]
        land = self._select_land(player, "传送到领地", lands)
        if land is None:
            return
        self._tp(player, [land.name])

    def _create(self, player: Player, args: List[str]):  # skipcq: PY-R1000
        """Implement the create operation."""
        if len(args) < 2:
            player.show(self._error(
                f"请直接输入唤醒词 {' / '.join(self.wake_words)} 进入创建菜单"))
            return
        name = args[0]
        shape_arg = str(args[1]).strip().lower()
        explicit_circle = shape_arg in ("圆形", "circle", "round")
        explicit_box = LandData.normalize_shape(shape_arg) == "方形"
        shape = "方形" if explicit_box else "圆形"
        size = None
        if shape == "方形":
            if len(args) < 5:
                player.show(self._error("方形领地需要输入 长 高 宽"))
                return
            size, err = self._parse_box_size_input(" ".join(args[2:5]))
            if size is None:
                player.show(self._error(err or "方形领地尺寸无效"))
                return
            radius = box_radius_for_size(size)
        else:
            radius_arg = args[2] if len(
                args) >= 3 and explicit_circle else args[1]
            try:
                radius = int(radius_arg)
            except ValueError:
                player.show(self._error("半径必须为整数"))
                return
            if radius <= 0 or radius > self.max_radius:
                player.show(self._error(f"半径必须在 1~{self.max_radius} 之间"))
                return

        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        owned = [
            land_item for land_item in self.lands.values()
            if land_item.owner_xuid == player_xuid
        ]
        if len(owned) >= self.max_lands_per_player:
            player.show(
                self._error(
                    f"你最多只能拥有 {self.max_lands_per_player} 个领地"))
            return

        pos = self._get_player_coord(player.name)
        if not pos:
            player.show(self._warn("无法自动获取坐标，请手动输入"))
            pos = self._manual_coord(player)
            if not pos:
                return
        x, y, z = pos

        overlap = self._get_land_candidate_overlap_reason(
            (x, y, z), radius, shape, size)
        if overlap:
            player.show(self._error(overlap))
            return

        land_id = str(uuid.uuid4())
        member = LandMember(
            name=player.name,
            xuid=player_xuid,
            rank=LandRank.OWNER)
        land = LandData(
            land_id=land_id,
            name=name,
            owner=player.name,
            owner_xuid=player_xuid,
            center=(x, y, z),
            radius=radius,
            shape=shape,
            size=size,
            members=[member]
        )
        self.lands[land_id] = land
        self._add_player_land(player_xuid, land_id)
        self._save_data()
        player.show(self._success(f"成功创建领地 '{name}'，{land.range_text()}"))
        self._spawn_entity(land)

    def _delete(self, player: Player, args: List[str]):
        """Implement the delete operation."""
        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        owned = [
            land_item for land_item in self.lands.values()
            if land_item.owner_xuid == player_xuid
        ]
        if not owned:
            player.show(self._error("你没有拥有任何领地"))
            return

        if args:
            name = args[0]
            land = next(
                (land_item for land_item in owned if land_item.name == name),
                None,
            )
            if not land:
                player.show(self._error(f"你没有名为 '{name}' 的领地"))
                return
        else:
            if len(owned) > 1:
                names = "、".join(land_item.name for land_item in owned)
                player.show(self._error(f"你拥有多个领地，请指定名称：{names}"))
                return
            land = owned[0]

        self._remove_entity(land)
        for m in land.members:
            self._remove_player_land(m.xuid, land.land_id)
        del self.lands[land.land_id]
        self._save_data()
        player.show(self._success(f"已删除领地 '{land.name}'"))

    def _info(self, player: Player, args: List[str]):
        """Implement the info operation."""
        land = None
        if args:
            name = args[0]
            land = next(
                (
                    land_item for land_item in self.lands.values()
                    if land_item.name == name
                ),
                None,
            )
            if not land:
                player.show(self._error(f"领地 '{name}' 不存在"))
                return
        else:
            land = self._find_land_at_player(player.name)
            if not land:
                player.show(self._error("你当前不在任何领地内，请指定领地名称"))
                return

        admins = [m.name for m in land.members if m.rank == LandRank.ADMIN]
        members = [m.name for m in land.members if m.rank == LandRank.MEMBER]
        player.show(self._ui_card(
            f"领地信息 - {land.name}",
            [
                f"中心：{land.center[0]}, {land.center[1]}, {land.center[2]}",
                f"范围：{land.range_text()}",
                f"领主：{land.owner}",
                f"管理员：{', '.join(admins) or '无'}",
                f"成员：{', '.join(members) or '无'}",
            ],
        ))

    def _member(self, player: Player, args: List[str]):  # skipcq: PY-R1000
        """Implement the member operation."""
        if len(args) < 1:
            player.show(self._error(
                f"请直接输入唤醒词 {' / '.join(self.wake_words)} 进入成员管理菜单"))
            return
        sub = args[0].lower()
        if sub == "列表":
            land = self._find_land_at_player(player.name)
            if not land:
                player.show(self._error("你当前不在任何领地内"))
                return
            self._info(player, [land.name])
            return

        if len(args) < 2:
            player.show(self._error(
                f"请直接输入唤醒词 {' / '.join(self.wake_words)} 进入成员管理菜单"))
            return
        target = args[1]
        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        target_member = self._make_member(
            target, LandRank.MEMBER, allow_offline=True)
        if target_member is None:
            player.show(self._error(f"无法获取 {target} 的 XUID"))
            return

        land = self._find_land_at_player(player.name)
        if not land:
            player.show(self._error("你当前不在任何领地内"))
            return

        if not land.has_permission(player_xuid, "manage_member"):
            player.show(self._error("你没有权限管理成员"))
            return

        if sub == "添加":
            if land.get_member(target_member.xuid):
                player.show(self._warn(f"{target} 已是成员"))
                return
            land.members.append(target_member)
            self._add_player_land(target_member.xuid, land.land_id)
            self._save_data()
            player.show(self._success(f"已将 {target} 添加为成员"))
        elif sub == "移除":
            if not land.get_member(target_member.xuid):
                player.show(self._error(f"{target} 不是成员"))
                return
            if not land.can_manage_member(player_xuid, target_member.xuid):
                player.show(self._error("你不能移除该成员"))
                return
            land.members = [
                m for m in land.members if m.xuid != target_member.xuid]
            self._remove_player_land(target_member.xuid, land.land_id)
            self._save_data()
            player.show(self._success(f"已将 {target} 移除成员"))
        else:
            player.show(self._error("未知子命令"))

    def _admin(self, player: Player, args: List[str]):
        """Implement the admin operation."""
        if len(args) < 2:
            player.show(self._error(
                f"请直接输入唤醒词 {' / '.join(self.wake_words)} 进入管理员管理菜单"))
            return
        sub = args[0].lower()
        target = args[1]
        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        target_xuid = self._get_xuid_by_name(target, allow_offline=True)
        if target_xuid is None:
            player.show(self._error(f"无法获取 {target} 的 XUID"))
            return

        land = self._find_land_at_player(player.name)
        if not land:
            player.show(self._error("你当前不在任何领地内"))
            return

        if land.owner_xuid != player_xuid:
            player.show(self._error("只有领主可以管理管理员"))
            return

        if sub == "添加":
            member = land.get_member(target_xuid)
            if not member:
                player.show(self._error(f"{target} 不是成员"))
                return
            if member.rank == LandRank.ADMIN:
                player.show(self._warn(f"{target} 已经是管理员"))
                return
            member.rank = LandRank.ADMIN
            self._save_data()
            player.show(self._success(f"已将 {target} 设为管理员"))
        elif sub == "移除":
            member = land.get_member(target_xuid)
            if not member or member.rank != LandRank.ADMIN:
                player.show(self._error(f"{target} 不是管理员"))
                return
            member.rank = LandRank.MEMBER
            self._save_data()
            player.show(self._success(f"已将 {target} 移除管理员"))
        else:
            player.show(self._error("未知子命令"))

    def _tp(self, player: Player, args: List[str]):
        """Implement the tp operation."""
        land = None
        if args:
            name = args[0]
            land = next(
                (
                    land_item for land_item in self.lands.values()
                    if land_item.name == name
                ),
                None,
            )
            if not land:
                player.show(self._error(f"领地 '{name}' 不存在"))
                return
        else:
            land = self._find_land_at_player(player.name)
            if not land:
                player_xuid = self._get_player_xuid(player)
                if player_xuid is None:
                    player.show(self._error("无法获取你的 XUID"))
                    return
                owned = [
                    land_item for land_item in self.lands.values()
                    if land_item.owner_xuid == player_xuid
                ]
                if owned:
                    land = owned[0]
                else:
                    player.show(self._error("你当前不在任何领地内，且你没有拥有领地，请指定名称"))
                    return

        player_xuid = self._get_player_xuid(player)
        if player_xuid is None:
            player.show(self._error("无法获取你的 XUID"))
            return
        if not land.has_permission(player_xuid, "tp"):
            player.show(self._error("你没有权限传送到该领地"))
            return

        cx, cy, cz = land.center
        self.game_ctrl.sendwocmd(f"/tp {player.name} {cx} {cy + 1} {cz}")
        player.show(self._success(f"已传送到领地 '{land.name}'"))

    def _list(self, player: Player):
        """Implement the list operation."""
        if not self.lands:
            player.show(self._error("暂无任何领地"))
            return
        options = [
            f"{land.name} §7- 领主: {land.owner}, {land.range_text()}"
            for land in self.lands.values()
        ]
        player.show(self._ui_menu("领地列表", options, [f"共 {len(options)} 个领地"]))

    def _test(self, player: Player):
        """Implement the test operation."""
        pos = self._get_player_coord(player.name)
        lines = []
        if pos:
            lines.append(f"当前坐标：{pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}")
        else:
            lines.append("无法获取坐标")

        in_land = self._find_land_at_player(player.name)
        if in_land:
            lines.append(f"当前位置：位于领地 '{in_land.name}' 内")
        else:
            lines.append("当前位置：不在任何领地内")

        if self.lands:
            lines.append(
                "所有领地："
                + "、".join(
                    f"{land.name}({land.owner})" for land in self.lands.values()
                )
            )
        else:
            lines.append("所有领地：无")
        player.show(self._ui_card("测试信息", lines))

    def on_player_join(self, player: Player):
        """Implement the on player join operation."""
        _ = player
        if not self.enabled:
            return
        return

    def on_player_leave(self, player: Player):
        """Implement the on player leave operation."""
        _ = player
        if not self.enabled:
            return
        return

    # ---------- 外部插件 API ----------
    def api_list_lands(self) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Expose the api list lands API operation."""
        lands = [self._land_summary(land) for land in self.lands.values()]
        return True, f"共 {len(lands)} 个领地", lands

    def api_get_land(
            self, land_query: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Expose the api get land API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        return True, "查询成功", self._land_summary(land)

    def api_add_land(  # skipcq: PY-R1000
        self,
        owner: str,
        name: str,
        center: Tuple[float, float, float],
        shape: str = "圆形",
        radius: Optional[int] = None,
        size: Optional[Tuple[int, int, int]] = None,
        dimension: int = 0,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Expose the api add land API operation."""
        owner = str(owner).strip()
        name = str(name).strip()
        if not owner or not name:
            return False, "领地主人和领地名称不能为空", None
        if self._find_land_by_name_or_id(name):
            return False, f"领地 '{name}' 已存在", None
        owner_member = self._make_member(
            owner, LandRank.OWNER, allow_offline=True)
        if owner_member is None:
            return False, f"无法获取 {owner} 的 XUID", None
        if len([land for land in self.lands.values() if land.owner_xuid ==
               owner_member.xuid]) >= self.max_lands_per_player:
            return False, f"{owner} 已达到最大领地数量 {self.max_lands_per_player}", None
        try:
            center_tuple = (
                float(
                    center[0]), float(
                    center[1]), float(
                    center[2]))
        except (TypeError, ValueError, IndexError):
            return False, "中心坐标无效", None

        normalized_shape = LandData.normalize_shape(shape)
        normalized_size = None
        if normalized_shape == "方形":
            if size is None:
                return False, "方形领地需要提供 长 高 宽", None
            normalized_size = LandData.normalize_size(size, radius or 1)
            if normalized_size[0] > self.max_length:
                return False, f"长不能超过 {self.max_length}", None
            if normalized_size[1] > self.max_height:
                return False, f"高不能超过 {self.max_height}", None
            if normalized_size[2] > self.max_width:
                return False, f"宽不能超过 {self.max_width}", None
            land_radius = box_radius_for_size(normalized_size)
        else:
            try:
                land_radius = int(radius)
            except (TypeError, ValueError):
                return False, "圆形领地半径必须为整数", None
            if land_radius <= 0 or land_radius > self.max_radius:
                return False, f"半径必须在 1~{self.max_radius} 之间", None

        overlap = self._get_land_candidate_overlap_reason(
            center_tuple,
            land_radius,
            normalized_shape,
            normalized_size,
            dimension,
        )
        if overlap:
            return False, overlap, None

        land_id = str(uuid.uuid4())
        land = LandData(
            land_id=land_id,
            name=name,
            owner=owner,
            owner_xuid=owner_member.xuid,
            center=center_tuple,
            radius=land_radius,
            shape=normalized_shape,
            size=normalized_size,
            dimension=dimension,
            members=[owner_member],
        )
        self.lands[land_id] = land
        self._rebuild_player_land_cache()
        self._save_data()
        self._spawn_entity(land)
        return True, f"已新增玩家 {owner} 的领地 '{name}'，{land.range_text()}", self._land_summary(land)

    def api_delete_land(self, land_query: str) -> Tuple[bool, str, None]:
        """Expose the api delete land API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        self._remove_entity(land)
        del self.lands[land.land_id]
        self._rebuild_player_land_cache()
        self._save_data()
        return True, f"已删除领地 '{land.name}'", None

    def api_add_member(self,
                       land_query: str,
                       player_name: str,
                       rank: str = "member") -> Tuple[bool,
                                                      str,
                                                      Optional[Dict[str,
                                                                    Any]]]:
        """Expose the api add member API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        target_rank = LandRank.ADMIN if str(rank).lower() in (
            "admin", "管理员", "管理") else LandRank.MEMBER
        member = self._make_member(
            player_name, target_rank, allow_offline=True)
        if member is None:
            return False, f"无法获取 {player_name} 的 XUID", None
        old_member = land.get_member(member.xuid)
        if old_member:
            if old_member.rank == LandRank.OWNER:
                return False, "所有者不能被改为成员或管理员", self._land_summary(land)
            old_member.name = player_name
            old_member.rank = target_rank
        else:
            land.members.append(member)
        self._rebuild_player_land_cache()
        self._save_data()
        role_name = "管理员" if target_rank == LandRank.ADMIN else "成员"
        return True, f"已将 {player_name} 添加为领地 '{land.name}' 的{role_name}", self._land_summary(land)

    def api_set_member_rank(
        self,
        land_query: str,
        player_name: str,
        rank: str,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Expose the api set member rank API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        target_rank = LandRank.ADMIN if str(rank).lower() in (
            "admin", "管理员", "管理") else LandRank.MEMBER
        target_xuid = self._get_xuid_by_name(player_name, allow_offline=True)
        if target_xuid is None:
            return False, f"无法获取 {player_name} 的 XUID", None
        member = land.get_member(target_xuid)
        if member is None:
            return False, f"{player_name} 不在领地 '{land.name}' 中", self._land_summary(land)
        if member.rank == LandRank.OWNER:
            return False, "所有者不能修改身份", self._land_summary(land)
        member.name = player_name
        member.rank = target_rank
        self._save_data()
        role_name = "管理员" if target_rank == LandRank.ADMIN else "成员"
        return True, f"已将 {player_name} 设为领地 '{land.name}' 的{role_name}", self._land_summary(land)

    def api_remove_member(self,
                          land_query: str,
                          player_name: str) -> Tuple[bool,
                                                     str,
                                                     Optional[Dict[str,
                                                                   Any]]]:
        """Expose the api remove member API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        target_xuid = self._get_xuid_by_name(player_name, allow_offline=True)
        if target_xuid is None:
            return False, f"无法获取 {player_name} 的 XUID", None
        member = land.get_member(target_xuid)
        if not member:
            return False, f"{player_name} 不在领地 '{land.name}' 中", self._land_summary(land)
        if member.rank == LandRank.OWNER:
            return False, "不能删除领地所有者，请先转移所有者", self._land_summary(land)
        land.members = [m for m in land.members if m.xuid != target_xuid]
        self._rebuild_player_land_cache()
        self._save_data()
        return True, f"已从领地 '{land.name}' 移除 {player_name}", self._land_summary(land)

    def api_transfer_owner(
        self,
        land_query: str,
        owner: str,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Expose the api transfer owner API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        owner_member_data = self._make_member(
            owner, LandRank.OWNER, allow_offline=True)
        if owner_member_data is None:
            return False, f"无法获取 {owner} 的 XUID", None
        land.owner = owner
        land.owner_xuid = owner_member_data.xuid
        for member in land.members:
            if member.rank == LandRank.OWNER:
                member.rank = LandRank.ADMIN
        owner_member = land.get_member(owner_member_data.xuid)
        if owner_member:
            owner_member.name = owner
            owner_member.rank = LandRank.OWNER
        else:
            land.members.append(owner_member_data)
        self._rebuild_player_land_cache()
        self._save_data()
        return True, f"已修改领地 '{land.name}' 所有者为 {owner}", self._land_summary(land)

    def api_update_land_center(
        self,
        land_query: str,
        center: Tuple[float, float, float],
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Expose the api update land center API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        try:
            center_tuple = (
                float(
                    center[0]), float(
                    center[1]), float(
                    center[2]))
        except (TypeError, ValueError, IndexError):
            return False, "中心坐标无效", self._land_summary(land)
        overlap = self._get_land_edit_overlap_reason(
            land, center_tuple, land.radius)
        if overlap:
            return False, overlap, self._land_summary(land)
        land.center = center_tuple
        self._save_data()
        self._spawn_entity(land)
        return True, f"已修改领地 '{land.name}' 中心点", self._land_summary(land)

    def api_update_land_range(
        self,
        land_query: str,
        radius: Optional[int] = None,
        size: Optional[Tuple[int, int, int]] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Expose the api update land range API operation."""
        land = self._find_land_by_name_or_id(land_query)
        if land is None:
            return False, f"领地 '{land_query}' 不存在", None
        if land.is_box():
            if size is None:
                return False, "方形领地需要提供 长 高 宽", self._land_summary(land)
            normalized_size = LandData.normalize_size(size, land.radius)
            if normalized_size[0] > self.max_length:
                return False, f"长不能超过 {self.max_length}", self._land_summary(land)
            if normalized_size[1] > self.max_height:
                return False, f"高不能超过 {self.max_height}", self._land_summary(land)
            if normalized_size[2] > self.max_width:
                return False, f"宽不能超过 {self.max_width}", self._land_summary(land)
            land_radius = box_radius_for_size(normalized_size)
            overlap = self._get_land_edit_overlap_reason(
                land, land.center, land_radius, "方形", normalized_size)
            if overlap:
                return False, overlap, self._land_summary(land)
            land.size = normalized_size
            land.radius = land_radius
        else:
            try:
                land_radius = int(radius)
            except (TypeError, ValueError):
                return False, "半径必须为整数", self._land_summary(land)
            if land_radius <= 0 or land_radius > self.max_radius:
                return False, f"半径必须在 1~{self.max_radius} 之间", self._land_summary(land)
            overlap = self._get_land_edit_overlap_reason(
                land, land.center, land_radius, "圆形", None)
            if overlap:
                return False, overlap, self._land_summary(land)
            land.radius = land_radius
            land.size = None
        self._save_data()
        return True, f"已修改领地 '{land.name}' 范围为 {land.range_text()}", self._land_summary(land)

    def _console_print(self, text: str):
        """Implement the console print operation."""
        _ = self
        fmts.print_inf(text)

    def _console_prompt(self, prompt: str) -> Optional[str]:
        """Implement the console prompt operation."""
        value = input(fmts.fmt_info(
            f"§a❀ §b{prompt} §7(输入 . 退出整个领地系统云链联动版管理菜单): ")).strip()
        if self._is_exit_input(value):
            raise ConsoleMenuExit
        return value

    def _console_select(self, title: str, options: List[str]) -> Optional[int]:
        """Implement the console select operation."""
        while True:
            self._console_print(self._ui_menu(
                title,
                options,
                [f"输入 §e[1-{len(options)}]§b 之间的数字以选择", "输入 §c.§b 退出整个领地系统云链联动版管理菜单"],
            ))
            value = self._console_prompt("请输入序号")
            if value is None:
                return None
            choice = utils.try_int(value.strip().strip("[]"))
            if choice is None or choice not in range(1, len(options) + 1):
                fmts.print_err(self._error("输入有误"))
                continue
            return choice

    def _console_prompt_float(self, prompt: str) -> Optional[float]:
        """Implement the console prompt float operation."""
        value = self._console_prompt(prompt)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            fmts.print_err(self._error("请输入有效数字"))
            return None

    def _console_prompt_int(self, prompt: str) -> Optional[int]:
        """Implement the console prompt int operation."""
        value = self._console_prompt(prompt)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            fmts.print_err(self._error("请输入有效整数"))
            return None

    def _console_prompt_pos(self, prompt: str) -> Optional[List[float]]:
        """Implement the console prompt pos operation."""
        value = self._console_prompt(f"{prompt}，格式 x y z")
        if value is None:
            return None
        parts = value.split()
        if len(parts) != 3:
            fmts.print_err(self._error("坐标格式错误，需要 x y z 三个数字"))
            return None
        try:
            return [float(parts[0]), float(parts[1]), float(parts[2])]
        except ValueError:
            fmts.print_err(self._error("坐标必须是数字"))
            return None

    def _console_select_land(
        self,
        title: str,
        lands: Optional[List[LandData]] = None,
    ) -> Optional[LandData]:
        """Implement the console select land operation."""
        lands = list(self.lands.values()) if lands is None else lands
        if not lands:
            fmts.print_err(self._error("暂无可选择的领地"))
            return None
        choice = self._console_select(
            title,
            [f"{land.name} - 领主: {land.owner}, {land.range_text()}" for land in lands],
        )
        if choice is None:
            return None
        return lands[choice - 1]

    def console_manage(self, _args: List[str]):
        """Implement the console manage operation."""
        try:
            while True:
                choice = self._console_select(
                    "控制台管理菜单",
                    ["新增不可创建领地区域", "删除不可创建领地区域", "新增玩家领地", "删除玩家领地", "管理玩家领地"],
                )
                if choice is None:
                    fmts.print_inf(self._success("已退出领地系统云链联动版管理菜单"))
                    return
                if choice == 1:
                    self._console_add_no_create_region()
                elif choice == 2:
                    self._console_delete_no_create_region()
                elif choice == 3:
                    self._console_add_land()
                elif choice == 4:
                    self._console_delete_land()
                elif choice == 5:
                    self._console_manage_land()
        except ConsoleMenuExit:
            fmts.print_inf(self._success("已退出领地系统云链联动版管理菜单"))

    def _console_add_no_create_region(self):
        """Implement the console add no create region operation."""
        name = self._console_prompt("请输入区域名称")
        if name is None:
            return
        region_choice = self._console_select("新增不可创建区域", ["圆形区域", "方形区域"])
        if region_choice is None:
            return
        if region_choice == 1:
            center = self._console_prompt_pos("请输入圆形区域中心")
            radius = self._console_prompt_float("请输入圆形区域半径")
            if center is None or radius is None or radius <= 0:
                fmts.print_err(self._error("区域参数无效"))
                return
            region = {
                "名称": name,
                "启用": True,
                "类型": "圆形",
                "中心": center,
                "半径": radius}
        else:
            start = self._console_prompt_pos("请输入方形区域起点")
            end = self._console_prompt_pos("请输入方形区域终点")
            if start is None or end is None:
                fmts.print_err(self._error("区域参数无效"))
                return
            region = {
                "名称": name,
                "启用": True,
                "类型": "方形",
                "起点": start,
                "终点": end}
        self.no_create_regions_raw.append(region)
        self._save_no_create_regions()
        self._reload_no_create_regions()
        fmts.print_suc(self._success(f"已新增不可创建领地区域 '{name}'"))

    def _console_delete_no_create_region(self):
        """Implement the console delete no create region operation."""
        if not self.no_create_regions_raw:
            fmts.print_err(self._error("暂无不可创建领地区域"))
            return
        choice = self._console_select(
            "删除不可创建区域",
            [
                (
                    f"{region.get('名称', f'区域{i}')} - "
                    f"{region.get('类型', '未知')} - "
                    f"{'启用' if region.get('启用', True) else '禁用'}"
                )
                for i, region in enumerate(self.no_create_regions_raw, 1)
            ],
        )
        if choice is None:
            return
        region = self.no_create_regions_raw.pop(choice - 1)
        self._save_no_create_regions()
        self._reload_no_create_regions()
        fmts.print_suc(
            self._success(
                f"已删除不可创建领地区域 '{region.get('名称',choice)}'"))

    def _console_add_land(self):
        """Implement the console add land operation."""
        owner = self._console_prompt("请输入领地主人玩家名")
        name = self._console_prompt("请输入领地名称")
        center = self._console_prompt_pos("请输入领地中心坐标")
        shape_choice = self._console_select("请选择领地类型", ["圆形领地", "方形领地"])
        if owner is None or name is None or center is None or shape_choice is None:
            return
        owner_member = self._make_member(
            owner, LandRank.OWNER, allow_offline=True)
        if owner_member is None:
            fmts.print_err(self._error(f"无法获取 {owner} 的 XUID"))
            return
        shape = "圆形"
        size = None
        if shape_choice == 1:
            radius = self._console_prompt_int(
                f"请输入领地半径，范围 1~{self.max_radius}")
            if radius is None:
                return
            if radius <= 0 or radius > self.max_radius:
                fmts.print_err(self._error(f"半径必须在 1~{self.max_radius} 之间"))
                return
        else:
            size_text = self._console_prompt(
                f"请输入方形领地 长 高 宽，最大 {self.max_length} {self.max_height} {self.max_width}")
            if size_text is None:
                return
            size, err = self._parse_box_size_input(size_text)
            if size is None:
                fmts.print_err(self._error(err or "方形领地尺寸无效"))
                return
            shape = "方形"
            radius = box_radius_for_size(size)
        overlap = self._get_land_candidate_overlap_reason(
            tuple(center), radius, shape, size)
        if overlap:
            fmts.print_err(self._error(overlap))
            return
        land_id = str(uuid.uuid4())
        land = LandData(
            land_id=land_id,
            name=name,
            owner=owner,
            owner_xuid=owner_member.xuid,
            center=tuple(center),
            radius=radius,
            shape=shape,
            size=size,
            members=[owner_member],
        )
        self.lands[land_id] = land
        self._rebuild_player_land_cache()
        self._save_data()
        self._spawn_entity(land)
        fmts.print_suc(
            self._success(
                f"已新增玩家 {owner} 的领地 '{name}'，{land.range_text()}"))

    def _console_delete_land(self):
        """Implement the console delete land operation."""
        land = self._console_select_land("删除玩家领地")
        if land is None:
            return
        self._remove_entity(land)
        del self.lands[land.land_id]
        self._rebuild_player_land_cache()
        self._save_data()
        fmts.print_suc(self._success(f"已删除领地 '{land.name}'"))

    def _console_manage_land(self):
        """Implement the console manage land operation."""
        land = self._console_select_land("管理玩家领地")
        if land is None:
            return
        while True:
            choice = self._console_select(
                f"管理领地 - {land.name}",
                ["管理用户", "管理管理人员", "管理所有者", "管理领地中心点", "管理领地范围", "查看领地信息"],
            )
            if choice is None:
                return
            if choice == 1:
                self._console_manage_land_users(land)
            elif choice == 2:
                self._console_manage_land_admins(land)
            elif choice == 3:
                self._console_manage_land_owner(land)
            elif choice == 4:
                self._console_manage_land_center(land)
            elif choice == 5:
                self._console_manage_land_radius(land)
            elif choice == 6:
                self._console_show_land_info(land)

    def _console_show_land_info(self, land: LandData):
        """Implement the console show land info operation."""
        admins = [m.name for m in land.members if m.rank == LandRank.ADMIN]
        members = [m.name for m in land.members if m.rank == LandRank.MEMBER]
        fmts.print_inf(self._ui_card(
            f"领地信息 - {land.name}",
            [
                f"领主：{land.owner}",
                f"中心：{land.center[0]}, {land.center[1]}, {land.center[2]}",
                f"范围：{land.range_text()}",
                f"管理员：{', '.join(admins) or '无'}",
                f"用户：{', '.join(members) or '无'}",
            ],
        ))

    def _console_manage_land_users(self, land: LandData):  # skipcq: PY-R1000
        """Implement the console manage land users operation."""
        while True:
            choice = self._console_select(
                f"管理用户 - {land.name}",
                ["添加用户", "删除用户", "查看用户列表"],
            )
            if choice is None:
                return
            if choice == 1:
                target = self._console_prompt("请输入要添加的玩家名")
                if not target:
                    continue
                member = self._make_member(
                    target, LandRank.MEMBER, allow_offline=True)
                if member is None:
                    fmts.print_err(self._error(f"无法获取 {target} 的 XUID"))
                    continue
                if land.get_member(member.xuid):
                    fmts.print_err(self._warn(f"{target} 已在该领地中"))
                    continue
                land.members.append(member)
                self._rebuild_player_land_cache()
                self._save_data()
                fmts.print_suc(self._success(f"已添加用户 {target}"))
            elif choice == 2:
                target = self._console_prompt("请输入要删除的玩家名")
                if not target:
                    continue
                target_xuid = self._get_xuid_by_name(
                    target, allow_offline=True)
                if target_xuid is None:
                    fmts.print_err(self._error(f"无法获取 {target} 的 XUID"))
                    continue
                member = land.get_member(target_xuid)
                if not member:
                    fmts.print_err(self._error(f"{target} 不在该领地中"))
                    continue
                if member.rank == LandRank.OWNER:
                    fmts.print_err(self._error("不能在用户管理中删除所有者，请先转移所有者"))
                    continue
                land.members = [
                    m for m in land.members if m.xuid != target_xuid]
                self._rebuild_player_land_cache()
                self._save_data()
                fmts.print_suc(self._success(f"已删除用户 {target}"))
            elif choice == 3:
                users = [
                    f"{m.name}({m.rank.display_name})" for m in land.members]
                fmts.print_inf(self._ui_card(
                    f"用户列表 - {land.name}",
                    [", ".join(users) if users else "无用户"],
                ))

    def _console_manage_land_admins(self, land: LandData):  # skipcq: PY-R1000
        """Implement the console manage land admins operation."""
        while True:
            choice = self._console_select(
                f"管理管理人员 - {land.name}",
                ["添加管理人员", "删除管理人员", "查看管理人员"],
            )
            if choice is None:
                return
            if choice == 1:
                target = self._console_prompt("请输入要设为管理人员的玩家名")
                if not target:
                    continue
                target_xuid = self._get_xuid_by_name(
                    target, allow_offline=True)
                if target_xuid is None:
                    fmts.print_err(self._error(f"无法获取 {target} 的 XUID"))
                    continue
                member = land.get_member(target_xuid)
                if member and member.rank == LandRank.OWNER:
                    fmts.print_err(self._error("所有者不能设为管理人员"))
                    continue
                if member:
                    member.name = target
                    member.rank = LandRank.ADMIN
                else:
                    land.members.append(
                        LandMember(
                            target,
                            target_xuid,
                            LandRank.ADMIN))
                self._rebuild_player_land_cache()
                self._save_data()
                fmts.print_suc(self._success(f"已将 {target} 设为管理人员"))
            elif choice == 2:
                target = self._console_prompt("请输入要删除管理权限的玩家名")
                if not target:
                    continue
                target_xuid = self._get_xuid_by_name(
                    target, allow_offline=True)
                if target_xuid is None:
                    fmts.print_err(self._error(f"无法获取 {target} 的 XUID"))
                    continue
                member = land.get_member(target_xuid)
                if not member or member.rank != LandRank.ADMIN:
                    fmts.print_err(self._error(f"{target} 不是管理人员"))
                    continue
                member.rank = LandRank.MEMBER
                self._rebuild_player_land_cache()
                self._save_data()
                fmts.print_suc(self._success(f"已删除 {target} 的管理权限"))
            elif choice == 3:
                admins = [
                    m.name for m in land.members if m.rank == LandRank.ADMIN]
                fmts.print_inf(self._ui_card(
                    f"管理人员 - {land.name}",
                    [", ".join(admins) if admins else "暂无管理人员"],
                ))

    def _console_manage_land_owner(self, land: LandData):
        """Implement the console manage land owner operation."""
        while True:
            choice = self._console_select(
                f"管理所有者 - {land.name}",
                ["修改所有者", "查看所有者"],
            )
            if choice is None:
                return
            if choice == 1:
                owner = self._console_prompt("请输入新所有者玩家名")
                if not owner:
                    continue
                owner_member_data = self._make_member(
                    owner, LandRank.OWNER, allow_offline=True)
                if owner_member_data is None:
                    fmts.print_err(self._error(f"无法获取 {owner} 的 XUID"))
                    continue
                land.owner = owner
                land.owner_xuid = owner_member_data.xuid
                for member in land.members:
                    if member.rank == LandRank.OWNER:
                        member.rank = LandRank.ADMIN
                owner_member = land.get_member(owner_member_data.xuid)
                if owner_member:
                    owner_member.name = owner
                    owner_member.rank = LandRank.OWNER
                else:
                    land.members.append(owner_member_data)
                self._rebuild_player_land_cache()
                self._save_data()
                fmts.print_suc(self._success(f"已修改所有者为 {owner}"))
            elif choice == 2:
                fmts.print_inf(self._ui_card(
                    f"所有者 - {land.name}", [land.owner]))

    def _console_manage_land_center(self, land: LandData):
        """Implement the console manage land center operation."""
        while True:
            choice = self._console_select(
                f"管理领地中心点 - {land.name}",
                ["修改中心点", "查看中心点"],
            )
            if choice is None:
                return
            if choice == 1:
                center = self._console_prompt_pos("请输入新的领地中心点")
                if center is None:
                    continue
                center_tuple = tuple(center)
                overlap = self._get_land_edit_overlap_reason(
                    land, center_tuple, land.radius)
                if overlap:
                    fmts.print_err(self._error(overlap))
                    continue
                land.center = center_tuple
                self._save_data()
                self._spawn_entity(land)
                fmts.print_suc(self._success(
                    f"已修改领地中心点为 {center[0]}, {center[1]}, {center[2]}"))
            elif choice == 2:
                fmts.print_inf(self._ui_card(
                    f"领地中心点 - {land.name}",
                    [f"{land.center[0]}, {land.center[1]}, {land.center[2]}"],
                ))

    def _console_manage_land_radius(self, land: LandData):
        """Implement the console manage land radius operation."""
        while True:
            options = [
                "修改方形长高宽",
                "查看方形长高宽"] if land.is_box() else [
                "修改范围半径",
                "查看范围半径"]
            choice = self._console_select(
                f"管理领地范围 - {land.name}",
                options,
            )
            if choice is None:
                return
            if choice == 1:
                if land.is_box():
                    size_text = self._console_prompt(
                        f"请输入新的 长 高 宽，最大 {self.max_length} {self.max_height} {self.max_width}")
                    if size_text is None:
                        continue
                    size, err = self._parse_box_size_input(size_text)
                    if size is None:
                        fmts.print_err(self._error(err or "方形领地尺寸无效"))
                        continue
                    radius = box_radius_for_size(size)
                    overlap = self._get_land_edit_overlap_reason(
                        land, land.center, radius, "方形", size)
                    if overlap:
                        fmts.print_err(self._error(overlap))
                        continue
                    land.shape = "方形"
                    land.size = size
                    land.radius = radius
                    self._save_data()
                    fmts.print_suc(self._success(
                        f"已修改方形领地范围为 长:{size[0]}, 高:{size[1]}, 宽:{size[2]}"))
                else:
                    radius = self._console_prompt_int(
                        f"请输入新范围半径，范围 1~{self.max_radius}")
                    if radius is None:
                        continue
                    if radius <= 0 or radius > self.max_radius:
                        fmts.print_err(
                            self._error(
                                f"半径必须在 1~{self.max_radius} 之间"))
                        continue
                    overlap = self._get_land_edit_overlap_reason(
                        land, land.center, radius, "圆形", None)
                    if overlap:
                        fmts.print_err(self._error(overlap))
                        continue
                    land.shape = "圆形"
                    land.size = None
                    land.radius = radius
                    self._save_data()
                    fmts.print_suc(self._success(f"已修改领地范围半径为 {radius}"))
            elif choice == 2:
                fmts.print_inf(self._ui_card(
                    f"领地范围 - {land.name}", [land.range_text()]))

    def _get_land_candidate_overlap_reason(
        self,
        center: Tuple[float, float, float],
        radius: int,
        shape: str,
        size: Optional[Tuple[int, int, int]] = None,
        dimension: int = 0,
        skip_land_id: Optional[str] = None,
    ) -> Optional[str]:
        """Return land candidate overlap reason data."""
        blocked_region = self._get_no_create_overlap_reason(
            center, radius, shape, size)
        if blocked_region:
            return f"领地不能与不可创建区域 '{blocked_region}' 重叠"
        for other in self.lands.values():
            if other.land_id == skip_land_id or other.dimension != dimension:
                continue
            if land_overlaps_candidate(other, center, radius, shape, size):
                return f"领地与 '{other.name}' 重叠"
        return None

    def _get_land_edit_overlap_reason(
        self,
        land: LandData,
        center: Tuple[float, float, float],
        radius: int,
        shape: Optional[str] = None,
        size: Optional[Tuple[int, int, int]] = None,
    ) -> Optional[str]:
        """Return land edit overlap reason data."""
        edit_shape = shape or land.shape
        edit_size = size if size is not None else land.size
        return self._get_land_candidate_overlap_reason(
            center,
            radius,
            edit_shape,
            edit_size,
            land.dimension,
            land.land_id,
        )

    def console_test(self, args: List[str]):
        """Implement the console test operation."""
        if not self.enabled:
            fmts.print_war(self._warn("领地系统云链联动版当前已在配置中禁用"))
            return
        if args:
            target = args[0]
            pos = self._get_player_coord(target)
            if pos:
                fmts.print_inf(
                    self._ui_card(
                        "控制台测试", [
                            f"玩家 {target} 坐标：{pos}"]))
            else:
                fmts.print_err(self._error("无法获取坐标"))
        else:
            fmts.print_inf(self._notice("用法: 领地测试 <玩家名>"))


entry = plugin_entry(LandPlugin, "领地系统云链联动版", (0, 1, 18))
