from tooldelta import Plugin, plugin_entry, cfg, game_utils
import sqlite3
import os
import re
import random
import operator

# ─────────────────── cfg 兼容处理 ───────────────────
if not hasattr(cfg, "List") and hasattr(cfg, "JsonList"):   # 老版 tooldelta 兼容
    cfg.List = cfg.JsonList


class ScoreboardPlugin(Plugin):
    """聊天栏计分板插件（SQLite 版，cmd 扩展 + 引号/空格容错 + 选择器支持）"""

    name    = "聊天栏计分板"
    author  = "猫七街"
    version = (0, 0, 7)              # ★ 记得同步上调版本号

    # ─────────────────── 内置默认配置 ───────────────────
    CONFIG_DEFAULT = {
        "预设": {
            "签到": [
                "/scoreboard players add {player} sign 1",
                "/say {player} 今天也来打卡啦!"
            ],
            "领钻石": [
                "/give {player} diamond 1",
                "/title {player} title §b§l恭喜获得钻石!"
            ]
        }
    }
    CONFIG_STD = {
        "预设": cfg.AnyKeyValue(cfg.JsonList(str))
    }

    # ─────────────────── 初始化 ───────────────────
    def __init__(self, frame):
        super().__init__(frame)

        # 数据库路径 = 插件数据目录/scoreboard_data.db
        self.make_data_path()
        self.db_path = os.path.join(self.data_path, "scoreboard_data.db")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS boards("
            "name TEXT PRIMARY KEY, display_name TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS scores("
            "player TEXT, board TEXT, value INTEGER, "
            "PRIMARY KEY(player, board), "
            "FOREIGN KEY(board) REFERENCES boards(name) ON DELETE CASCADE)"
        )
        self.conn.commit()

        # 读取/初始化配置文件
        config, _ = cfg.get_plugin_config_and_version(
            self.name, self.CONFIG_STD, self.CONFIG_DEFAULT, self.version
        )
        self.presets: dict[str, list[str]] = config["预设"]

        # 临时变量池
        self.temp_vars: dict[str, int] = {}
        self._cur_player = None

        # 监听聊天
        self.ListenChat(self.on_chat)

    # ─────────────────── SQLite 小工具 ───────────────────
    def _board_exists(self, b) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM boards WHERE name=? LIMIT 1", (b,)
        ).fetchone() is not None

    # ─────────────────── 分数操作 ───────────────────
    def get_score(self, p, b):
        row = self.conn.execute(
            "SELECT value FROM scores WHERE player=? AND board=?", (p, b)
        ).fetchone()
        return row[0] if row else 0

    def set_score(self, p, b, v):
        if not self._board_exists(b):
            raise ValueError(f"计分板 {b} 不存在")
        self.conn.execute(
            "INSERT INTO scores(player, board, value) VALUES(?,?,?) "
            "ON CONFLICT(player, board) DO UPDATE SET value=excluded.value",
            (p, b, v)
        )
        self.conn.commit()

    def add_score(self, p, b, v): self.set_score(p, b, self.get_score(p, b) + v)
    def sub_score(self, p, b, v): self.set_score(p, b, self.get_score(p, b) - v)

    def reset_score(self, p, b):
        self.conn.execute("DELETE FROM scores WHERE player=? AND board=?", (p, b))
        self.conn.commit()

    # ─────────────────── 计分板 CRUD ───────────────────
    def create_board(self, b, d=None):
        if self._board_exists(b):
            raise ValueError("计分板已存在")
        self.conn.execute("INSERT INTO boards(name, display_name) VALUES(?,?)",
                          (b, d or b))
        self.conn.commit()

    def remove_board(self, b):
        if not self._board_exists(b):
            raise ValueError("计分板不存在")
        self.conn.execute("DELETE FROM boards WHERE name=?", (b,))
        self.conn.commit()

    def rename_board(self, old, new):
        if not self._board_exists(old):
            raise ValueError("原计分板不存在")
        if self._board_exists(new):
            raise ValueError("目标计分板已存在")
        self.conn.execute("UPDATE boards SET name=? WHERE name=?", (new, old))
        self.conn.execute("UPDATE scores SET board=? WHERE board=?", (new, old))
        self.conn.commit()

    # ─────────────────── 运算与字符串辅助 ───────────────────
    _ops = {">": operator.gt, "<": operator.lt, ">=": operator.ge,
            "<=": operator.le, "==": operator.eq, "!=": operator.ne}

    _quote_start = ('"', "'", '“', '‘', '«', '「', '『')
    _quote_end   = ('"', "'", '”', '’', '»', '」', '』')

    # ★ 支持选择器解析 (@s/@p/@a) ----------
    def _resolve_players(self, name: str, src):
        name = name.strip()
        if name == "@s" and src:          # 执行者
            return [src.name]
        if name == "@p" and src:          # 最近玩家：简单用执行者代替
            return [src.name]
        if name == "@a":                  # 所有在线玩家
            try:
                return [p.name for p in self.game_ctrl.players]
            except Exception:
                return [src.name] if src else []
        return [name]                     # 普通字符串

    def _single_player(self, name: str, src):
        lst = self._resolve_players(name, src)
        if not lst:
            raise ValueError(f"未找到匹配的玩家: {name}")
        return lst[0]
    # --------------------------------------

    # rand(1,6) → "3"
    def _rand(self, tok):
        m = re.fullmatch(r"rand\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", tok)
        return str(random.randint(min(int(m[1]), int(m[2])),
                                  max(int(m[1]), int(m[2])))) if m else tok

    # 变量替换 + rand 处理
    def _sub(self, tok):
        tok = self._rand(tok)
        return re.sub(
            r"\$\{([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\}",
            lambda m: str(self.temp_vars.get(m[1], 0)),
            tok
        )

    def _intval(self, expr): return int(self._sub(expr))

    # 解析 score(player, board) → int
    def _score_func(self, txt):
        m = re.fullmatch(r"score\(\s*([^,]+)\s*,\s*([^)]+)\s*\)", txt)
        if not m:
            raise ValueError("score() 用法错误")
        return self.get_score(self._single_player(m[1], self._cur_player), m[2])

    def _operand(self, op):
        op = self._sub(op)
        return self._score_func(op) if op.startswith("score(") else int(op)

    def _cond(self, l, o, r):
        return self._ops[o](self._operand(l), self._operand(r))

    # ─────────────────── 条件解析 ───────────────────
    def _parse_cond(self, toks):
        m = re.match(r"^\s*(.+?)\s*(>=|<=|==|!=|>|<)\s*(.+?)\s*$",
                     " ".join(toks))
        if not m:
            raise ValueError("条件格式: A op B")
        return self._cond(m[1], m[2], m[3])

    # ────────── 支持嵌套 { … } ──────────
    def _blk(self, txt: str):
        txt = txt.strip()
        if not txt.startswith("{"):
            raise ValueError("缺少 { }")

        # then 块
        depth = 0
        close = None
        for i, ch in enumerate(txt):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close is None:
            raise ValueError("缺少 }")
        then_blk = self._split_top(txt[1:close].strip())

        # optional else 块
        rest = txt[close + 1:].strip()
        else_blk: list[str] = []
        if rest:
            m = re.match(r"(?i)^else\s*(.*)$", rest, re.S)   # 修正正则标志位置
            if not m:
                raise ValueError("else 语法错误")
            else_txt = m[1].strip()
            if not else_txt.startswith("{"):
                raise ValueError("缺少 { }")
            depth = 0
            close2 = None
            for j, ch in enumerate(else_txt):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        close2 = j
                        break
            if close2 is None:
                raise ValueError("缺少 }")
            if else_txt[close2 + 1:].strip():
                raise ValueError("else 之后有多余内容")
            else_blk = self._split_top(else_txt[1:close2].strip())

        return [then_blk, else_blk]

    # ─────────────────── 帮助 ───────────────────
    def _help(self, pl):
        for line in (
            "§a计分板命令:",
            "scoreboard set|add|sub <玩家> <计分板> <数值>",
            "scoreboard get <玩家> <计分板> [as/-> 变量]",
            "scoreboard reset <玩家> <计分板>",
            "scoreboard batch <玩家1,玩家2,...> <计分板> <数值>",
            "scoreboard cmd <原生MC指令>",
            "scoreboard board create|remove|rename|list ..."
        ):
            pl.show(line)

    # ─────────────────── 聊天入口 ───────────────────
    def on_chat(self, chat):
        msg = chat.msg.strip()

        # 去掉首尾引号
        if msg and msg[0] in self._quote_start:
            msg = msg[1:].lstrip()
        if msg and msg[-1] in self._quote_end:
            msg = msg[:-1].rstrip()

        m = re.match(r"^/scoreboard\s+(.+)", msg, re.I)
        if not m:
            return

        self._cur_player = chat.player
        self.temp_vars.clear()

        for seg in self._split_top(m[1]):
            try:
                self._dispatch(chat.player, seg.strip())
            except Exception as e:
                chat.player.show(f"§c错误: {e}")

        self.temp_vars.clear()
        self._cur_player = None

    # ─────────────────── 顶层分割 ───────────────────
    @staticmethod
    def _split_top(text):
        res, buf, depth = [], "", 0
        for ch in text:
            if ch == "{": depth += 1
            elif ch == "}": depth -= 1
            if ch == ";" and depth == 0:
                res.append(buf)
                buf = ""
            else:
                buf += ch
        if buf:
            res.append(buf)
        return res

    # ─────────────────── 调度 ───────────────────
    def _dispatch(self, player, cmd):
        cmd = cmd.strip()
        if not cmd or cmd == "}":
            return
        t0, *rest = cmd.split()
        kw = t0.lower()

        if kw in ("help", "?", "？"):
            self._help(player)
        elif kw == "cmd":
            self._cmd_exec(player, rest)
        elif kw == "if":
            self._cmd_if(player, rest)
        elif kw == "while":
            self._cmd_while(player, rest)
        elif kw == "var":
            self._cmd_var(player, rest)
        elif kw == "board":
            self._cmd_board(player, rest)
        elif kw == "preset":
            self._cmd_preset(player, rest)
        else:
            self._cmd_score(player, [t0, *rest])

    # ─────────────────── cmd：原生命令 ───────────────────
    def _cmd_exec(self, pl, a):
        if not a:
            raise ValueError("cmd <原生指令>")
        raw = " ".join(a)
        try:
            res = game_utils.sendcmd(raw, waitForResp=True, timeout=3)
        except Exception as e:
            pl.show(f"§c执行指令失败: {raw} → {e}")
            return
        pl.show(f"§a{raw} → Success={res.SuccessCount}" if res
                else f"§a已发送指令: {raw}")

    # ─────────────────── var ───────────────────
    def _cmd_var(self, pl, a):
        if not a:
            raise ValueError("var set|add|get 名称 [值]")
        sub = a[0].lower()
        if sub == "set" and len(a) == 3:
            self.temp_vars[a[1]] = self._intval(a[2])
        elif sub == "add" and len(a) == 3:
            self.temp_vars[a[1]] = int(self.temp_vars.get(a[1], 0)) + self._intval(a[2])
        elif sub == "get" and len(a) == 2:
            pl.show(f"{a[1]} = {self.temp_vars.get(a[1], 0)}")
        else:
            raise ValueError("var 用法错误")

    # ─────────────────── if / while ───────────────────
    def _cmd_if(self, pl, a):
        if "then" not in a:
            raise ValueError("缺少 then")
        idx = a.index("then")
        cond = self._parse_cond(a[:idx])
        then_blk, else_blk = self._blk(" ".join(a[idx + 1:]))
        for c in (then_blk if cond else else_blk):
            self._dispatch(pl, c)

    def _cmd_while(self, pl, a):
        if "do" not in a:
            raise ValueError("缺少 do")
        idx = a.index("do")
        cond_tokens = a[:idx]
        body, _ = self._blk(" ".join(a[idx + 1:]))
        limit = 1000
        while self._parse_cond(cond_tokens):
            for c in body:
                self._dispatch(pl, c)
            limit -= 1
            if limit <= 0:
                raise ValueError("循环次数过多，可能存在死循环")

    # ─────────────────── board ───────────────────
    def _cmd_board(self, pl, a):
        if not a:
            raise ValueError("board create|remove|rename|list")
        sub = a[0].lower()
        if sub == "create" and len(a) >= 2:
            self.create_board(a[1], " ".join(a[2:]) or None)
            pl.show(f"已创建 {a[1]}")
        elif sub == "remove" and len(a) == 2:
            self.remove_board(a[1])
            pl.show(f"已删除 {a[1]}")
        elif sub == "rename" and len(a) == 3:
            self.rename_board(a[1], a[2])
            pl.show(f"{a[1]} → {a[2]}")
        elif sub == "list":
            bs = [row[0] for row in
                  self.conn.execute("SELECT name FROM boards ORDER BY name")]
            pl.show("§e计分板列表:" if bs else "§e暂无计分板")
            for b in bs:
                pl.show(f" - {b}")
        else:
            raise ValueError("board 用法错误")

    # ─────────────────── score / batch ───────────────────
    def _cmd_score(self, pl, t):
        act = t[0].lower()

        # set / add / sub
        if act in ("set", "add", "sub") and len(t) == 4:
            val = self._intval(t[3])
            for name in self._resolve_players(t[1], pl):
                {"set": self.set_score,
                 "add": self.add_score,
                 "sub": self.sub_score}[act](name, t[2], val)
            pl.show(f"{act} {t[1]} {t[2]} = {val}")
            return

        # get [as/-> VAR]
        if act == "get" and len(t) in (3, 5):
            var_name = None
            if len(t) == 5 and t[3] in ("as", "->"):
                var_name = t[4]
            elif len(t) == 5:
                raise ValueError("get 语法错误")
            for name in self._resolve_players(t[1], pl):
                val = self.get_score(name, t[2])
                if var_name:
                    self.temp_vars[var_name] = val
                pl.show(f"{name} 在 {t[2]} 的分数为 {val}")
            return

        # reset
        if act == "reset" and len(t) == 3:
            for name in self._resolve_players(t[1], pl):
                self.reset_score(name, t[2])
            pl.show("已重置完成")
            return

        # batch
        if act == "batch" and len(t) == 4:
            val = self._intval(t[3])
            targets = [n.strip() for n in t[1].split(",") if n.strip()]
            for n in targets:
                self.set_score(n, t[2], val)
            pl.show(f"batch → {t[2]} = {val}")
            return

        raise ValueError("未知操作，输入 /scoreboard help 查看")

    # ─────────────────── preset ───────────────────
    def _cmd_preset(self, pl, a):
        if not a:
            raise ValueError("preset list|run 名称")
        sub = a[0].lower()

        if sub == "list":
            names = list(self.presets)
            pl.show("§e可用预设:" if names else "§e暂无预设")
            for n in names:
                pl.show(f" - {n}")
            return

        if sub == "run" and len(a) == 2:
            name = a[1]
            if name not in self.presets:
                raise ValueError(f"预设 {name} 不存在")
            for raw in self.presets[name]:
                cmd = raw.replace("{player}", pl.name)
                try:
                    res = game_utils.sendcmd(cmd, waitForResp=True, timeout=3)
                except Exception as e:
                    pl.show(f"§c执行指令失败: {cmd} → {e}")
                    continue
                pl.show(f"§a{cmd} → Success={res.SuccessCount}" if res
                        else f"§a已发送指令: {cmd}")
            pl.show(f"§b已执行预设 {name}")
            return

        raise ValueError("preset 用法错误: preset list | preset run 名称")


# ─────────────────── 插件入口 ───────────────────
entry = plugin_entry(ScoreboardPlugin)
