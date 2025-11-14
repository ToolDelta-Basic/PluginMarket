import os, json, threading, time, re
from datetime import datetime, timedelta
from collections import defaultdict

from tooldelta.plugin_load.classic_plugin import Plugin, plugin_entry
from tooldelta import fmts, game_utils
from tooldelta.constants import PacketIDS

try:
    import requests
    HAVE_REQ = True
except Exception:
    import urllib.request, urllib.error
    HAVE_REQ = False

_ig_sessions = defaultdict(dict)

CONFIG_GROUP_VERSION = "0.4.0"
PAGE_LEN_API  = 59
PAGE_LEN_VIEW = 9

def _now_beijing():
    return datetime.utcfromtimestamp(time.time()) + timedelta(hours=8)

def _fmt_bj(dt: datetime):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _read_lines(path: str):
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]

def _write_lines(path: str, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")

def _split_csv_names(val):
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    return []

def _json_escape(s: str):
    return s.replace("\\", "\\\\").replace("\"", "\\\"")

class ServerBlacklistGateway(Plugin):
    name = "服务器黑名单封禁系统"
    author = "丸山彩"
    version = (0, 5, 4)
    description = "通过nv1拉黑式封禁玩家，同时是一个前置插件"

    def __init__(self, frame):
        super().__init__(frame)
        # 数据文件
        self.path_ban_time = os.path.join(self.data_path, "玩家拉黑时长数据.txt")
        self.path_uid_map  = os.path.join(self.data_path, "玩家名-uid-9位服务器赋予id记录.txt")
        self.path_dev_ban  = os.path.join(self.data_path, "设备封锁名单.txt")

        # 配置
        base = os.path.dirname(os.path.dirname(self.data_path))
        self.config_dir  = os.path.join(base, "插件配置文件")
        self.config_path = os.path.join(self.config_dir, f"{self.name}.json")
        self.cn  = self._load_config_items()
        self.cfg = self._cn_items_to_internal(self.cn)

        self._stop_flag   = False
        self._auto_thread = None

        self._chat_sessions = {}

        try:
            self.game_ctrl = self.frame.get_game_control()
        except Exception:
            self.game_ctrl = None

        self.ListenPreload(self._on_preload)
        self.ListenFrameExit(self._on_exit)
        self.ListenPacket(PacketIDS.IDPlayerList, self._on_playerlist_early)
        self.ListenPacket(PacketIDS.IDText, self._on_text_packet)
        self.ListenChat(self._on_player_chat)

    # 前置 API
    
    def ban(self, player_or_name, ban_time: int, reason: str = ""):
        try:
            if hasattr(player_or_name, "name"):
                name = getattr(player_or_name, "name", None) or str(player_or_name)
            else:
                name = str(player_or_name)
            name = name.strip()
            if not name:
                fmts.print_war("[API] ban：空名字，已忽略"); 
                return False

            skip, why = self._should_skip_target(name)
            if skip:
                fmts.print_inf(f"[API] ban：已跳过 {name}（{why}）")
                return False

            if str(ban_time).strip() == "-1":
                expire_dt = datetime(2099, 12, 31, 23, 59, 59)
                is_perm = True
            else:
                secs = int(ban_time)
                if secs <= 0:
                    fmts.print_war(f"[API] ban：无效封禁秒数 {ban_time}"); 
                    return False
                expire_dt = _now_beijing() + timedelta(seconds=secs)
                is_perm = False
            expire_str = _fmt_bj(expire_dt)

            ent = self._find_entity_by_name_quick(name)
            if not ent:
                fmts.print_war(f"[API] ban：服务器历史加入列表中未找到目标玩家：{name}")
                return False
    
            ok, http_status, reason2 = self._set_state(ent["entity_id"], 1)
            if not ok:
                fmts.print_war(f"[API] ban：封禁失败：{name}（HTTP={http_status}；原因={reason2}）")
                return False

            self._record_ban_time(name, ent.get("user_id",""), ent["entity_id"], expire_str)
            self._update_uid_map(ent.get("user_id",""), ent["entity_id"], name)
            fmts.print_suc(f"[API] 封禁成功：{name} 至 {expire_str}" if not is_perm else f"[API] 封禁成功（永久）：{name}")
            return True
        except Exception as e:
            fmts.print_war(f"[API] ban 异常：{e}")
            return False
    
    
    def unban(self, player_or_name):
        try:
            if hasattr(player_or_name, "name"):
                name = getattr(player_or_name, "name", None) or str(player_or_name)
            else:
                name = str(player_or_name)
            name = name.strip()
            if not name:
                fmts.print_war("[API] unban：空名字，已忽略"); 
                return False

            hits = self._search_list(player_list_type=2, name_frag=name, first_page_only=False)
            if not hits:
                fmts.print_inf(f"[API] unban：黑名单中未找到 {name}")
                return False

            ent = None
            for e in hits:
                if str(e.get("name","")).strip().lower() == name.lower():
                    ent = e; break
            if not ent: 
                ent = hits[0]
    
            ok, http_status, reason2 = self._set_state(ent["entity_id"], 0)
            if not ok:
                fmts.print_war(f"[API] unban：解除失败：{name}（HTTP={http_status}；原因={reason2}）")
                return False

            self._remove_from_ban_time_file(ent["entity_id"])
            fmts.print_suc(f"[API] 已解除拉黑：{name}")
            return True
        except Exception as e:
            fmts.print_war(f"[API] unban 异常：{e}")
            return False

    def _on_player_chat(self, chat):
        try:
            player_name = getattr(chat.player, "name", None) or ""
            msg = (chat.msg or "").strip()
            if not player_name or not msg:
                return False

            fake_pkt = {
                "TextType": 1,
                "SourceName": player_name,
                "Message": msg
            }
            try:
                return bool(self._on_text_packet(fake_pkt)) or False
            except Exception:
                return False
        except Exception:
            return False

    def _default_items(self):
        return {
            "服务器ID": "CHANGE_ME",
            "查询接口URL": "https://nv1.nethard.pro/api/open-api/rentalGame/getRentalGamePlayerList",
            "设置状态接口URL": "https://nv1.nethard.pro/api/open-api/rentalGame/setRentalGamePlayerState",
            "你的API-key": "CHANGE_ME",
            "调用方": "gameaccount",
            "Cookie": "locale=en-us",
            "超时秒数": 10,
            "历史加入翻页最大数": 10,

            "控制台": {
                "封禁命令": "blban",
                "解禁命令": "blunban"
            },

            "游戏内": {
                "封禁提示词": ".blban",
                "解禁提示词": ".blunban",
                "OP可使用": True,
                "允许普通玩家使用（逗号分隔）": "",
                "排除的白名单玩家（逗号分隔）": "Steve,Alex"
            },

            "对OP生效": False,
            "默认封禁时长": "30分",

            "联动猎户座": True,
            "猎户座玩家记录路径": "插件数据文件/『Orion System』违规与作弊行为综合反制系统/玩家丨设备号丨xuid丨历史名称丨记录.json",

            "前置XUID记录路径": "插件数据文件/前置-玩家XUID获取/xuids.json",
            "到期检查间隔秒": 1
        }

    def _merge_defaults(self, items: dict):
        d = self._default_items()
        for k, v in d.items():
            if k not in items:
                items[k] = v
            elif isinstance(v, dict):
                for kk, vv in v.items():
                    items[k].setdefault(kk, vv)
        return items

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
            items = self._default_items()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"配置版本": CONFIG_GROUP_VERSION, "配置项": items}, f, ensure_ascii=False, indent=2)
            return items
        if not (isinstance(wrapped, dict) and isinstance(wrapped.get("配置项"), dict)):
            items = self._default_items()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"配置版本": CONFIG_GROUP_VERSION, "配置项": items}, f, ensure_ascii=False, indent=2)
            return items
        items = self._merge_defaults(wrapped["配置项"])
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"配置版本": wrapped.get("配置版本", CONFIG_GROUP_VERSION), "配置项": items}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return items

    def _cn_items_to_internal(self, cn: dict):
        c  = cn.get("控制台", {}) or {}
        gi = cn.get("游戏内", {}) or {}
        hist_pages = int(cn.get("历史加入翻页最大数", 10) or 10)
        if hist_pages < 1: hist_pages = 1

        allowed_normal = _split_csv_names(gi.get("允许普通玩家使用（逗号分隔）", ""))
        exclude_white  = _split_csv_names(gi.get("排除的白名单玩家（逗号分隔）", "Steve,Alex"))

        return {
            "server_id":                 str(cn.get("服务器ID", "")),
            "query_url":                 str(cn.get("查询接口URL", "")),
            "set_state_url":             str(cn.get("设置状态接口URL", "")),
            "api_key":                   str(cn.get("你的API-key", "")),
            "x_caller":                  str(cn.get("调用方", "gameaccount")),
            "cookie":                    str(cn.get("Cookie", "")),
            "timeout_sec":               float(cn.get("超时秒数", 10) or 10),
            "history_max_pages":         hist_pages,

            "console_ban":               str(c.get("封禁命令", "blban")),
            "console_unban":             str(c.get("解禁命令", "blunban")),

            "chat_ban_kw":               str(gi.get("封禁提示词", ".blban")),
            "chat_unban_kw":             str(gi.get("解禁提示词", ".blunban")),
            "chat_op_can_use":           bool(gi.get("OP可使用", True)),
            "chat_allowed_names":        [str(x) for x in allowed_normal],
            "exclude_white_csv":         [str(x) for x in exclude_white],

            "apply_to_op":               bool(cn.get("对OP生效", False)),

            "default_ban_time":          str(cn.get("默认封禁时长", "30分")),
            "link_orion_record":         bool(cn.get("联动猎户座", True)),
            "orion_player_record_path":  str(cn.get("猎户座玩家记录路径", "")),
            "xuid_map_path":             str(cn.get("前置XUID记录路径", "")),
            "expire_check_interval":     float(cn.get("到期检查间隔秒", 1) or 1),
        }

    def _on_preload(self):
        c = self.cfg
        self.frame.add_console_cmd_trigger([c["console_ban"]],   "",  "手动拉黑（交互）",     self._cmd_blban)
        self.frame.add_console_cmd_trigger([c["console_unban"]], "",  "手动解除拉黑（交互）", self._cmd_blunban)

        self._stop_flag = False
        self._auto_thread = threading.Thread(target=self._expire_loop, daemon=True)
        self._auto_thread.start()
        pass
        return False

    def _on_exit(self, ev=None):
        self._stop_flag = True
        self._chat_sessions.clear()
        fmts.print_suc(f"{self.name} 已停止")
        return False

    def _is_op_like_orion(self, player_name: str) -> bool:
        try:
            return bool(game_utils.is_op(player_name))
        except Exception:
            pass
        try:
            gc = self.frame.get_game_control()
        except Exception:
            return False
        for attr in ("isOP", "is_op", "IsOP", "isOp", "isOperator", "is_operator",
                     "isLevelAdmin", "is_admin", "checkOP", "check_op"):
            fn = getattr(gc, attr, None)
            if callable(fn):
                try:
                    if bool(fn(player_name)):
                        return True
                except Exception:
                    pass
        return False

    def _can_player_use_chat_cmd(self, player_name: str) -> bool:
        if self.cfg.get("chat_op_can_use", True) and self._is_op_like_orion(player_name):
            return True
        allow = [x.lower() for x in (self.cfg.get("chat_allowed_names") or [])]
        return player_name.lower() in allow

    def _tell(self, player_name: str, text: str):
        msg = _json_escape(text)
        cmd = f'/tellraw "{_json_escape(player_name)}" {{"rawtext":[{{"text":"{msg}"}}]}}'
        try:
            gc = self.frame.get_game_control()
        except Exception:
            gc = None
        if gc:
            try:
                if hasattr(gc, "sendwocmd"):
                    gc.sendwocmd(cmd); return
            except Exception:
                pass
            try:
                if hasattr(gc, "runcmd"):
                    gc.runcmd(cmd); return
            except Exception:
                pass
        fmts.print_inf(f"[TELLRAW→{player_name}] {text}")

    def _get_online_names(self):
        try:
            gc = self.frame.get_game_control()
        except Exception:
            return []
        try:
            players = gc.players.getAllPlayers()
            names = []
            for p in players:
                try: nm = p.name if hasattr(p, "name") else str(p)
                except Exception: nm = str(p)
                if nm: names.append(nm)
            if names: return names
        except Exception:
            pass
        try:
            alt = getattr(gc, "allplayers", None)
            if isinstance(alt, (list, tuple)):
                return [str(x) for x in alt]
        except Exception:
            pass
        return []

    def _is_online_name(self, name: str) -> bool:
        try:
            gc = self.frame.get_game_control()
            if hasattr(gc, "players") and hasattr(gc.players, "getPlayerByName"):
                if gc.players.getPlayerByName(name) is not None:
                    return True
        except Exception:
            pass
        try:
            names = self._get_online_names()
            return name.lower() in {x.lower() for x in names}
        except Exception:
            return False

    def _should_skip_target(self, name: str):
        wl = [x.lower() for x in (self.cfg.get("exclude_white_csv") or [])]
        if name.lower() in wl:
            return True, "目标在反制白名单中"

        if not self.cfg.get("apply_to_op", False):
            try:
                if self._is_online_name(name) and self._is_op_like_orion(name):
                    return True, "目标为在线OP"
            except Exception:
                pass
    
        return False, ""

    def _cmd_blban(self, args):
        try:
            self._interactive_ban()
        except KeyboardInterrupt:
            fmts.print_inf("已退出服务器黑名单封禁")

    def _cmd_blunban(self, args):
        try:
            self._interactive_unban()
        except KeyboardInterrupt:
            fmts.print_inf("已退出服务器黑名单解封")

    def _paginate(self, items, page: int, per_page: int):
        total = len(items)
        if total <= 0: return (0, 0, 0)
        total_pages = (total - 1) // per_page + 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = min(total, start + per_page)
        return (total_pages, start, end)

    def _parse_ban_input_to_datetime(self, s: str):
        if s is None: return (None, False)
        raw = str(s).strip()
        if raw == "": return (None, False)
        if raw == "-1":
            return (datetime(2099, 12, 31, 23, 59, 59), True)
        if re.fullmatch(r"\d+", raw):
            sec = int(raw)
            if sec <= 0: return (None, False)
            return (_now_beijing() + timedelta(seconds=sec), False)
        pairs = re.findall(r"(\d+)\s*(年|月|日|时|分|秒)", raw)
        if not pairs: return (None, False)
        now = _now_beijing()
        y, M, d = now.year, now.month, now.day
        H, m, s2 = now.hour, now.minute, now.second
        for val, unit in pairs:
            v = int(val)
            if unit == "年":  y = v if v > 0 else y
            elif unit == "月": M = v if v > 0 else M
            elif unit == "日": d = v if v > 0 else d
            elif unit == "时": H = v
            elif unit == "分": m = v
            elif unit == "秒": s2 = v
        try:
            expire_dt = datetime(y, M, d, H, m, s2)
        except Exception:
            return (None, False)
        return (expire_dt, False)

    def _safe_read_json(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _orion_build_indices(self, record: dict):
        name_to_pairs = {}
        xuid_to_devices = {}
        xuid_to_names = {}
        device_to_names = {}
        try:
            for device_id, inner in record.items():
                if not isinstance(inner, dict): continue
                names_for_dev = set()
                for xuid, names in inner.items():
                    if not isinstance(names, list): continue
                    xuid_to_devices.setdefault(xuid, set()).add(device_id)
                    name_set = xuid_to_names.setdefault(xuid, set())
                    for nm in names:
                        if not isinstance(nm, str): continue
                        names_for_dev.add(nm)
                        name_set.add(nm)
                        name_to_pairs.setdefault(nm.lower(), set()).add((xuid, device_id))
                if names_for_dev:
                    device_to_names.setdefault(device_id, set()).update(names_for_dev)
        except Exception:
            pass
        return name_to_pairs, xuid_to_devices, xuid_to_names, device_to_names

    def _read_device_ban_file(self):
        out = {}
        for ln in _read_lines(self.path_dev_ban):
            parts = ln.split("\t")
            if len(parts) < 2: continue
            dev = parts[0].strip()
            exp = parts[1].strip()
            names = set()
            if len(parts) >= 3:
                names = set([x for x in parts[2].split("|") if x])
            try:
                dt = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            out[dev] = {"expire": dt, "names": names}
        return out

    def _write_device_ban_file(self, m: dict):
        rows = []
        for dev, info in m.items():
            exp = _fmt_bj(info["expire"])
            names = "|".join(sorted(info.get("names") or []))
            rows.append(f"{dev}\t{exp}\t{names}")
        _write_lines(self.path_dev_ban, rows)

    def _add_device_bans_for_name_xuids(self, source_name: str, xuids: set, xuid_to_devices: dict, expire_dt: datetime):
        m = self._read_device_ban_file()
        for x in xuids:
            devices = xuid_to_devices.get(x, set()) or set()
            for dev in devices:
                if dev in m:
                    if expire_dt > m[dev]["expire"]:
                        m[dev]["expire"] = expire_dt
                    m[dev].setdefault("names", set()).add(source_name)
                else:
                    m[dev] = {"expire": expire_dt, "names": set([source_name])}
        self._write_device_ban_file(m)

    def _remove_device_bans_for_name(self, name: str):
        m = self._read_device_ban_file()
        changed = False
        to_del = []
        for dev, info in m.items():
            names = info.get("names") or set()
            if name in names:
                names.discard(name)
                if names:
                    m[dev]["names"] = names
                else:
                    to_del.append(dev)
                changed = True
        for dev in to_del:
            del m[dev]
        if changed:
            self._write_device_ban_file(m)

    def _apply_device_bans_to_online(self):
            try:
                if not self.cfg.get("link_orion_record", False):
                    return
    
                orion_path = self.cfg.get("orion_player_record_path") or ""
                if not orion_path or (not os.path.exists(orion_path)):
                    return
    
                record = self._safe_read_json(orion_path)
                name_to_pairs, xuid_to_devices, xuid_to_names, device_to_names = self._orion_build_indices(record)
    
                dev_bans = self._read_device_ban_file()
                if not dev_bans:
                    return
    
                now_bj = _now_beijing()
                banned_devs = {dev for dev, info in dev_bans.items() if info["expire"] > now_bj}
                if not banned_devs:
                    return
    
                online_names = self._get_online_names() or []
                for login_name in online_names:
                    if not login_name:
                        continue
                    skip, _ = self._should_skip_target(login_name)
                    if skip:
                        continue

                    pairs = name_to_pairs.get(login_name.lower(), set())
                    xuids = {x for (x, _dev) in pairs}
                    if not xuids:
                        continue
    
                    devices = set()
                    for x in xuids:
                        devices |= (xuid_to_devices.get(x, set()) or set())
    
                    hit = [dev for dev in devices if dev in banned_devs]
                    if not hit:
                        continue
    
                    expire_dt = max(dev_bans[dev]["expire"] for dev in hit)
                    if (expire_dt - now_bj).total_seconds() <= 1:
                        continue
    
                    ent = self._find_entity_by_name_quick(login_name)
                    if not ent or not ent.get("entity_id"):
                        continue
    
                    ok, http_status, reason = self._set_state(ent["entity_id"], 1)
                    if ok:
                        self._record_ban_time(login_name, ent.get("user_id", ""), ent["entity_id"], _fmt_bj(expire_dt))
                        self._update_uid_map(ent.get("user_id", ""), ent["entity_id"], login_name)
                        fmts.print_suc(f"[设备封锁联动] 已拉黑：{login_name}（命中设备封锁；至 { _fmt_bj(expire_dt) }）")
                    else:
                        fmts.print_war(f"[设备封锁联动] 拉黑失败：{login_name}（HTTP={http_status}；原因={reason}）")
            except Exception as e:
                fmts.print_war(f"[设备封锁联动] 扫描在线玩家异常：{e}")

    def _post_json(self, url, payload, headers, timeout):
        raw = ""; status = -1
        try:
            if HAVE_REQ:
                r = requests.post(url, data=json.dumps(payload, ensure_ascii=False), headers=headers, timeout=timeout)
                raw = r.text; status = r.status_code
            else:
                req = urllib.request.Request(url=url, method="POST")
                for k, v in (headers or {}).items(): req.add_header(k, v)
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                with urllib.request.urlopen(req, data=data, timeout=timeout) as rr:
                    status = int(getattr(rr, "status", 200))
                    raw = rr.read().decode("utf-8", "ignore")
        except Exception as e:
            return False, -1, {"error": str(e)}
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {"raw": raw}
        return (200 <= status < 300), status, obj

    def _headers(self):
        h = {
            "Content-Type": "application/json",
            "authorization": str(self.cfg.get("api_key") or ""),
            "X-Caller": str(self.cfg.get("x_caller") or "gameaccount"),
            "x_caller": str(self.cfg.get("x_caller") or "gameaccount"),
        }
        ck = self.cfg.get("cookie") or ""
        if ck: h["Cookie"] = ck
        return h

    def _query_page(self, player_list_type: int, offset: int, length: int):
        url = self.cfg.get("query_url") or ""
        timeout = float(self.cfg.get("timeout_sec", 10) or 10)
        payload = {"serverID": str(self.cfg.get("server_id") or ""), "length": int(length), "offset": int(offset), "playerListType": int(player_list_type)}
        ok, http_status, obj = self._post_json(url, payload, self._headers(), timeout)
        if not ok: return {}
        if not (obj.get("success") in (True, "true", "True")): return {}
        data = obj.get("data") or {}
        try:
            if int(data.get("code", -1)) != 0: return {}
        except Exception:
            return {}
        return {"entities": data.get("entities") or [], "total": data.get("total", 0)}

    def _search_list(self, player_list_type: int, name_frag=None, first_page_only=False):
        frag = (name_frag or "").strip().lower()
        out = []; seen_first_ids = set()
        page = 0
        cfg_max_pages = int(self.cfg.get("history_max_pages") or 10)
        if cfg_max_pages < 1: cfg_max_pages = 1
        max_pages = cfg_max_pages if player_list_type == 1 else 10**9
        while True:
            if page >= max_pages: break
            offset = page * PAGE_LEN_API
            batch = self._query_page(player_list_type, offset=offset, length=PAGE_LEN_API)
            ents = (batch or {}).get("entities") or []
            if not ents: break
            first_id = str(ents[0].get("entity_id") or ents[0].get("_id") or f"{offset}")
            if first_id in seen_first_ids and page > 0: break
            seen_first_ids.add(first_id)
            for e in ents:
                nm = str(e.get("name") or e.get("user_name") or "").strip()
                if not nm: continue
                if (not frag) or (frag in nm.lower()):
                    out.append({"name": nm, "user_id": str(e.get("user_id") or ""), "entity_id": str(e.get("entity_id") or e.get("_id") or "")})
            if first_page_only: break
            if len(ents) < PAGE_LEN_API: break
            page += 1
        return out

    def _find_entity_by_name_quick(self, name: str):
        target = name.strip().lower()
        page = 0; seen_first_ids=set()
        max_pages = int(self.cfg.get("history_max_pages") or 10)
        if max_pages < 1: max_pages = 1
        while page < max_pages:
            offset = page * PAGE_LEN_API
            batch = self._query_page(player_list_type=1, offset=offset, length=PAGE_LEN_API)
            ents = (batch or {}).get("entities") or []
            if not ents: break
            first_id = str(ents[0].get("entity_id") or ents[0].get("_id") or f"{offset}")
            if first_id in seen_first_ids and page>0: break
            seen_first_ids.add(first_id)
            for e in ents:
                nm = str(e.get("name") or e.get("user_name") or "").strip()
                if nm and nm.lower() == target:
                    return {"name": nm, "user_id": str(e.get("user_id") or ""), "entity_id": str(e.get("entity_id") or e.get("_id") or "")}
            if len(ents) < PAGE_LEN_API: break
            page += 1
        return None

    def _set_state(self, entity_id: str, state: int):
        url = self.cfg.get("set_state_url") or ""
        timeout = float(self.cfg.get("timeout_sec", 10) or 10)
        payload = {"entityID": int(entity_id), "PlayerState": int(state)}
        ok, http_status, obj = self._post_json(url, payload, self._headers(), timeout)
        if not ok:
            return False, http_status, "HTTP失败"
        if obj.get("success") in (True, "true", "True"):
            data = obj.get("data", {})
            try:
                if int(data.get("code", -1)) == 0:
                    return True, http_status, ""
            except Exception:
                pass
        return False, http_status, f"业务失败: {obj}"

    def _query_local_ban_status(self, name:str) -> str:
        try:
            now = _now_beijing()
            for ln in _read_lines(self.path_ban_time):
                parts = ln.split("\t")
                if len(parts) < 4: continue
                nm, _, _, exp = parts[0], parts[1], parts[2], parts[3]
                if nm != name: continue
                try:
                    dt = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                except:
                    continue
                if dt > now:
                    return _fmt_bj(dt)
        except Exception:
            pass
        return ""

    def _record_ban_time(self, name: str, uid: str, entity_id: str, expire_bj: str):
        line = f"{name}\t{uid}\t{entity_id}\t{expire_bj}"
        old = _read_lines(self.path_ban_time)
        keep = [ln for ln in old if (len(ln.split('\t'))<3 or ln.split('\t')[2] != entity_id)]
        keep.append(line)
        _write_lines(self.path_ban_time, keep)

    def _remove_from_ban_time_file(self, entity_id: str):
        lines = _read_lines(self.path_ban_time)
        keep = []
        changed = False
        for ln in lines:
            parts = ln.split("\t")
            if len(parts) >= 3 and parts[2] == str(entity_id):
                changed = True
                continue
            keep.append(ln)
        if changed:
            _write_lines(self.path_ban_time, keep)

    def _update_uid_map(self, uid: str, entity_id: str, name: str):
        uid = str(uid or ""); entity_id = str(entity_id or ""); name = str(name or "")
        rows = _read_lines(self.path_uid_map)
        out = []; found = False
        for ln in rows:
            parts = ln.split("\t")
            if len(parts) < 3: continue
            u, ent, names = parts[0], parts[1], parts[2]
            if u == uid:
                found = True
                name_set = set([x for x in names.split("|") if x])
                name_set.add(name)
                out.append(f"{uid}\t{entity_id or ent}\t{'|'.join(sorted(name_set))}")
            else:
                out.append(ln)
        if not found:
            out.append(f"{uid}\t{entity_id}\t{name}")
        _write_lines(self.path_uid_map, out)

    def _expire_loop(self):
        interval = float(self.cfg.get("expire_check_interval", 1) or 1)
        slice_count = 10
        while not self._stop_flag:
            try:
                now_bj = _now_beijing()
                lines = _read_lines(self.path_ban_time)
                keep = []
                for ln in lines:
                    parts = ln.split("\t")
                    if len(parts) < 4: continue
                    name, uid, entity_id, expire_s = parts[0], parts[1], parts[2], parts[3]
                    try:
                        expire_dt = datetime.strptime(expire_s, "%Y-%m-%d %H:%M:%S")
                    except:
                        keep.append(ln); continue
                    if expire_dt <= now_bj:
                        ok, http_status, reason = self._set_state(entity_id, 0)
                        if ok:
                            fmts.print_suc(f"[拉黑已到期] {name}（uid={uid}，entity_id={entity_id}）")
                        else:
                            fmts.print_war(f"[解除拉黑失败] {name}（HTTP={http_status}；原因={reason}）")
                            keep.append(ln)
                    else:
                        keep.append(ln)
                if keep != lines:
                    _write_lines(self.path_ban_time, keep)

                devmap = self._read_device_ban_file()
                changed = False
                for dev in list(devmap.keys()):
                    if devmap[dev]["expire"] <= now_bj:
                        del devmap[dev]; changed = True
                if changed:
                    self._write_device_ban_file(devmap)

            except Exception as e:
                fmts.print_war(f"[到期线程异常] {e}")

            per = max(0.05, interval / slice_count)
            for _ in range(slice_count):
                if self._stop_flag: break
                time.sleep(per)

    def _interactive_ban(self):
        PAGE = PAGE_LEN_VIEW
        while True:
            fmts.print_inf("—— 服务器黑名单封禁系统 ——")
            fmts.print_inf("[1] 根据在线玩家封禁（可封设备号）")
            fmts.print_inf("[2] 根据历史进服玩家模糊搜索封禁（读xuid文件，不封设备）")
            fmts.print_inf("[3] 根据历史进服玩家模糊搜索封锁设备号（读猎户座数据文件）")
            choice = input(fmts.fmt_info("输入 1/2/3 选择；输入 . 退出：")).strip()
            if choice in (".", "。", ""):
                fmts.print_inf("已退出封禁")
                return

            if choice == "1":
                names = self._get_online_names()
                if not names:
                    fmts.print_war("当前无在线玩家"); return

                def render(page):
                    total_pages, start, end = self._paginate(names, page, PAGE)
                    if total_pages == 0:
                        fmts.print_inf("(空)"); return (page, total_pages, [])
                    fmts.print_inf(f"—— 在线名单 ——  第 {page}/{total_pages} 页")
                    cur = []
                    for i, nm in enumerate(names[start:end], start=1):
                        st = self._query_local_ban_status(nm)
                        fmts.print_inf(f"[{i}] {nm}  -  {'已封禁，至 '+st if st else '未封禁'}")
                        cur.append(nm)
                    fmts.print_inf("提示：输入数字选择；- 上一页；+ 下一页；直接回车退出")
                    return (page, total_pages, cur)

                page = 1
                while True:
                    page, total_pages, cur = render(page)
                    if total_pages == 0: break
                    s = input(fmts.fmt_info("> ")).strip()
                    if s in ("", ".", "。"): return
                    if s == "-" and page > 1: page -= 1; continue
                    if s == "+" and page < total_pages: page += 1; continue
                    try:
                        idx = int(s)
                        if 1 <= idx <= len(cur):
                            name = cur[idx-1]
                        else:
                            fmts.print_war("序号超出范围"); continue
                    except:
                        fmts.print_war("请输入数字序号 / - / + / ."); continue

                    skip, why = self._should_skip_target(name)
                    if skip:
                        fmts.print_war(f"已跳过：{name}（{why}）")
                        return

                    t = input(fmts.fmt_info("请输入封禁时长（-1=永久；正整数=秒；或形如 2025年10月20日18时30分00秒；输入 . 取消）：")).strip()
                    if t in (".", "。", ""): return
                    expire_dt, is_perm = self._parse_ban_input_to_datetime(t)
                    if not expire_dt:
                        fmts.print_war("封禁时长/时间格式无效"); return
                    expire = _fmt_bj(expire_dt)

                    devices = set()
                    try:
                        if self.cfg.get("link_orion_record", False):
                            orion_path = self.cfg.get("orion_player_record_path") or ""
                            record = self._safe_read_json(orion_path) if orion_path and os.path.exists(orion_path) else {}
                            n2p, x2d, x2n, d2n = self._orion_build_indices(record)
                            pairs = n2p.get(name.lower(), set())
                            xuids = {x for (x, _d) in pairs}
                            for x in xuids:
                                devices |= (x2d.get(x, set()) or set())
                            if xuids:
                                self._add_device_bans_for_name_xuids(name, xuids, x2d, expire_dt)
                        else:
                            fmts.print_war("未开启『联动猎户座』，无法封锁设备与联动同设备玩家。")
                    except Exception as e:
                        fmts.print_war(f"[猎户座映射失败] {e}")

                    ent = self._find_entity_by_name_quick(name)
                    if ent:
                        ok, http_status, reason = self._set_state(ent["entity_id"], 1)
                        if ok:
                            self._record_ban_time(name, ent.get("user_id",""), ent["entity_id"], expire)
                            self._update_uid_map(ent.get("user_id",""), ent["entity_id"], name)
                            fmts.print_suc(f"封禁成功：{name} 至 {expire}" if not is_perm else f"封禁成功（永久）：{name}")
                        else:
                            fmts.print_war(f"封禁失败：{name}（HTTP={http_status}；原因={reason}）")
                    else:
                        fmts.print_war(f"服务器历史加入列表中未找到目标玩家：{name}")

                    if devices:
                        try:
                            orion_path = self.cfg.get("orion_player_record_path") or ""
                            record = self._safe_read_json(orion_path) if orion_path and os.path.exists(orion_path) else {}
                            d2n = {}
                            for dev, inner in record.items():
                                if not isinstance(inner, dict): continue
                                s_names = set()
                                for _xuid, names in inner.items():
                                    if isinstance(names, list):
                                        for nm in names:
                                            if isinstance(nm, str) and nm:
                                                s_names.add(nm)
                                if s_names:
                                    d2n[dev] = s_names
                            same_device_names = set()
                            for dev in devices:
                                same_device_names.update(d2n.get(dev, set()))
                            if name in same_device_names:
                                same_device_names.discard(name)
                            count_ok = 0; count_fail = 0
                            for nm in sorted(same_device_names):
                                skip2, why2 = self._should_skip_target(nm)
                                if skip2:
                                    continue
                                ent2 = self._find_entity_by_name_quick(nm)
                                if not ent2:
                                    continue
                                ok2, http_status2, reason2 = self._set_state(ent2["entity_id"], 1)
                                if ok2:
                                    self._record_ban_time(nm, ent2.get("user_id",""), ent2["entity_id"], expire)
                                    self._update_uid_map(ent2.get("user_id",""), ent2["entity_id"], nm)
                                    count_ok += 1
                                else:
                                    count_fail += 1
                            if count_ok or count_fail:
                                fmts.print_inf(f"同设备封锁：成功 {count_ok} 人，失败 {count_fail} 人。")
                        except Exception as e:
                            fmts.print_war(f"[同设备封锁异常] {e}")
                    return

            elif choice == "2":
                xuid_path = self.cfg.get("xuid_map_path") or ""
                if not xuid_path or (not os.path.exists(xuid_path)):
                    fmts.print_war("未找到 XUID 名单文件，请检查“前置XUID记录路径”。")
                    return
                xmap = self._safe_read_json(xuid_path) or {}
                if not isinstance(xmap, dict):
                    fmts.print_war("XUID 名单文件格式错误，应为 {xuid: name} 映射。")
                    return

                frag = input(fmts.fmt_info("请输入名称片段（. 退出）：")).strip()
                if frag in (".", "。", ""): return
                frag_l = frag.lower()

                items = []
                for xuid, nm in xmap.items():
                    try:
                        nm_s = str(nm or "").strip()
                        if nm_s and (frag_l in nm_s.lower()):
                            items.append((nm_s, str(xuid)))
                    except Exception:
                        continue
                seen = set(); dedup = []
                for nm, x in items:
                    if nm.lower() in seen: continue
                    seen.add(nm.lower()); dedup.append((nm, x))
                items = sorted(dedup, key=lambda t: (t[0].lower(), t[1]))
                if not items:
                    fmts.print_war("未在 XUID 名单中找到匹配玩家"); return

                page = 1
                def render(page):
                    total_pages, start, end = self._paginate(items, page, PAGE_LEN_VIEW)
                    if total_pages == 0:
                        fmts.print_inf("(空)"); return (page, total_pages, [])
                    fmts.print_inf(f"—— XUID 名单匹配（名字）：{frag} ——  第 {page}/{total_pages} 页")
                    cur = []
                    for i, (nm, xuid) in enumerate(items[start:end], start=1):
                        st = self._query_local_ban_status(nm)
                        fmts.print_inf(f"[{i}] {nm}  | xuid={xuid}  -  {'已封禁，至 '+st if st else '未封禁'}")
                        cur.append((nm, xuid))
                    fmts.print_inf("提示：输入数字选择；- 上一页；+ 下一页；直接输入新片段重新搜索；. 退出")
                    return (page, total_pages, cur)

                while True:
                    page, total_pages, cur = render(page)
                    if total_pages == 0: break
                    s = input(fmts.fmt_info("> ")).strip()
                    if s in (".", "。"): return
                    if s == "-" and page > 1: page -= 1; continue
                    if s == "+" and page < total_pages: page += 1; continue
                    chosen = None
                    try:
                        idx = int(s)
                        if 1 <= idx <= len(cur):
                            chosen = cur[idx-1]
                        else:
                            fmts.print_war("序号超出范围"); continue
                    except:
                        frag = s; frag_l = frag.lower()
                        xmap = self._safe_read_json(xuid_path) or {}
                        items = []
                        for xuid, nm in xmap.items():
                            try:
                                nm_s = str(nm or "").strip()
                                if nm_s and (frag_l in nm_s.lower()):
                                    items.append((nm_s, str(xuid)))
                            except Exception:
                                continue
                        seen = set(); dedup = []
                        for nm, x in items:
                            if nm.lower() in seen: continue
                            seen.add(nm.lower()); dedup.append((nm, x))
                        items = sorted(dedup, key=lambda t: (t[0].lower(), t[1]))
                        if not items:
                            fmts.print_war("未在 XUID 名单中找到匹配玩家"); return
                        page = 1; continue

                    name, xuid = chosen
                    skip, why = self._should_skip_target(name)
                    if skip:
                        fmts.print_war(f"已跳过：{name}（{why}）")
                        return
                    t = input(fmts.fmt_info("请输入封禁时长（-1=永久；正整数=秒；或形如 2025年10月20日18时30分00秒；输入 . 取消）：")).strip()
                    if t in (".", "。", ""): return
                    expire_dt, is_perm = self._parse_ban_input_to_datetime(t)
                    if not expire_dt:
                        fmts.print_war("封禁时长/时间格式无效"); return
                    expire = _fmt_bj(expire_dt)
                    ent = self._find_entity_by_name_quick(name)
                    if ent:
                        ok, http_status, reason = self._set_state(ent["entity_id"], 1)
                        if ok:
                            self._record_ban_time(name, ent.get("user_id",""), ent["entity_id"], expire)
                            self._update_uid_map(ent.get("user_id",""), ent["entity_id"], name)
                            fmts.print_suc(f"封禁成功：{name}（xuid={xuid}） 至 {expire}" if not is_perm else f"封禁成功（永久）：{name}（xuid={xuid}）")
                        else:
                            fmts.print_war(f"封禁失败：{name}（HTTP={http_status}；原因={reason}）")
                    else:
                        fmts.print_war(f"服务器历史加入列表中未找到目标玩家：{name}")
                    return

            elif choice == "3":
                if not self.cfg.get("link_orion_record", False):
                    fmts.print_war("未开启『联动猎户座』，无法使用模式3。请在配置中启用。")
                    return
                orion_path = self.cfg.get("orion_player_record_path") or ""
                if not orion_path or (not os.path.exists(orion_path)):
                    fmts.print_war("未找到猎户座玩家记录文件，请检查配置路径。")
                    return

                record = self._safe_read_json(orion_path)
                name_to_pairs, xuid_to_devices, xuid_to_names, device_to_names = self._orion_build_indices(record)

                frag = input(fmts.fmt_info("请输入名称片段（. 退出）：")).strip()
                if frag in (".", "。", ""): return
                frag_l = frag.lower()

                candidate_names = sorted([nm for nm in set(name_to_pairs.keys()) if frag_l in nm])
                if candidate_names:
                    def devices_union_for_name(nm):
                        pairs = name_to_pairs.get(nm.lower(), set())
                        xuids = {x for (x, _d) in pairs}
                        devs = set()
                        for x in xuids: devs |= (xuid_to_devices.get(x, set()) or set())
                        return xuids, devs

                    items = []
                    for nm in candidate_names:
                        xuids, devs = devices_union_for_name(nm)
                        items.append((nm, xuids, devs))
                    page = 1

                    def render(page):
                        total_pages, start, end = self._paginate(items, page, PAGE_LEN_VIEW)
                        if total_pages == 0:
                            fmts.print_inf("(空)"); return (page, total_pages, [])
                        fmts.print_inf(f"—— 猎户座匹配（名字）：{frag} ——  第 {page}/{total_pages} 页")
                        cur = []
                        for i, (nm, xuids, devs) in enumerate(items[start:end], start=1):
                            st = self._query_local_ban_status(nm)
                            fmts.print_inf(f"[{i}] {nm}  | xuid数={len(xuids)} | 设备数={len(devs)}  -  {'已封禁，至 '+st if st else '未封禁'}")
                            cur.append((nm, xuids, devs))
                        fmts.print_inf("提示：输入数字选择；- 上一页；+ 下一页；直接输入新片段重新搜索；. 退出")
                        return (page, total_pages, cur)

                    while True:
                        page, total_pages, cur = render(page)
                        if total_pages == 0: break
                        s = input(fmts.fmt_info("> ")).strip()
                        if s in (".", "。"): return
                        if s == "-" and page > 1: page -= 1; continue
                        if s == "+" and page < total_pages: page += 1; continue
                        try:
                            idx = int(s)
                            if 1 <= idx <= len(cur):
                                nm, xuids, devs = cur[idx-1]
                            else:
                                fmts.print_war("序号超出范围"); continue
                        except:
                            frag = s; frag_l = frag.lower()
                            candidate_names = sorted([nn for nn in set(name_to_pairs.keys()) if frag_l in nn])
                            if not candidate_names:
                                fmts.print_war("未找到匹配玩家"); return
                            items = []
                            for nn in candidate_names:
                                xset, dset = devices_union_for_name(nn)
                                items.append((nn, xset, dset))
                            page = 1; continue

                        t = input(fmts.fmt_info("请输入封禁时长（-1=永久；正整数=秒；或形如 2025年10月20日18时30分00秒；输入 . 取消）：")).strip()
                        if t in (".", "。", ""): return
                        expire_dt, is_perm = self._parse_ban_input_to_datetime(t)
                        if not expire_dt:
                            fmts.print_war("封禁时长/时间格式无效"); return
                        self._add_device_bans_for_name_xuids(nm, xuids, xuid_to_devices, expire_dt)
                        self._apply_device_bans_to_online()
                        fmts.print_suc(f"已封锁设备 {len(devs)} 个（按名字 {nm} 的 xuid 聚合，至 { _fmt_bj(expire_dt) }{'（永久）' if is_perm else ''}）。")
                        fmts.print_inf("后续发现这些设备登录时将自动黑名单拉黑")
                        return

                xuid_hit = None
                sample_name = ""
                for xuid, names in sorted(xuid_to_names.items(), key=lambda kv: kv[0]):
                    for nm in names:
                        if frag_l in nm.lower():
                            xuid_hit = xuid; sample_name = nm; break
                    if xuid_hit: break

                if not xuid_hit:
                    fmts.print_war("未在猎户座记录中找到匹配玩家")
                    return

                t = input(fmts.fmt_info(f"找到历史名（xuid={xuid_hit[:8]}…）：例如 {sample_name}；请输入封禁时长（-1/秒数/到期时间；. 取消）：")).strip()
                if t in (".", "。", ""): return
                expire_dt, is_perm = self._parse_ban_input_to_datetime(t)
                if not expire_dt:
                    fmts.print_war("封禁时长/时间格式无效"); return
                self._add_device_bans_for_name_xuids(sample_name, {xuid_hit},
                                                     self._orion_build_indices(self._safe_read_json(self.cfg.get("orion_player_record_path") or ""))[1],
                                                     expire_dt)
                self._apply_device_bans_to_online()
                fmts.print_suc(f"已封锁设备（历史名所在 xuid 聚合），至 { _fmt_bj(expire_dt) }{'（永久）' if is_perm else ''}。")
                fmts.print_inf("后续发现这些设备登录时将自动黑名单拉黑")
                return

            else:
                fmts.print_war("请输入 1 / 2 / 3")

    def _interactive_unban(self):
        PAGE = PAGE_LEN_VIEW
        while True:
            fmts.print_inf("—— 解除封禁 ——")
            fmts.print_inf("[1] 列出黑名单第1页（黑名单列表的前59名玩家）")
            fmts.print_inf("[2] 在黑名单中按名称片段搜索")
            fmts.print_inf("[3] 解封玩家设备号")
            choice = input(fmts.fmt_info("输入 1/2/3 选择；输入 . 退出：")).strip()
            if choice in (".", "。", ""):
                fmts.print_inf("已退出解封交互。")
                return

            if choice == "1":
                ents = self._search_list(player_list_type=2, name_frag=None, first_page_only=True)
                if not ents:
                    fmts.print_war("未在黑名单列表找到任何玩家"); return
                def render(page):
                    total_pages, start, end = self._paginate(ents, page, PAGE)
                    fmts.print_inf(f"—— 黑名单（第1页） ——")
                    cur=[]
                    for i, e in enumerate(ents[start:end], start=1):
                        nm=e.get("name","?"); uid=e.get("user_id","?"); eid=e.get("entity_id","?")
                        fmts.print_inf(f"[{i}] {nm} | uid={uid} | entity_id={eid}")
                        cur.append(e)
                    fmts.print_inf("提示：输入数字选择；直接回车退出")
                    return (page, 1, cur)

                page=1
                while True:
                    _,_,cur = render(page)
                    s = input(fmts.fmt_info("> ")).strip()
                    if s in ("", ".", "。"): return
                    try:
                        idx = int(s)
                        if 1 <= idx <= len(cur):
                            ent = cur[idx-1]; name=ent.get("name","")
                            ok, http_status, reason = self._set_state(ent["entity_id"], 0)
                            if ok:
                                fmts.print_suc(f"解除拉黑成功：{name}（entity_id={ent['entity_id']}）")
                                self._remove_from_ban_time_file(ent["entity_id"])
                                self._remove_device_bans_for_name(name)
                            else:
                                fmts.print_war(f"解除拉黑失败：{name}（HTTP={http_status}；原因={reason}）")
                            return
                        fmts.print_war("序号超出范围")
                    except:
                        fmts.print_war("请输入数字序号 / .")
                return

            elif choice == "2":
                frag = input(fmts.fmt_info("请输入名称片段（. 退出）：")).strip().lower()
                if frag in (".", "。", ""):
                    fmts.print_inf("已退出解封交互。"); return
                ents = self._search_list(player_list_type=2, name_frag=frag, first_page_only=False)
                if not ents:
                    fmts.print_war("未找到匹配玩家"); return

                def render(page):
                    total_pages, start, end = self._paginate(ents, page, PAGE)
                    if total_pages == 0:
                        fmts.print_inf("(空)"); return (page, total_pages, [])
                    fmts.print_inf(f"—— 黑名单（匹配：{frag}）——  第 {page}/{total_pages} 页")
                    cur=[]
                    for i, e in enumerate(ents[start:end], start=1):
                        nm=e.get("name","?"); uid=e.get("user_id","?"); eid=e.get("entity_id","?")
                        fmts.print_inf(f"[{i}] {nm} | uid={uid} | entity_id={eid}")
                        cur.append(e)
                    fmts.print_inf("提示：输入数字选择；- 上一页；+ 下一页；直接输入新片段重新搜索；. 退出")
                    return (page, total_pages, cur)

                page=1
                while True:
                    page, total_pages, cur = render(page)
                    if total_pages == 0: break
                    s = input(fmts.fmt_info("> ")).strip()
                    if s in (".", "。"): return
                    if s == "-" and page > 1: page -= 1; continue
                    if s == "+" and page < total_pages: page += 1; continue
                    try:
                        idx = int(s)
                        if 1 <= idx <= len(cur):
                            ent = cur[idx-1]; name=ent.get("name","")
                            ok, http_status, reason = self._set_state(ent["entity_id"], 0)
                            if ok:
                                fmts.print_suc(f"解除拉黑成功：{name}（entity_id={ent['entity_id']}）")
                                self._remove_from_ban_time_file(ent["entity_id"])
                                self._remove_device_bans_for_name(name)
                            else:
                                fmts.print_war(f"解除拉黑失败：{name}（HTTP={http_status}；原因={reason}）")
                            return
                        fmts.print_war("序号超出范围")
                    except:
                        frag = s.lower()
                        ents = self._search_list(player_list_type=2, name_frag=frag, first_page_only=False)
                        if not ents:
                            fmts.print_war("未找到匹配玩家"); return
                        page = 1; continue

            elif choice == "3":
                devmap = self._read_device_ban_file()
                if not devmap:
                    fmts.print_inf("（当前没有设备封锁记录）"); return

                items = []
                for dev, info in devmap.items():
                    expire = info.get("expire")
                    names  = sorted(list(info.get("names") or []))
                    items.append((dev, expire, names))
                items.sort(key=lambda t: t[1])
    
                def render(page):
                    total_pages, start, end = self._paginate(items, page, PAGE)
                    fmts.print_inf(f"—— 设备封锁记录 —— 第{page}/{total_pages}页")
                    cur = items[start:end]
                    for i, (dev, exp, names) in enumerate(cur, start=1):
                        nm = "|".join(names)[:40]
                        fmts.print_inf(f"[{i}] dev={dev} | expire={_fmt_bj(exp)} | 关联名称={nm}")
                    fmts.print_inf("提示：输入数字删除该条记录；输入 -/+ 翻页；输入 . 退出")
                    return total_pages, cur
    
                page = 1
                while True:
                    total_pages, cur = render(page)
                    s = input(fmts.fmt_info("> ")).strip()
                    if s in (".","。",""): return
                    if s == "-" and page > 1: page -= 1; continue
                    if s == "+" and page < total_pages: page += 1; continue
                    try:
                        idx = int(s)
                        if 1 <= idx <= len(cur):
                            dev = cur[idx-1][0]
                            if dev in devmap:
                                del devmap[dev]
                                self._write_device_ban_file(devmap)
                                fmts.print_suc(f"已删除设备封锁记录：{dev}")
                            else:
                                fmts.print_war("该设备记录已不存在。")
                            return
                        fmts.print_war("序号超出范围")
                    except:
                        fmts.print_war("请输入数字序号 / - / + / .")
            else:
                fmts.print_war("请输入 1 / 2 / 3")

    def _on_text_packet(self, pk):
        try:
            msg = pk.get("Message") or pk.get("message") or ""
            src = pk.get("SourceName") or pk.get("source_name") or pk.get("Sender") or pk.get("sender") or ""
        except Exception:
            return False
        if not msg or not src: 
            return False

        text = str(msg).strip()
        player = str(src).strip()

        ban_kw   = self.cfg.get("chat_ban_kw", ".blban")
        unban_kw = self.cfg.get("chat_unban_kw", ".blunban")

        if text == ban_kw or text == unban_kw:
            if not self._can_player_use_chat_cmd(player):
                self._tell(player, "§c你没有权限使用该功能。")
                return False
            key = ("ban" if text == ban_kw else "unban")
            self._chat_sessions[player] = {"type": key, "state": "menu"}
            if key == "ban":
                self._tell(player, "§b---- 服务器黑名单封禁系统 ----\n选择模式：\n§e1=在线玩家封禁\n§e2=历史进服玩家名称封禁\n§e3=历史进服玩家设备号封禁\n§7输入数字选择；输入 . 退出")
            else:
                self._tell(player, "---- 服务器黑名单解封系统 ----\n§b选择模式：\n§e1=列出黑名单列表的前59名玩家\n§e2=按名称片段搜索黑名单\n§e3=解封玩家设备号\n§7输入数字选择；输入 . 退出")
            return False

        sess = self._chat_sessions.get(player)
        if not sess:
            return False

        if text in (".", "。"):
            self._tell(player, "§a已退出。")
            self._chat_sessions.pop(player, None)
            return False

        if sess["type"] == "ban":
            self._chat_ban_flow(player, text, sess)
        else:
            self._chat_unban_flow(player, text, sess)
        return False

    def _chat_ban_flow(self, player, text, sess):
        st = sess.get("state")

        if st == "menu":
            if text not in ("1","2","3"):
                self._tell(player, "§c请输入 1 / 2 / 3 进行选择，或输入 . 退出")
                return
            sess["mode"] = text
            if text == "1":
                names = self._get_online_names()
                if not names:
                    self._tell(player, "§e当前无在线玩家。")
                    self._chat_sessions.pop(player, None); return
                sess["names"] = names
                sess["page"] = 1
                sess["state"] = "pick_online_name"
                self._chat_render_online_list(player, sess); return
            elif text == "2":
                sess["state"] = "ask_xuid_frag"
                self._tell(player, "§b请输入名称片段：§7输入 . 退出"); return
            else:
                sess["state"] = "ask_orion_frag"
                self._tell(player, "§b请输入名称片段：§7输入 . 退出"); return

        if st == "pick_online_name":
            if text == "-" or text == "上一页":
                if sess["page"] > 1: sess["page"] -= 1
                self._chat_render_online_list(player, sess); return
            if text == "+" or text == "下一页":
                total_pages = self._chat_online_total_pages(sess)
                if sess["page"] < total_pages: sess["page"] += 1
                self._chat_render_online_list(player, sess); return
            try:
                idx = int(text)
                cur = self._chat_online_current_page_items(sess)
                if 1 <= idx <= len(cur):
                    name = cur[idx-1]
                else:
                    self._tell(player, "§c序号超出范围。"); return
            except:
                self._tell(player, "§c请输入数字序号；或 - / + 翻页；或 . 退出"); return

            skip, why = self._should_skip_target(name)
            if skip:
                self._tell(player, f"§e已跳过：{name} §7（{why}）")
                self._chat_sessions.pop(player, None); return

            sess["target_name"] = name
            sess["state"] = "ask_ban_time"
            self._tell(player, "§b请输入封禁时长：§7-1=永久；正整数=秒；或形如 2025年10月20日18时30分00秒\n§7输入 . 取消")
            return

        if st == "ask_xuid_frag":
            frag = text.strip()
            if not frag:
                self._tell(player, "§c片段不能为空。"); return
            xuid_path = self.cfg.get("xuid_map_path") or ""
            if not xuid_path or (not os.path.exists(xuid_path)):
                self._tell(player, "§c未找到 XUID 名单文件，请检查“前置XUID记录路径”。")
                self._chat_sessions.pop(player, None); return
            xmap = self._safe_read_json(xuid_path) or {}
            if not isinstance(xmap, dict):
                self._tell(player, "§cXUID 名单文件格式错误，应为 {xuid: name} 映射。")
                self._chat_sessions.pop(player, None); return
            frag_l = frag.lower()
            items = []
            for xuid, nm in xmap.items():
                try:
                    nm_s = str(nm or "").strip()
                    if nm_s and (frag_l in nm_s.lower()):
                        items.append((nm_s, str(xuid)))
                except Exception:
                    continue
            seen = set(); dedup = []
            for nm, x in items:
                if nm.lower() in seen: continue
                seen.add(nm.lower()); dedup.append((nm, x))
            items = sorted(dedup, key=lambda t: (t[0].lower(), t[1]))
            if not items:
                self._tell(player, "§e未在 XUID 名单中找到匹配玩家。")
                self._chat_sessions.pop(player, None); return
            sess["xuid_items"] = items
            sess["page"] = 1
            sess["state"] = "pick_xuid_name"
            self._chat_render_xuid_items(player, sess, frag); return

        if st == "pick_xuid_name":
            if text in ("-","+"):
                self._chat_turn_page(player, sess, key="xuid_items", per=PAGE_LEN_VIEW, inc=(1 if text=="+" else -1)); return
            try:
                idx = int(text)
                cur = self._chat_current_page_list(sess, key="xuid_items", per=PAGE_LEN_VIEW)
                if 1 <= idx <= len(cur):
                    name, xuid = cur[idx-1]
                else:
                    self._tell(player, "§c序号超出范围。"); return
            except:
                sess["state"] = "ask_xuid_frag"
                self._tell(player, "§b请输入新的名称片段（XUID 文件）：§7输入 . 退出"); return

            skip, why = self._should_skip_target(name)
            if skip:
                self._tell(player, f"§e已跳过：{name} §7（{why}）")
                self._chat_sessions.pop(player, None); return

            sess["target_name"] = name
            sess["target_xuid"] = xuid
            sess["state"] = "ask_ban_time"
            self._tell(player, "§b请输入封禁时长：§7-1=永久；正整数=秒；或形如 2025年10月20日18时30分00秒\n§7输入 . 取消")
            return

        if st == "ask_orion_frag":
            frag = text.strip()
            if not frag:
                self._tell(player, "§c片段不能为空。"); return
            if not self.cfg.get("link_orion_record", False):
                self._tell(player, "§c未开启『联动猎户座』，无法使用模式3。")
                self._chat_sessions.pop(player, None); return
            orion_path = self.cfg.get("orion_player_record_path") or ""
            if not orion_path or (not os.path.exists(orion_path)):
                self._tell(player, "§c未找到猎户座玩家记录文件，请检查配置路径。")
                self._chat_sessions.pop(player, None); return

            record = self._safe_read_json(orion_path)
            name_to_pairs, xuid_to_devices, xuid_to_names, device_to_names = self._orion_build_indices(record)
            frag_l = frag.lower()
            candidate_names = sorted([nm for nm in set(name_to_pairs.keys()) if frag_l in nm])
            if candidate_names:
                items = []
                for nm in candidate_names:
                    pairs = name_to_pairs.get(nm.lower(), set())
                    xuids = {x for (x, _d) in pairs}
                    devs = set()
                    for x in xuids: devs |= (xuid_to_devices.get(x, set()) or set())
                    items.append((nm, xuids, devs))
                sess["orion_items"] = items
                sess["page"] = 1
                sess["state"] = "pick_orion_name"
                self._chat_render_orion_items(player, sess, frag); return

            xuid_hit = None
            sample_name = ""
            for xuid, names in sorted(xuid_to_names.items(), key=lambda kv: kv[0]):
                for nm in names:
                    if frag_l in nm.lower():
                        xuid_hit = xuid; sample_name = nm; break
                if xuid_hit: break
            if not xuid_hit:
                self._tell(player, "§e未在猎户座记录中找到匹配玩家")
                self._chat_sessions.pop(player, None); return
            sess["history_xuid"] = xuid_hit
            sess["history_name"] = sample_name
            sess["state"] = "ask_ban_time_history"
            self._tell(player, f"§b找到历史名：§e{sample_name} §7(xuid={xuid_hit[:8]}…)；请输入封禁时长（-1/秒数/到期时间；. 取消）")
            return

        if st == "pick_orion_name":
            if text in ("-","+"):
                self._chat_turn_page(player, sess, key="orion_items", per=PAGE_LEN_VIEW, inc=(1 if text=="+" else -1)); return
            try:
                idx = int(text)
                cur = self._chat_current_page_list(sess, key="orion_items", per=PAGE_LEN_VIEW)
                if 1 <= idx <= len(cur):
                    nm, xuids, devs = cur[idx-1]
                else:
                    self._tell(player, "§c序号超出范围。"); return
            except:
                sess["state"] = "ask_orion_frag"
                self._tell(player, "§b请输入新的名称片段：§7输入 . 退出"); return

            sess["orion_pick_nm"] = nm
            sess["orion_pick_xuids"] = xuids
            sess["state"] = "ask_ban_time"
            self._tell(player, "§b请输入封禁时长：§7-1=永久；正整数=秒；或形如 2025年10月20日18时30分00秒\n§7输入 . 取消")
            return

        if st in ("ask_ban_time", "ask_ban_time_history"):
            expire_dt, is_perm = self._parse_ban_input_to_datetime(text)
            if not expire_dt:
                self._tell(player, "§c封禁时长/时间格式无效。"); return
            expire = _fmt_bj(expire_dt)

            if sess.get("mode") == "1":
                name = sess.get("target_name","")

                skip, why = self._should_skip_target(name)
                if skip:
                    self._tell(player, f"§e已跳过：{name} §7（{why}）")
                    self._chat_sessions.pop(player, None); return

                devices = set()
                try:
                    if self.cfg.get("link_orion_record", False):
                        orion_path = self.cfg.get("orion_player_record_path") or ""
                        record = self._safe_read_json(orion_path) if orion_path and os.path.exists(orion_path) else {}
                        n2p, x2d, x2n, d2n = self._orion_build_indices(record)
                        pairs = n2p.get(name.lower(), set())
                        xuids = {x for (x, _d) in pairs}
                        for x in xuids:
                            devices |= (x2d.get(x, set()) or set())
                        if xuids:
                            self._add_device_bans_for_name_xuids(name, xuids, x2d, expire_dt)
                except Exception:
                    pass

                ent = self._find_entity_by_name_quick(name)
                if ent:
                    ok, http_status, reason = self._set_state(ent["entity_id"], 1)
                    if ok:
                        self._record_ban_time(name, ent.get("user_id",""), ent["entity_id"], expire)
                        self._update_uid_map(ent.get("user_id",""), ent["entity_id"], name)
                        self._tell(player, f"§a封禁成功：§e{name} §7至 §b{expire}" + (" §7（永久）" if is_perm else ""))
                    else:
                        self._tell(player, f"§c封禁失败：§7{name} §8(HTTP={http_status}; 原因={reason})")
                else:
                    self._tell(player, f"§e未能在历史加入列表找到该玩家的可操作条目：§7{name}")

                if devices:
                    try:
                        orion_path = self.cfg.get("orion_player_record_path") or ""
                        record = self._safe_read_json(orion_path) if orion_path and os.path.exists(orion_path) else {}
                        d2n = {}
                        for dev, inner in record.items():
                            if not isinstance(inner, dict): continue
                            s_names = set()
                            for _xuid, names in inner.items():
                                if isinstance(names, list):
                                    for nm in names:
                                        if isinstance(nm, str) and nm:
                                            s_names.add(nm)
                            if s_names:
                                d2n[dev] = s_names
                        same_device_names = set()
                        for dev in devices:
                            same_device_names.update(d2n.get(dev, set()))
                        if name in same_device_names:
                            same_device_names.discard(name)
                        count_ok = 0; count_fail = 0
                        for nm in sorted(same_device_names):
                            skip2, why2 = self._should_skip_target(nm)
                            if skip2:
                                continue
                            ent2 = self._find_entity_by_name_quick(nm)
                            if not ent2:
                                continue
                            ok2, http_status2, reason2 = self._set_state(ent2["entity_id"], 1)
                            if ok2:
                                self._record_ban_time(nm, ent2.get("user_id",""), ent2["entity_id"], expire)
                                self._update_uid_map(ent2.get("user_id",""), ent2["entity_id"], nm)
                                count_ok += 1
                            else:
                                count_fail += 1
                        if count_ok or count_fail:
                            self._tell(player, f"§7同设备封锁：成功 §a{count_ok} §7人，失败 §c{count_fail} §7人。")
                    except Exception:
                        pass

                self._chat_sessions.pop(player, None); return

            elif sess.get("mode") == "2":
                name = sess.get("target_name","")
                xuid = sess.get("target_xuid","")

                skip, why = self._should_skip_target(name)
                if skip:
                    self._tell(player, f"§e已跳过：{name} §7（{why}）")
                    self._chat_sessions.pop(player, None); return

                ent = self._find_entity_by_name_quick(name)
                if ent:
                    ok, http_status, reason = self._set_state(ent["entity_id"], 1)
                    if ok:
                        self._record_ban_time(name, ent.get("user_id",""), ent["entity_id"], expire)
                        self._update_uid_map(ent.get("user_id",""), ent["entity_id"], name)
                        self._tell(player, f"§a封禁成功：§e{name} §7(xuid={xuid}) 至 §b{expire}" + (" §7（永久）" if is_perm else ""))
                    else:
                        self._tell(player, f"§c封禁失败：§7{name} §8(HTTP={http_status}; 原因={reason})")
                else:
                    self._tell(player, f"§e服务器历史加入列表中未找到目标玩家：§7{name}")
                self._chat_sessions.pop(player, None); return

            else:
                if st == "ask_ban_time_history":
                    xuid_hit = sess.get("history_xuid","")
                    sample_name = sess.get("history_name","")
                    record = self._safe_read_json(self.cfg.get("orion_player_record_path") or "")
                    x2d = self._orion_build_indices(record)[1]
                    devs = x2d.get(xuid_hit, set()) or set()
                    self._add_device_bans_for_name_xuids(sample_name, {xuid_hit}, x2d, expire_dt)
                    self._apply_device_bans_to_online()
                    self._tell(player, f"§a已封锁设备 §e{len(devs)} §7个（至 §b{expire}§7）。" + (" §7（永久）" if is_perm else ""))
                    self._tell(player, "§7后续发现这些设备登录时将自动黑名单拉黑")
                    self._chat_sessions.pop(player, None); return
                else:
                    nm = sess.get("orion_pick_nm","")
                    xuids = sess.get("orion_pick_xuids", set())
                    record = self._safe_read_json(self.cfg.get("orion_player_record_path") or "")
                    x2d = self._orion_build_indices(record)[1]
                    devs = set()
                    for x in xuids:
                        devs |= (x2d.get(x, set()) or set())
                    self._add_device_bans_for_name_xuids(nm, xuids, x2d, expire_dt)
                    self._apply_device_bans_to_online()
                    self._tell(player, f"§a已封锁设备 §e{len(devs)} §7个（按名字 §e{nm} §7的 xuid 聚合，至 §b{expire}§7）。" + (" §7（永久）" if is_perm else ""))
                    self._tell(player, "§7后续发现这些设备登录时将自动黑名单拉黑")
                    self._chat_sessions.pop(player, None); return

    def _chat_unban_flow(self, player, text, sess):
        st = sess.get("state")
        if st == "menu":
            if text not in ("1","2","3"):
                self._tell(player, "§c请输入 1 / 2 / 3 进行选择，或输入 . 退出")
                return
            if text == "1":
                ents = self._search_list(player_list_type=2, name_frag=None, first_page_only=True)
                if not ents:
                    self._tell(player, "§e未在黑名单列表找到任何玩家。")
                    self._chat_sessions.pop(player, None); return
                sess["ents"] = ents
                sess["page"] = 1
                sess["state"] = "pick_unban_first"
                self._chat_render_unban_page(player, sess); return
            elif text == "2":
                sess["state"] = "ask_unban_frag"
                self._tell(player, "§b请输入名称片段（搜索黑名单）：§7输入 . 退出"); return
            else:
                m = self._read_device_ban_file()
                if not m:
                    self._tell(player, "§e当前没有设备封锁记录。"); self._chat_sessions.pop(player, None); return
                items = []
                for dev, info in m.items():
                    items.append((dev, info.get("expire"), sorted(list(info.get("names") or []))))
                items.sort(key=lambda t: t[1])
                sess["dev_items"] = items
                sess["page"] = 1
                sess["state"] = "pick_dev_unban"
                self._chat_render_dev_items(player, sess); return

        if st == "pick_unban_first":
            if text in ("-","+"):
                self._chat_turn_page(player, sess, key="ents", per=PAGE_LEN_VIEW, inc=(1 if text=="+" else -1)); return
            if text in (".","。"):
                self._chat_sessions.pop(player, None); return
            try:
                idx = int(text)
                cur = self._chat_current_page_list(sess, key="ents", per=PAGE_LEN_VIEW)
                if 1 <= idx <= len(cur):
                    ent = cur[idx-1]; name=ent.get("name","")
                    ok, http_status, reason = self._set_state(ent["entity_id"], 0)
                    if ok:
                        self._tell(player, f"§a解除拉黑成功：§e{name} §7(entity_id={ent['entity_id']})")
                        self._remove_from_ban_time_file(ent["entity_id"])
                        self._remove_device_bans_for_name(name)
                    else:
                        self._tell(player, f"§c解除拉黑失败：§7{name} §8(HTTP={http_status}; 原因={reason})")
                else:
                    self._tell(player, "§c序号超出范围。")
            except:
                self._tell(player, "§c请输入数字序号；或 - / + 翻页；或 . 退出")
            self._chat_sessions.pop(player, None); return

        if st == "ask_unban_frag":
            frag = text.strip().lower()
            if frag in ("",".","。"):
                self._chat_sessions.pop(player, None); return
            ents = self._search_list(player_list_type=2, name_frag=frag, first_page_only=False)
            if not ents:
                self._tell(player, "§e未找到匹配玩家。")
                self._chat_sessions.pop(player, None); return
            sess["ents"] = ents
            sess["page"] = 1
            sess["state"] = "pick_unban_search"
            self._chat_render_unban_page(player, sess, frag=frag); return

        if st == "pick_unban_search":
            if text in ("-","+"):
                self._chat_turn_page(player, sess, key="ents", per=PAGE_LEN_VIEW, inc=(1 if text=="+" else -1)); return
            if text in (".","。"):
                self._chat_sessions.pop(player, None); return
            try:
                idx = int(text)
                cur = self._chat_current_page_list(sess, key="ents", per=PAGE_LEN_VIEW)
                if 1 <= idx <= len(cur):
                    ent = cur[idx-1]; name=ent.get("name","")
                    ok, http_status, reason = self._set_state(ent["entity_id"], 0)
                    if ok:
                        self._tell(player, f"§a解除拉黑成功：§e{name} §7(entity_id={ent['entity_id']})")
                        self._remove_from_ban_time_file(ent["entity_id"])
                        self._remove_device_bans_for_name(name)
                    else:
                        self._tell(player, f"§c解除拉黑失败：§7{name} §8(HTTP={http_status}; 原因={reason})")
                else:
                    self._tell(player, "§c序号超出范围。")
            except:
                self._tell(player, "§c请输入数字序号；或 - / + 翻页；或 . 退出")
            self._chat_sessions.pop(player, None); return

        if st == "pick_dev_unban":
            if text in ("-","+"):
                self._chat_turn_page(player, sess, key="dev_items", per=PAGE_LEN_VIEW, inc=(1 if text=="+" else -1)); return
            if text in (".","。"):
                self._chat_sessions.pop(player, None); return
            try:
                idx = int(text)
                cur = self._chat_current_page_list(sess, key="dev_items", per=PAGE_LEN_VIEW)
                if 1 <= idx <= len(cur):
                    dev = cur[idx-1][0]
                    m = self._read_device_ban_file()
                    if dev in m:
                        del m[dev]
                        self._write_device_ban_file(m)
                        self._tell(player, f"§a已删除设备封锁记录：§e{dev}")
                    else:
                        self._tell(player, "§e该设备记录已不存在。")
                else:
                    self._tell(player, "§c序号超出范围。")
            except:
                self._tell(player, "§c请输入数字序号；或 - / + 翻页；或 . 退出")
            self._chat_sessions.pop(player, None); return

    def _chat_online_total_pages(self, sess):
        names = sess.get("names") or []
        total_pages, _, _ = self._paginate(names, 1, PAGE_LEN_VIEW)
        return total_pages

    def _chat_online_current_page_items(self, sess):
        names = sess.get("names") or []
        page = sess.get("page", 1)
        total_pages, start, end = self._paginate(names, page, PAGE_LEN_VIEW)
        return names[start:end]

    def _chat_render_online_list(self, player, sess):
        page = sess.get("page", 1)
        names = sess.get("names") or []
        total_pages, start, end = self._paginate(names, page, PAGE_LEN_VIEW)
        if total_pages == 0:
            self._tell(player, "§7(空)")
            return
        lines = [f"§b—— 在线名单 —— §7第 §e{page}§7/§e{total_pages} §7页"]
        cur = names[start:end]
        for i, nm in enumerate(cur, start=1):
            st = self._query_local_ban_status(nm)
            lines.append(f"§7[{i}] §f{nm} §8- " + (f"§c已封禁，至 §7{st}" if st else "§a未封禁"))
        lines.append("§7提示：输入数字选择；输入 §e- §7上一页；输入 §e+ §7下一页；输入 §e. §7退出")
        self._tell(player, "\n".join(lines))

    def _chat_current_page_list(self, sess, key, per):
        items = sess.get(key) or []
        page = sess.get("page", 1)
        total_pages, start, end = self._paginate(items, page, per)
        return items[start:end]

    def _chat_turn_page(self, player, sess, key, per, inc):
        items = sess.get(key) or []
        page = sess.get("page", 1) + inc
        total_pages, _, _ = self._paginate(items, page, per)
        if total_pages == 0:
            self._tell(player, "§7(空)")
            return
        page = max(1, min(page, total_pages))
        sess["page"] = page
        if key == "xuid_items":
            self._chat_render_xuid_items(player, sess, "")
        elif key == "orion_items":
            self._chat_render_orion_items(player, sess, "")
        elif key == "dev_items":
            self._chat_render_dev_items(player, sess)
        else:
            self._chat_render_unban_page(player, sess)

    def _chat_render_xuid_items(self, player, sess, frag):
        items = sess.get("xuid_items") or []
        page = sess.get("page", 1)
        total_pages, start, end = self._paginate(items, page, PAGE_LEN_VIEW)
        if total_pages == 0:
            self._tell(player, "§7(空)"); return
        lines = [f"§b—— XUID 名单匹配（名字） —— §7第 §e{page}§7/§e{total_pages} §7页"]
        cur = items[start:end]
        for i, (nm, xuid) in enumerate(cur, start=1):
            st = self._query_local_ban_status(nm)
            lines.append(f"§7[{i}] §f{nm} §8| xuid=§7{xuid} §8- " + (f"§c已封禁，至 §7{st}" if st else "§a未封禁"))
        lines.append("§7提示：输入数字选择；输入 §e- §7上一页；输入 §e+ §7下一页；输入 §e. §7退出；或直接输入新片段重新搜索")
        self._tell(player, "\n".join(lines))

    def _chat_render_orion_items(self, player, sess, frag):
        items = sess.get("orion_items") or []
        page = sess.get("page", 1)
        total_pages, start, end = self._paginate(items, page, PAGE_LEN_VIEW)
        if total_pages == 0:
            self._tell(player, "§7(空)"); return
        lines = [f"§b—— 猎户座匹配（名字） —— §7第 §e{page}§7/§e{total_pages} §7页"]
        cur = items[start:end]
        for i, (nm, xuids, devs) in enumerate(cur, start=1):
            st = self._query_local_ban_status(nm)
            lines.append(f"§7[{i}] §f{nm} §8| xuid数=§7{len(xuids)} §8| 设备数=§7{len(devs)} §8- " + (f"§c已封禁，至 §7{st}" if st else "§a未封禁"))
        lines.append("§7提示：输入数字选择；输入 §e- §7上一页；输入 §e+ §7下一页；输入 §e. §7退出；或直接输入新片段重新搜索")
        self._tell(player, "\n".join(lines))

    def _chat_render_dev_items(self, player, sess):
        page = sess.get("page", 1)
        items = sess.get("dev_items") or []
        total_pages, start, end = self._paginate(items, page, PAGE_LEN_VIEW)
        if total_pages == 0:
            self._tell(player, "§7(空)")
            return
        lines = [f"§b—— 设备封锁记录 —— §7第 §e{page}§7/§e{total_pages} §7页"]
        cur = items[start:end]
        for i, (dev, exp, names) in enumerate(cur, start=1):
            nm = "|".join(names)[:40]
            lines.append(f"§7[{i}] §fdev={dev} §8| §7到期=§f{_fmt_bj(exp)} §8| §7关联名=§f{nm}")
        lines.append("§7提示：输入数字删除该条设备记录；输入 §e- §7上一页；输入 §e+ §7下一页；输入 §e. §7退出")
        self._tell(player, "\n".join(lines))

    def _chat_render_unban_page(self, player, sess, frag=""):
        ents = sess.get("ents") or []
        page = sess.get("page", 1)
        total_pages, start, end = self._paginate(ents, page, PAGE_LEN_VIEW)
        if total_pages == 0:
            self._tell(player, "§7(空)"); return
        title = "黑名单（第1页）" if not frag else f"黑名单（匹配：{frag}）"
        lines = [f"§b—— {title} —— §7第 §e{page}§7/§e{total_pages} §7页"]
        cur = ents[start:end]
        for i, e in enumerate(cur, start=1):
            nm=e.get("name","?"); uid=e.get("user_id","?"); eid=e.get("entity_id","?")
            lines.append(f"§7[{i}] §f{nm} §8| uid=§7{uid} §8| entity_id=§7{eid}")
        if not frag:
            lines.append("§7提示：输入数字选择；输入 §e- §7上一页；输入 §e+ §7下一页；输入 §e. §7退出")
        else:
            lines.append("§7提示：输入数字选择；输入 §e- §7上一页；输入 §e+ §7下一页；输入 §e. §7退出；或直接输入新片段重新搜索")
        self._tell(player, "\n".join(lines))

    def _on_playerlist_early(self, pk):
        try:
            if not self.cfg.get("link_orion_record", False):
                return False
            action = pk.get("ActionType", None)
            is_join = (action == 0) or (action is False) or (str(action).lower() == "add")
            if not is_join:
                return False
            entries = pk.get("Entries", []) or []
            if not entries:
                return False

            orion_path = self.cfg.get("orion_player_record_path") or ""
            if not orion_path or (not os.path.exists(orion_path)):
                return False

            record = self._safe_read_json(orion_path)
            name_to_pairs, xuid_to_devices, xuid_to_names, device_to_names = self._orion_build_indices(record)

            dev_bans = self._read_device_ban_file()
            if not dev_bans:
                return False
            now_bj = _now_beijing()
            banned_devs = {dev for dev, info in dev_bans.items() if info["expire"] > now_bj}

            for entry in entries:
                login_name = entry.get("Username") or entry.get("Name") or entry.get("PlayerName") or ""
                if not login_name:
                    continue
                skip, _ = self._should_skip_target(login_name)
                if skip:
                    continue

                pairs = name_to_pairs.get(login_name.lower(), set())
                xuids = {x for (x, _d) in pairs}
                if not xuids:
                    continue
                devices = set()
                for x in xuids:
                    devices |= (xuid_to_devices.get(x, set()) or set())
                hit = [dev for dev in devices if dev in banned_devs]
                if not hit:
                    continue
                expire_dt = max(dev_bans[dev]["expire"] for dev in hit)
                if (expire_dt - now_bj).total_seconds() <= 1:
                    continue
                ent = self._find_entity_by_name_quick(login_name)
                if not ent or not ent.get("entity_id"):
                    continue
                ok, http_status, reason = self._set_state(ent["entity_id"], 1)
                if ok:
                    self._record_ban_time(login_name, ent.get("user_id",""), ent["entity_id"], _fmt_bj(expire_dt))
                    self._update_uid_map(ent.get("user_id",""), ent["entity_id"], login_name)
                    fmts.print_suc(f"[设备封锁] {login_name}（发现设备 {len(hit)} 个，至 { _fmt_bj(expire_dt) }）")
                else:
                    fmts.print_war(f"[设备封锁失败] {login_name}（HTTP={http_status}；原因={reason}）")
        except Exception as e:
            fmts.print_war(f"[设备封锁异常] {e}")
        return False

entry = plugin_entry(ServerBlacklistGateway, "服务器黑名单封禁系统")
