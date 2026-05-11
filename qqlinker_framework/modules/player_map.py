"""玩家坐标分布图模块，持久化坐标数据并生成地图图片，提供安全模块接口。"""
import asyncio
import base64
import io
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List

from ..core.module import Module
from ..core.decorators import command

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 时间粒度映射
_TIME_UNITS = {
    "毫秒": 1,
    "秒": 1000,
    "分钟": 60000,
}


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
        # 毫秒保持原样（浮点数转 int 毫秒），秒/分钟则截断为整数单位
        if self._unit_ms == 1:
            return int(ts * 1000)  # 转为毫秒整数
        return int(ts * 1000 / self._unit_ms) * self._unit_ms

    async def update_positions(self, positions: Dict[str, dict]):
        """添加新的坐标快照（异步安全），并持久化。"""
        async with self._lock:
            now = time.time()
            truncated = self._truncate_time(now)
            # 避免同一粒度内的重复快照
            if (
                self._snapshots
                and self._snapshots[-1].get("timestamp") == truncated
            ):
                # 更新最后一个快照的位置数据
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


class PlayerMapModule(Module):
    """玩家位置地图模块，持久化坐标数据并生成地图图片。"""

    name = "player_map"
    version = (1, 0, 1)
    required_services = ["config", "message", "adapter"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._lock = asyncio.Lock()
        self._service: Optional[PlayerPositionService] = None
        self._positions: Dict[str, Dict[str, float]] = {}

    async def on_init(self):
        """初始化数据目录、服务注册、命令和广播监听。"""
        self.config.register_section("玩家分布图", {
            "最大快照数": 100,
            "存储粒度": "秒",
        })
        cfg = self.config.get("玩家分布图")
        max_snapshots = cfg.get("最大快照数", 100)
        time_unit = cfg.get("存储粒度", "秒")

        module_dir = self.get_data_dir()
        self._service = PlayerPositionService(
            module_dir,
            max_snapshots=max_snapshots,
            time_unit=time_unit,
        )
        self.services.register("player_positions", self._service)

        self.register_command(
            ".map", self._cmd_map,
            description="查看玩家坐标分布图",
        )
        self.register_command(
            ".pos", self._cmd_pos,
            description="查看指定玩家的当前坐标",
            argument_hint="<玩家名>",
        )

        self.adapter.listen_internal_broadcast(
            "ggpp:publish_player_position",
            self._on_position_broadcast,
        )

    def _on_position_broadcast(self, data: Dict[str, Any]):
        """接收坐标广播，异步更新内存和持久化。"""
        try:
            asyncio.run_coroutine_threadsafe(
                self._handle_position_update(data),
                asyncio.get_running_loop(),
            )
        except RuntimeError:
            self._positions = data

    async def _handle_position_update(self, data: Dict[str, Any]):
        """异步安全更新内存缓存和持久化存储。"""
        async with self._lock:
            self._positions = data
        if self._service:
            await self._service.update_positions(data)

    @command(".map")
    async def _cmd_map(self, ctx):
        """生成玩家分布图并发送到当前群。"""
        if not HAS_PIL:
            await ctx.reply("Pillow 库未安装，无法生成地图。")
            return

        positions = (
            await self._service.get_current_positions()
            if self._service
            else self._positions
        )
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

    @command(".pos")
    async def _cmd_pos(self, ctx):
        """查询指定玩家当前坐标。"""
        if not self._service:
            await ctx.reply("坐标服务未就绪。")
            return
        if not ctx.args:
            await ctx.reply("用法：.pos <玩家名>")
            return
        target = ctx.args[0]
        positions = await self._service.get_current_positions()
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

    async def _render_map(
        self, positions: Dict[str, Dict[str, float]]
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
            logging.getLogger(__name__).error(f"渲染地图失败: {e}")
            return None
