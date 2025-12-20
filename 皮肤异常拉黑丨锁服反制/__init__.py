import os
import json
import time
import threading
import base64
from typing import Any, Dict, Tuple, Optional

import requests

from tooldelta.plugin_load.classic_plugin import Plugin, plugin_entry
from tooldelta.constants import PacketIDS
from tooldelta import fmts


CONFIG_GROUP_VERSION = "0.2.3"
PAGE_LEN_API = 59

def _get(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    lower_map = {str(k).lower(): k for k in d.keys()}
    for k in keys:
        kk = lower_map.get(str(k).lower())
        if kk is not None and d.get(kk) is not None:
            return d.get(kk)
    return default


def _b64_to_bytes(v) -> bytes:
    if v is None:
        return b""
    if isinstance(v, bytes):
        return v
    if isinstance(v, str):
        return base64.b64decode(v)
    raise TypeError(f"unsupported type for b64 data: {type(v)}")


class SkinAbnormalStandalone(Plugin):
    name = "皮肤异常拉黑丨锁服反制"
    author = "丸山彩"
    version = (0, 2, 3)

    _ALLOW_CAPE = False
    _ANIM_COUNTS = {0, 1}
    _SKIN_SIZES = {64, 128, 256, 512}
    _ANIM_W = {0, 32}
    _ANIM_H = {0, 64}
    _REQUIRE_EMPTY_ANIMDATA = True

    _COOLDOWN_SEC = 60

    _URL_SEARCH_RENTALGAME = "https://nv1.nethard.pro/api/open-api/rentalGame/searchRentalGame"
    _URL_GET_PLAYER_LIST = "https://nv1.nethard.pro/api/open-api/rentalGame/getRentalGamePlayerList"
    _URL_SET_PLAYER_STATE = "https://nv1.nethard.pro/api/open-api/rentalGame/setRentalGamePlayerState"

    _URL_GET_SAUTH = "https://nv1.nethard.pro/api/open-api/user/getLoginUserSAuth"
    _URL_VITALITY_REFRESH = "https://nv1.nethard.pro/api/vitalityApi/refresh"

    _X_CALLER = "gameaccount"
    _COOKIE = "locale=en-us"
    _TIMEOUT_SEC = 10

    def __init__(self, frame):
        super().__init__(frame)

        base = os.path.dirname(os.path.dirname(self.data_path))
        self.root_dir = base
        self.main_cfg_path = os.path.join(self.root_dir, "ToolDelta基本配置.json")

        self.config_dir = os.path.join(self.root_dir, "插件配置文件")
        self.config_path = os.path.join(self.config_dir, f"{self.name}.json")

        self.cn = self._load_config_items()
        self.cfg = self._cn_to_internal(self.cn)

        self._runtime_enabled = True
        self._cooldown_ts: Dict[str, float] = {}
        self._lock = threading.Lock()

        self._sdkuid = ""
        self._vit_stop = threading.Event()
        self._vit_thread: Optional[threading.Thread] = None

        self._autofill_lock = threading.Lock()
        self._autofill_inflight = False

        self.ListenPreload(self._on_preload)
        self.ListenFrameExit(self._on_frame_exit)
        self.ListenPacket(PacketIDS.IDPlayerList, self._on_playerlist)

    # 配置

    def _default_items(self):
        return {
            "服务器ID": "填好API-Key会自动填",
            "NV1-OpenAPI-API-Key": "",
            "活力刷新间隔秒": 2400,
            "停止命令": "skinbanstop",
            "开启命令": "skinbanstart",
        }

    def _load_config_items(self):
        os.makedirs(self.config_dir, exist_ok=True)
        if not os.path.exists(self.config_path):
            items = self._default_items()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"配置版本": CONFIG_GROUP_VERSION, "配置项": items}, f, ensure_ascii=False, indent=2)
            return items

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                wrapped = json.load(f)
        except Exception:
            wrapped = {}

        items = wrapped.get("配置项", {}) if isinstance(wrapped, dict) else {}
        if not isinstance(items, dict):
            items = {}

        defaults = self._default_items()
        for k, v in defaults.items():
            items.setdefault(k, v)

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"配置版本": wrapped.get("配置版本", CONFIG_GROUP_VERSION), "配置项": items},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

        return items

    def _save_config_items(self, items: dict):
        wrapped = {"配置版本": CONFIG_GROUP_VERSION, "配置项": items}
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(wrapped, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _cn_to_internal(self, cn: dict):
        return {
            "server_entity_id": str(cn.get("服务器ID", "") or "").strip(),
            "api_key": str(cn.get("NV1-OpenAPI-API-Key", "") or "").strip(),
            "vitality_interval_sec": int(cn.get("活力刷新间隔秒", 2400) or 2400),
            "cmd_stop": str(cn.get("停止命令", "skinbanstop") or "skinbanstop").strip(),
            "cmd_start": str(cn.get("开启命令", "skinbanstart") or "skinbanstart").strip(),
        }

    def _on_preload(self):
        try:
            self.frame.add_console_cmd_trigger([self.cfg["cmd_stop"]], None, "停止：禁用检测并停止活力刷新", self._cmd_stop)
            self.frame.add_console_cmd_trigger([self.cfg["cmd_start"]], None, "开启：恢复检测并启动活力刷新", self._cmd_start)
        except Exception:
            pass

        if not self.cfg["api_key"]:
            try:
                fmts.print_war(f"[皮肤异常拉黑] 未填写 NV1-OpenAPI-API-Key，将不会拉黑/不会刷新活力")
                fmts.print_inf(f"[皮肤异常拉黑] 请编辑：{self.config_path}")
            except Exception:
                pass
            return False

        self._kick_autofill_server_entity_id()

        self._ensure_vitality_loop_started()
        return False

    def _on_frame_exit(self, evt):
        try:
            self._runtime_enabled = False
            self._stop_vitality_loop(join_sec=1.0)
        except Exception:
            pass
        return False

    def _cmd_stop(self, args: list[str]):
        self._runtime_enabled = False
        self._stop_vitality_loop(join_sec=1.0)
        try:
            fmts.print_suc(f"[皮肤异常拉黑] 已停止（检测关闭 + 活力线程停止），服主可以上线")
        except Exception:
            pass

    def _cmd_start(self, args: list[str]):
        self._runtime_enabled = True
        if self.cfg["api_key"]:
            self._ensure_vitality_loop_started()
            self._kick_autofill_server_entity_id()
        try:
            fmts.print_suc(f"[皮肤异常拉黑] 已开启（检测恢复 + 活力线程运行），服主请下线")
        except Exception:
            pass

    def _ensure_vitality_loop_started(self):
        if not self.cfg["api_key"]:
            return
        interval = int(self.cfg.get("vitality_interval_sec") or 0)
        if interval <= 0:
            return
        if self._vit_thread and self._vit_thread.is_alive():
            return

        self._vit_stop.clear()
        self._vit_thread = threading.Thread(target=self._vitality_loop, daemon=True)
        self._vit_thread.start()

    def _stop_vitality_loop(self, join_sec: float = 0.0):
        try:
            self._vit_stop.set()
        except Exception:
            return
        t = self._vit_thread
        if t and join_sec and t.is_alive():
            try:
                t.join(join_sec)
            except Exception:
                pass

    def _vitality_loop(self):
        self._vitality_once()
        while not self._vit_stop.is_set():
            interval = int(self.cfg.get("vitality_interval_sec") or 2400)
            if self._vit_stop.wait(timeout=max(1, interval)):
                return
            self._vitality_once()

    def _vitality_once(self):
        try:
            sdkuid = self._sdkuid or self._get_sdkuid_from_sauth()
            if not sdkuid:
                return
            self._call_vitality_refresh(sdkuid)
        except Exception as e:
            try:
                fmts.print_war(f"[皮肤异常拉黑] 活力刷新失败：{e}")
            except Exception:
                pass
            return

    def _get_sdkuid_from_sauth(self) -> str:
        headers = {
            "authorization": self.cfg["api_key"],
            "X-Caller": self._X_CALLER,
            "Cookie": self._COOKIE,
        }
        r = requests.get(self._URL_GET_SAUTH, headers=headers, timeout=self._TIMEOUT_SEC)
        obj = r.json() if r is not None else {}
        if not (isinstance(obj, dict) and obj.get("success") in (True, "true", "True")):
            return ""
        data = obj.get("data") or {}
        sauth = (data.get("sauth") or {}) if isinstance(data, dict) else {}
        sdkuid = str(sauth.get("sdkuid") or "").strip()
        if not sdkuid:
            return ""
        self._sdkuid = sdkuid
        try:
            fmts.print_suc(f"[皮肤异常拉黑] 已获取sdkuid：{sdkuid}")
        except Exception:
            pass
        return sdkuid

    def _call_vitality_refresh(self, sdkuid: str):
        payload = {"sdkuid": sdkuid}
        r = requests.post(self._URL_VITALITY_REFRESH, json=payload, timeout=self._TIMEOUT_SEC)
        obj = r.json() if r is not None else {}
        if not (isinstance(obj, dict) and obj.get("success") in (True, "true", "True")):
            raise RuntimeError(f"vitality refresh failed: {obj!r}")
        try:
            fmts.print_suc(f"[皮肤异常拉黑] 已刷新活力")
        except Exception:
            pass

    def _load_server_id(self):
        if not os.path.exists(self.main_cfg_path):
            try:
                fmts.print_war(f"未找到配置文件：{self.main_cfg_path}")
            except Exception:
                pass
            return None

        try:
            with open(self.main_cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            try:
                fmts.print_war(f"读取 ToolDelta基本配置.json 失败：{e}")
            except Exception:
                pass
            return None

        try:
            block = cfg.get("NeOmega接入点启动模式", {})
            server_id = block.get("服务器号", None)
        except Exception as e:
            try:
                fmts.print_war(f"解析服务器号时出错：{e}")
            except Exception:
                pass
            return None

        if server_id is None:
            try:
                fmts.print_war(f"配置文件中未找到服务器号")
            except Exception:
                pass
            return None

        s = str(server_id).strip()
        if not (s.isdigit() and 4 <= len(s) <= 8):
            try:
                fmts.print_war(f"服务器号{server_id}不是4-8位数字")
            except Exception:
                pass
            return None
        return s

    def _kick_autofill_server_entity_id(self):
        with self._autofill_lock:
            if self._autofill_inflight:
                return
            self._autofill_inflight = True
        threading.Thread(target=self._autofill_server_entity_id_worker, daemon=True).start()

    def _autofill_server_entity_id_worker(self):
        try:
            cur = (self.cfg.get("server_entity_id") or "").strip()
            if cur and cur != "填好API-Key会自动填":
                return

            server_code = self._load_server_id()
            if not server_code:
                return

            eid = self._query_server_entity_id(server_code)
            if not eid:
                return

            self.cn["服务器ID"] = str(eid)
            self._save_config_items(self.cn)
            self.cfg["server_entity_id"] = str(eid)

            try:
                fmts.print_suc(f"[皮肤异常拉黑] 已填写服务器ID：{eid}")
            except Exception:
                pass
        finally:
            with self._autofill_lock:
                self._autofill_inflight = False

    def _query_server_entity_id(self, server_code: str) -> str:
        headers = {
            "Content-Type": "application/json",
            "X-Caller": self._X_CALLER,
            "Cookie": self._COOKIE,
            "authorization": self.cfg["api_key"],
        }
        payload = {"rentalGameCode": server_code, "offset": "0"}
        try:
            resp = requests.post(self._URL_SEARCH_RENTALGAME, json=payload, headers=headers, timeout=self._TIMEOUT_SEC)
        except Exception:
            return ""
        if resp.status_code != 200:
            return ""
        try:
            data = resp.json()
        except Exception:
            return ""
        data_block = data.get("data") or {}
        entities = data_block.get("entities") or []
        if not entities:
            return ""
        ent0 = entities[0] if isinstance(entities[0], dict) else {}
        eid = ent0.get("entity_id", None)
        return "" if eid is None else str(eid)

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "authorization": self.cfg["api_key"],
            "X-Caller": self._X_CALLER,
            "Cookie": self._COOKIE,
        }

    def _post_json(self, url: str, payload: dict):
        r = requests.post(
            url,
            data=json.dumps(payload, ensure_ascii=False),
            headers=self._headers(),
            timeout=self._TIMEOUT_SEC,
        )
        if not (200 <= int(r.status_code) < 300):
            return False, int(r.status_code), {}
        try:
            obj = r.json()
        except Exception:
            obj = {}
        return True, int(r.status_code), obj

    def _query_history_page(self, offset: int, length: int):
        payload = {
            "serverID": str(self.cfg.get("server_entity_id") or ""),
            "length": int(length),
            "offset": int(offset),
            "playerListType": 1,
        }
        ok, _, obj = self._post_json(self._URL_GET_PLAYER_LIST, payload)
        if not ok:
            return []
        if not (isinstance(obj, dict) and obj.get("success") in (True, "true", "True")):
            return []
        data = obj.get("data") or {}
        try:
            if int(data.get("code", -1)) != 0:
                return []
        except Exception:
            return []
        ents = data.get("entities") or []
        return ents if isinstance(ents, list) else []

    def _find_entity_id_in_history(self, name: str) -> str:
        target = name.strip().lower()
        if not target:
            return ""
        seen_first = set()

        for page in range(10):
            ents = self._query_history_page(offset=page * PAGE_LEN_API, length=PAGE_LEN_API)
            if not ents:
                return ""

            first_id = str(_get(ents[0], "entity_id", "_id", default=page * PAGE_LEN_API) or "")
            if first_id in seen_first and page > 0:
                return ""
            seen_first.add(first_id)

            for e in ents:
                if not isinstance(e, dict):
                    continue
                nm = str(_get(e, "name", "user_name", default="") or "").strip()
                if nm and nm.lower() == target:
                    eid = _get(e, "entity_id", "_id", default=None)
                    return "" if eid is None else str(eid)

            if len(ents) < PAGE_LEN_API:
                return ""

        return ""

    def _set_state(self, player_entity_id: str, state: int):
        payload = {"entityID": int(player_entity_id), "PlayerState": int(state)}
        ok, _, obj = self._post_json(self._URL_SET_PLAYER_STATE, payload)
        if not ok:
            return False
        if isinstance(obj, dict) and obj.get("success") in (False, "false", "False"):
            return False
        return True

    def _cooldown_hit(self, name: str) -> bool:
        now = time.time()
        key = name.lower()
        with self._lock:
            last = self._cooldown_ts.get(key, 0.0)
            if now - last < self._COOLDOWN_SEC:
                return True
            self._cooldown_ts[key] = now
            return False

    def _on_playerlist(self, pk: Dict[str, Any]):
        if not self._runtime_enabled:
            return False
        if not self.cfg["api_key"]:
            return False

        sid = (self.cfg.get("server_entity_id") or "").strip()
        if not sid or sid == "填好API-Key会自动填":
            self._kick_autofill_server_entity_id()
            return False

        try:
            action = _get(pk, "ActionType", "actionType", default=None)
            if action is None or int(action) != 0:
                return False
        except Exception:
            return False

        entries = _get(pk, "Entries", "entries", default=[])
        if not isinstance(entries, list) or not entries:
            return False

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            name = str(_get(entry, "Username", "Name", "PlayerName", default="") or "").strip()
            if not name:
                continue
            if self._cooldown_hit(name):
                continue

            skin = _get(entry, "Skin", "skin", default=None)
            skin_dict = skin if isinstance(skin, dict) else entry

            abnormal, why = self._is_abnormal_skin_like_orion1_strict(skin_dict)
            if not abnormal:
                continue

            reason = f"皮肤数据异常(反制1)：{why}"
            threading.Thread(target=self._ban_once, args=(name, reason), daemon=True).start()

        return False

    def _ban_once(self, name: str, reason: str):
        try:
            entity_id = ""
            for wait_sec in (0.0, 0.8, 2.0, 4.0):
                if wait_sec:
                    time.sleep(wait_sec)
                entity_id = self._find_entity_id_in_history(name)
                if entity_id:
                    break

            if not entity_id:
                try:
                    fmts.print_war(f"[皮肤异常拉黑] 拉黑失败：历史进服玩家列表中找不到该玩家：{name}")
                except Exception:
                    pass
                return

            if self._set_state(entity_id, 1):
                try:
                    fmts.print_suc(f"[皮肤异常拉黑] 已拉黑：{name}（{reason}）")
                except Exception:
                    pass
        except Exception:
            pass

    # 皮肤检查

    def _is_abnormal_skin_like_orion1_strict(self, skin: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            SkinImageWidth = int(_get(skin, "SkinImageWidth", default=0) or 0)
            SkinImageHeight = int(_get(skin, "SkinImageHeight", default=0) or 0)
            SkinData = _get(skin, "SkinData", default=b"")

            CapeImageWidth = int(_get(skin, "CapeImageWidth", default=0) or 0)
            CapeImageHeight = int(_get(skin, "CapeImageHeight", default=0) or 0)
            CapeData = _get(skin, "CapeData", default=b"")

            Animations = _get(skin, "Animations", default=[])
            AnimationData = _get(skin, "AnimationData", default=b"")

            if not isinstance(Animations, list):
                Animations = []

            skin_bytes = _b64_to_bytes(SkinData)
            skin_len = len(skin_bytes)

            a0 = Animations[0] if (len(Animations) == 1 and isinstance(Animations[0], dict)) else {}
            a_w = int(_get(a0, "ImageWidth", default=0) or 0)
            a_h = int(_get(a0, "ImageHeight", default=0) or 0)
            a_bytes = _b64_to_bytes(_get(a0, "ImageData", default=b""))
            a_len = len(a_bytes)

            if SkinImageWidth * SkinImageHeight * 4 != skin_len:
                return True, f"SkinData长度不匹配({SkinImageWidth}x{SkinImageHeight}x4 != {skin_len})"

            if SkinImageWidth not in self._SKIN_SIZES or SkinImageHeight not in self._SKIN_SIZES:
                return True, f"皮肤尺寸不允许({SkinImageWidth}x{SkinImageHeight})"

            if not self._ALLOW_CAPE:
                cape_bytes = _b64_to_bytes(CapeData)
                if CapeImageWidth != 0 or CapeImageHeight != 0 or len(cape_bytes) != 0:
                    return True, "披风字段不允许"

            if len(Animations) not in self._ANIM_COUNTS:
                return True, f"动画数量不允许(len={len(Animations)})"

            if a_w * a_h * 4 != a_len:
                return True, f"动画ImageData长度不匹配({a_w}x{a_h}x4 != {a_len})"

            if a_w not in self._ANIM_W or a_h not in self._ANIM_H:
                return True, f"动画尺寸不允许({a_w}x{a_h})"

            if self._REQUIRE_EMPTY_ANIMDATA:
                ad = _b64_to_bytes(AnimationData)
                if len(ad) != 0:
                    return True, "AnimationData非空"

            return False, ""
        except Exception as e:
            return True, f"解析异常({e})"


entry = plugin_entry(SkinAbnormalStandalone)
