"""玩家坐标追踪与分布图模块，通过适配器通用接口获取坐标。"""
import asyncio
import base64
import io
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List

from ...core.module import Module
from ...core.decorators import command

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_TIME_UNITS = {
    "毫秒": 1,
    "秒": 1000,
    "分钟": 60000,
}

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class PlayerPositionService:
    """玩家位置持久化服务，支持可配置的快照数量和时间粒度。"""

    def __init__(
        self,
        data_path: str,
        max_snapshots: int = 100,
        time_unit: str = "秒",
    ):
        self._file = os.path.join(data_path, "positions.json")
        self._snapshots: List[dict] = []
        self._max_snapshots = max_snapshots
        self._unit_ms = _TIME_UNITS.get(time_unit, 1000)
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        """从文件加载历史快照。"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._snapshots = json.load(f)
                if not isinstance(self._snapshots, list):
                    self._snapshots = []
                self._snapshots = self._snapshots[-self._max_snapshots:]
            except Exception:
                self._snapshots = []

    def _save(self):
        """保存快照到文件。"""
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._snapshots, f, ensure_ascii=False, indent=2)

    def _truncate_time(self, ts: float) -> int:
        """根据粒度截断时间戳。"""
        if self._unit_ms == 1:
            return int(ts * 1000)
        return int(ts * 1000 / self._unit_ms) * self._unit_ms

    async def update_positions(self, positions: Dict[str, dict]):
        """添加新的坐标快照（异步安全），并持久化。"""
        async with self._lock:
            now = time.time()
            truncated = self._truncate_time(now)
            if (
                self._snapshots
                and self._snapshots[-1].get("timestamp") == truncated
            ):
                self._snapshots[-1]["players"] = positions
            else:
                snapshot = {
                    "timestamp": truncated,
                    "players": positions,
                }
                self._snapshots.append(snapshot)
                while len(self._snapshots) > self._max_snapshots:
                    self._snapshots.pop(0)
            self._save()

    async def get_current_positions(self) -> Dict[str, dict]:
        """获取最新的玩家坐标快照。"""
        async with self._lock:
            if self._snapshots:
                return self._snapshots[-1].get("players", {})
            return {}

    async def get_recent_snapshots(self, count: int = 5) -> List[dict]:
        """获取最近 count 个坐标快照（按时间正序）。"""
        async with self._lock:
            return self._snapshots[-count:]


class PlayerTrackerModule(Module):
    """玩家坐标追踪模块，定时查询坐标，持久化并生成分布图。"""

    name = "player_tracker"
    tier = 100  # TIER_DAEMON  # daemon: 系统守护
    version = (1, 0, 0)
    required_services = ["config", "message", "adapter"]

    default_config = {
        "玩家分布图": {
            "最大快照数": 100,
            "存储粒度": "秒",
            "查询间隔秒": 2.0,
        }
    }

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._service: Optional[PlayerPositionService] = None
        self._lock = asyncio.Lock()
        self._positions: Dict[str, Dict[str, float]] = {}
        self._task: Optional[asyncio.Task] = None
        self._interval = 2.0
        self._query_timeout = 3.0

    async def on_init(self):
        """框架已自动注册 default_config 配置节，模块只初始化服务、命令和后台轮询。"""

        async def _dbg_positions():
            """调试端点。"""
            return str({"tracked": len(self._positions)})

        try:
            debug = self.services.get("debug")
            await debug.register_module(
                self.name, {"positions": _dbg_positions}
            )
        except KeyError:
            pass

        cfg = self.config.get("玩家分布图")
        max_snapshots = cfg.get("最大快照数", 100)
        time_unit = cfg.get("存储粒度", "秒")
        self._interval = cfg.get("查询间隔秒", 2.0)

        module_dir = self.data_dir
        self._service = PlayerPositionService(
            module_dir,
            max_snapshots=max_snapshots,
            time_unit=time_unit,
        )
        self._root_services.register("player_positions", self._service)

        self.register_command(
            ".分布图", self._cmd_map,
            description="查看玩家坐标分布图",
        )
        self.register_command(
            ".位置", self._cmd_pos,
            description="查看指定玩家的当前坐标",
            argument_hint="<玩家名>",
            op_only=True,
        )

        self._task = asyncio.ensure_future(self._polling_loop())

    async def on_stop(self):
        """停止后台轮询。"""
        if self._task:
            self._task.cancel()

    async def _polling_loop(self):
        """后台循环：通过适配器通用接口获取原始数据，自行解析坐标。"""
        while True:
            try:
                await asyncio.sleep(self._interval)
                resp = self.adapter.send_game_command_full(
                    "/querytarget @a", timeout=self._query_timeout
                )
                if resp is None or resp.get("success_count", 0) == 0:
                    continue

                positions = self._parse_positions_from_resp(resp)
                if positions:
                    async with self._lock:
                        self._positions = positions
                    await self._service.update_positions(positions)
            except asyncio.CancelledError:
                break
            except ValueError:
                _logger.warning("游戏连接未就绪，等待重试")
                await asyncio.sleep(5)
            except Exception as e:
                _logger.error("轮询异常: %s", e)

    def _parse_positions_from_resp(
        self, resp: Dict[str, Any]
    ) -> Dict[str, Dict[str, float]]:
        """从 send_game_command_full 的返回值中解析玩家坐标。

        通过适配器的 resolve_player_names 方法获取 UUID→名字映射，
        避免直接依赖平台内部对象，保持适配器抽象层清洁。
        """
        # 收集所有需要解析的条目
        all_entries = []
        for out in resp.get("output", []):
            for param in out.get("parameters", []):
                if not isinstance(param, str) or "{" not in param:
                    continue
                try:
                    data = json.loads(param)
                except json.JSONDecodeError:
                    try:
                        data = json.loads(
                            param.replace("\n", "").replace(" ", "")
                        )
                    except json.JSONDecodeError:
                        continue
                if isinstance(data, list):
                    all_entries.extend(data)
                elif isinstance(data, dict):
                    all_entries.append(data)

        # 通过适配器解析 UUID→名字（Pythonic：适配器自己知道怎么查）
        uuid_to_player = self.adapter.resolve_player_names(all_entries)

        positions = {}
        for entry in all_entries:
            if not isinstance(entry, dict):
                continue
            unique_id = entry.get("uniqueId", "")
            name = uuid_to_player.get(unique_id)
            if not name:
                continue
            pos = entry.get("position", {})
            positions[name] = {
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "z": float(pos.get("z", 0)),
                "yRot": float(entry.get("yRot", 0)),
                "dimension": int(entry.get("dimension", 0)),
            }
        return positions

    @command(".分布图")
    async def _cmd_map(self, ctx):
        """生成玩家分布图并发送到当前群。"""
        if not HAS_PIL:
            await ctx.reply("Pillow 库未安装，无法生成地图。")
            return

        async with self._lock:
            positions = dict(self._positions)

        if not positions:
            await ctx.reply("当前没有玩家坐标数据，请稍后再试。")
            return

        img = await self._render_map(positions)
        if img is None:
            await ctx.reply("图片生成失败。")
            return

        await self.message.send_group(
            ctx.group_id,
            f"[CQ:image,file=base64://{img}]",
        )

    @command(".位置", op_only=True)
    async def _cmd_pos(self, ctx):
        """查询指定玩家当前坐标（仅管理员）。"""
        if not ctx.args:
            await ctx.reply("用法：.位置 <玩家名>")
            return
        target = ctx.args[0]
        async with self._lock:
            positions = dict(self._positions)
        if target not in positions:
            await ctx.reply(f"玩家 {target} 当前不在线或暂无坐标数据。")
            return
        pos = positions[target]
        x = pos.get("x", 0)
        y = pos.get("y", 0)
        z = pos.get("z", 0)
        dim = pos.get("dimension", 0)
        dim_names = {0: "主世界", 1: "末地", 2: "下界"}
        dim_str = dim_names.get(dim, f"维度{dim}")
        await ctx.reply(
            f"{target} 坐标：({x:.1f}, {y:.1f}, {z:.1f}) {dim_str}"
        )

    @staticmethod
    async def _render_map(
        positions: Dict[str, Dict[str, float]]
    ) -> Optional[str]:
        """将坐标数据渲染为 base64 图片。"""
        try:
            coords_list = [
                (name, pos["x"], pos["z"])
                for name, pos in positions.items()
                if "x" in pos and "z" in pos
            ]
            if not coords_list:
                return None

            xs = [x for _, x, z in coords_list]
            zs = [z for _, x, z in coords_list]
            min_x, max_x = min(xs), max(xs)
            min_z, max_z = min(zs), max(zs)
            range_x = max_x - min_x or 1
            range_z = max_z - min_z or 1

            img_width = 800
            img_height = 800
            padding = 50
            map_w = img_width - 2 * padding
            map_h = img_height - 2 * padding

            def to_screen(x, z):
                """将游戏坐标映射到画布像素坐标。"""
                screen_x = padding + (x - min_x) / range_x * map_w
                screen_y = padding + (z - min_z) / range_z * map_h
                return int(screen_x), int(screen_y)

            img = Image.new("RGB", (img_width, img_height), (30, 30, 30))
            draw = ImageDraw.Draw(img)

            for i in range(0, img_width, 100):
                draw.line(
                    [(i, 0), (i, img_height)], fill=(60, 60, 60)
                )
            for i in range(0, img_height, 100):
                draw.line(
                    [(0, i), (img_width, i)], fill=(60, 60, 60)
                )

            dot_radius = 6
            for name, x, z in coords_list:
                sx, sz = to_screen(x, z)
                draw.ellipse(
                    [
                        sx - dot_radius,
                        sz - dot_radius,
                        sx + dot_radius,
                        sz + dot_radius,
                    ],
                    fill=(0, 255, 0),
                )
                draw.text(
                    (sx + 10, sz - 5), name, fill=(255, 255, 255)
                )

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            _logger.error("渲染地图失败: %s", e)
            return None
