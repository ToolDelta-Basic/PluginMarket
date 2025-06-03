from tooldelta import Plugin, plugin_entry, FrameExit
import sqlite3
import os
import threading
import time

class ScoreboardPlugin(Plugin):
    name = "云计分板API"
    author = "猫七街"
    version = (0, 0, 2)  # 版本号小改动

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self.ListenFrameExit(self.on_frame_exit)
        self.api = None

        # ---------- 1. 构造数据库路径，并确保目录存在 ----------
        db_dir = "data"
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "scoreboard.db")

        # ---------- 2. 建立 SQLite 连接，并开启多线程访问 ----------
        # check_same_thread=False 允许多线程并发访问，但要注意写时锁竞争
        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None  # 关闭事务自动提交，以便我们手动管理
        )
        # 为了让查询返回 dict 形式（更灵活）
        self.conn.row_factory = sqlite3.Row

        # ---------- 3. 针对性能做 PRAGMA 优化 ----------
        cur = self.conn.cursor()
        # 开启 WAL 模式：并发性能更好
        cur.execute("PRAGMA journal_mode = WAL")
        # 降低同步级别：在多数场景下数据丢失风险极低，但写性能显著提升
        cur.execute("PRAGMA synchronous = NORMAL")
        # 强制开启外键约束
        cur.execute("PRAGMA foreign_keys = ON")

        # ---------- 4. 创建表结构（如果不存在） ----------
        # boards 表：存储计分板基本信息
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS boards (
                name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        # scores 表：存储玩家分数，新增 created_at、updated_at
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scores (
                player TEXT NOT NULL,
                board TEXT NOT NULL,
                value INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY(player, board),
                FOREIGN KEY(board) REFERENCES boards(name) ON DELETE CASCADE
            )
            """
        )
        # ---------- 5. 创建索引，以优化常见查询 ----------
        # 当需要按 board 查找所有分数时，加速 WHERE board=?
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_board ON scores(board)")
        # 如果想要获取排行榜（按 value 排序），可以考虑下面这个组合索引
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_scores_board_value ON scores(board, value DESC)"
        )
        self.conn.commit()

        # 定义一个线程锁，确保多线程写入时的安全性
        self._lock = threading.Lock()

    def _execute(self, sql: str, params: tuple = (), commit: bool = False):
        """
        内部统一执行 SQL 的方法，自动加锁并处理异常。
        """
        with self._lock:
            cur = self.conn.cursor()
            try:
                cur.execute(sql, params)
                if commit:
                    self.conn.commit()
                return cur
            except sqlite3.Error as e:
                # 这里可以记录日志，或者重新抛出一个更清晰的错误
                raise RuntimeError(f"数据库操作失败: {e}")

    def _board_exists(self, board: str) -> bool:
        """
        检查计分板是否存在
        """
        row = self._execute(
            "SELECT 1 FROM boards WHERE name = ? LIMIT 1", (board,)
        ).fetchone()
        return row is not None

    def get_score(self, player: str, board: str) -> int:
        """
        获取指定玩家在指定计分板上的分数，如果不存在则返回 0
        """
        row = self._execute(
            "SELECT value FROM scores WHERE player = ? AND board = ?",
            (player, board)
        ).fetchone()
        return row["value"] if row else 0

    def set_score(self, player: str, board: str, value: int) -> None:
        """
        设置指定玩家在指定计分板上的分数
        Raises:
            ValueError: 如果计分板不存在
        """
        if not self._board_exists(board):
            raise ValueError(f"计分板 '{board}' 不存在")
        now_ts = int(time.time())
        # 插入或更新时，更新时间戳 updated_at
        self._execute(
            """
            INSERT INTO scores(player, board, value, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(player, board) DO UPDATE
              SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (player, board, value, now_ts, now_ts),
            commit=True,
        )

    def add_score(self, player: str, board: str, value: int) -> None:
        """
        在指定玩家的计分板上增加分数
        """
        current = self.get_score(player, board)
        self.set_score(player, board, current + value)

    def sub_score(self, player: str, board: str, value: int) -> None:
        """
        在指定玩家的计分板上减少分数
        """
        current = self.get_score(player, board)
        self.set_score(player, board, current - value)

    def reset_score(self, player: str, board: str) -> None:
        """
        重置指定玩家在指定计分板上的分数
        """
        self._execute(
            "DELETE FROM scores WHERE player = ? AND board = ?",
            (player, board),
            commit=True,
        )

    def create_board(self, board: str, display_name: str | None = None) -> None:
        """
        创建新的计分板
        Raises:
            ValueError: 如果计分板已存在
        """
        if self._board_exists(board):
            raise ValueError(f"计分板 '{board}' 已存在")
        now_ts = int(time.time())
        self._execute(
            "INSERT INTO boards(name, display_name, created_at) VALUES(?, ?, ?)",
            (board, display_name or board, now_ts),
            commit=True,
        )

    def remove_board(self, board: str) -> None:
        """
        删除计分板（会级联删除对应的 scores 记录）
        Raises:
            ValueError: 如果计分板不存在
        """
        if not self._board_exists(board):
            raise ValueError(f"计分板 '{board}' 不存在")
        self._execute(
            "DELETE FROM boards WHERE name = ?", (board,), commit=True
        )

    def rename_board(self, old_name: str, new_name: str) -> None:
        """
        重命名计分板
        Raises:
            ValueError: 如果原计分板不存在或目标计分板已存在
        """
        if not self._board_exists(old_name):
            raise ValueError(f"原计分板 '{old_name}' 不存在")
        if self._board_exists(new_name):
            raise ValueError(f"目标计分板 '{new_name}' 已存在")
        self._execute(
            "UPDATE boards SET name = ? WHERE name = ?",
            (new_name, old_name),
            commit=True,
        )
        # 同时更新 scores 表中的 board 字段
        self._execute(
            "UPDATE scores SET board = ? WHERE board = ?",
            (new_name, old_name),
            commit=True,
        )

    def list_boards(self) -> list[str]:
        """
        获取所有计分板列表（按名称排序）
        """
        rows = self._execute("SELECT name FROM boards ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def list_top_scores(self, board: str, limit: int = 10) -> list[tuple[str, int]]:
        """
        获取指定计分板上的排行榜（前 N 名）
        Returns:
            List of (player, value)
        Raises:
            ValueError: 如果计分板不存在
        """
        if not self._board_exists(board):
            raise ValueError(f"计分板 '{board}' 不存在")
        rows = self._execute(
            "SELECT player, value FROM scores WHERE board = ? ORDER BY value DESC LIMIT ?",
            (board, limit)
        ).fetchall()
        return [(row["player"], row["value"]) for row in rows]

    def on_preload(self):
        self.print("云计分板API 已初始化，数据库性能优化完成")

    def on_frame_exit(self, evt: FrameExit):
        if self.conn:
            self.conn.close()
        self.print("云计分板API 已关闭")

# 插件注册
entry = plugin_entry(ScoreboardPlugin, "云计分板API")
