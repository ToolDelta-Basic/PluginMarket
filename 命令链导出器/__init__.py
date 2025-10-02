from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Tuple, List  # noqa: F401, UP035
import math
from tooldelta import Plugin, plugin_entry, fmts


@dataclass
class CmdBlockInfo:
    position: tuple[int, int, int]
    mode: int  # 0 脉冲, 1 循环, 2 连锁
    conditional: bool  # True 有条件, False 无条件
    need_redstone: bool  # True 需要红石, False 始终开启
    facing: int  # 0~5 特殊值
    tick_delay: int
    name: str
    command: str


class ChainExporter(Plugin):
    name = "命令链导出器"
    author = "猫七街"
    description = "导出指定坐标处命令方块链为txt"
    version = (0, 1, 0)

    def __init__(self, frame):
        super().__init__(frame)
        self.world_api: Any | None = None
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        # 分片缓存：16x64x16，按 (cx, cy, cz) 分片，避免一次抓取过高导致失败
        self._chunk_cache: dict[tuple[int, int, int], Any] = {}
        self._chunk_size = 16
        self._y_min = -64
        self._y_slice = 64

    def on_preload(self):
        self.world_api = self.GetPluginAPI("前置-世界交互")

    def on_active(self):
        self.frame.add_console_cmd_trigger(
            ["export"], "x y z", "导出命令方块链为txt", self.on_export_cmd
        )
        self.frame.add_console_cmd_trigger(
            ["import"], None, "从txt导入命令方块链到指定坐标", self.on_import_cmd
        )

    def on_export_cmd(self, args: list[str]):
        if self.world_api is None:
            fmts.print_err("未找到前置-世界交互 API")
            return
        if len(args) < 3:
            fmts.print_err("用法: export x y z")
            return
        try:
            x, y, z = (int(args[0]), int(args[1]), int(args[2]))
        except Exception:
            fmts.print_err("参数错误，应为整数坐标 x y z")
            return

        # 交互式文件名
        try:
            filename = input("请输入导出文件名(默认 chain.txt): ").strip()
        except Exception:
            filename = "chain.txt"
        if filename == "":
            filename = "chain.txt"
        # 开始导出

        # 调试输出已关闭

        # 流式写入：确定好起点后，边遍历边写入
        out_path = self.data_path / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                for line in self.export_chain_iter((x, y, z)):
                    f.write(line + "\n")
                    total += 1
        except Exception as err:
            fmts.print_err(f"导出失败: {err}")
            return
        fmts.print_suc(f"已导出 {total} 行到 {out_path}")

    # ---- 核心逻辑 ----
    def export_chain(self, start_pos: tuple[int, int, int]) -> list[str]:
        # 先定位起点: 若给定的不是链表开头，则向前追溯直到起点
        head_pos, head_info = self.find_chain_head(start_pos)

        # 从起点开始遍历，允许跨区块，支持断链与首尾相接
        result_lines: list[str] = []
        visited: set[tuple[int, int, int]] = set()
        prev_pos: tuple[int, int, int] | None = None

        current_pos = head_pos
        current_info = head_info

        while True:
            if current_pos in visited:
                # 检测到环，结束
                break
            visited.add(current_pos)

            # 生成一行文本
            line = self.format_line(current_info, prev_pos)
            result_lines.append(line)

            # 记录上一块坐标用于下一行相对位移
            prev_pos = current_pos

            # 查找下一个命令方块（考虑断链与跨区块）
            nxt = self.find_next_cmd_block(current_pos, current_info)
            if nxt is None:
                break
            # 断链处理: 若中间缺失一格，再继续找
            if nxt == "deny":
                # deny 记录: 与上一个的相对坐标
                gap_pos = self.find_first_gap_pos(current_pos, current_info)
                rel = self.calc_rel_pos(prev_pos if prev_pos else current_pos, gap_pos)
                result_lines.append(f"[deny][{rel}]")
                # 继续寻找真正的下一个方块
                nxt2 = self.find_next_after_gap(current_pos, current_info)
                if nxt2 is None:
                    break
                current_pos, current_info = nxt2
            else:
                current_pos, current_info = nxt

        return result_lines

    def export_chain_iter(self, start_pos: tuple[int, int, int]):
        # 先定位起点
        head_pos, head_info = self.find_chain_head(start_pos)

        visited: set[tuple[int, int, int]] = set()
        prev_pos: tuple[int, int, int] | None = None
        current_pos = head_pos
        current_info = head_info

        while True:
            if current_pos in visited:
                break
            visited.add(current_pos)

            yield self.format_line(current_info, prev_pos)
            prev_pos = current_pos

            nxt = self.find_next_cmd_block(current_pos, current_info)
            if nxt is None:
                break
            if nxt == "deny":
                gap_pos = self.find_first_gap_pos(current_pos, current_info)
                rel = self.calc_rel_pos(prev_pos if prev_pos else current_pos, gap_pos)
                yield f"[deny][{rel}]"
                nxt2 = self.find_next_after_gap(current_pos, current_info)
                if nxt2 is None:
                    break
                current_pos, current_info = nxt2
            else:
                current_pos, current_info = nxt

    # ---- 工具方法 ----
    def find_chain_head(self, pos: tuple[int, int, int]):
        # 从起始方块往反方向追溯，直到没有上一个
        info = self.get_cmd_block_info(pos)
        if info is None:
            raise ValueError("起始坐标不是命令方块")
        cur_pos = pos
        cur_info = info

        while True:
            prev_pos = self.get_prev_pos_any(cur_pos)
            if prev_pos is None:
                return cur_pos, cur_info
            prev_info = self.get_cmd_block_info(prev_pos)
            if prev_info is None:
                return cur_pos, cur_info
            cur_pos, cur_info = prev_pos, prev_info

    def get_prev_pos(self, pos: tuple[int, int, int], info: CmdBlockInfo):
        # 由当前方块朝向推测上一个方块位置：上一方块输出指向当前
        # 上一方块应位于 “输出方向的反向” 一格
        dx, dy, dz = self.facing_to_output_delta(info.facing)
        prev_pos = (pos[0] - dx, pos[1] - dy, pos[2] - dz)
        # 可允许“隔一个方块断链”
        if self.is_cmd_block(prev_pos):
            return prev_pos
        gap_pos = (pos[0] - 2 * dx, pos[1] - 2 * dy, pos[2] - 2 * dz)
        if self.is_cmd_block(gap_pos):
            return gap_pos
        return None

    def get_prev_pos_any(self, pos: tuple[int, int, int]):
        """基于拓扑反向匹配，寻找上一块。
        规则：
        - 相邻1格 cand 为命令方块，且 cand 的输出向量指向当前 pos
        - 相邻1格不是命令方块，但相邻2格 cand2 是命令方块，且 cand2 的输出向量指向相邻1格
        """
        directions = [
            (1, 0, 0),
            (-1, 0, 0),
            (0, 1, 0),
            (0, -1, 0),
            (0, 0, 1),
            (0, 0, -1),
        ]
        px, py, pz = pos
        # 先检查相邻1格
        for ox, oy, oz in directions:
            cand = (px - ox, py - oy, pz - oz)
            if not self.is_cmd_block(cand):
                continue
            info = self.get_cmd_block_info(cand)
            if info is None:
                continue
            odx, ody, odz = self.facing_to_output_delta(info.facing)
            if (cand[0] + odx, cand[1] + ody, cand[2] + odz) == pos:
                return cand
        # 再检查间隔一格
        for ox, oy, oz in directions:
            imd = (px - ox, py - oy, pz - oz)
            cand2 = (px - 2 * ox, py - 2 * oy, pz - 2 * oz)
            if self.is_cmd_block(imd):
                continue
            if not self.is_cmd_block(cand2):
                continue
            info2 = self.get_cmd_block_info(cand2)
            if info2 is None:
                continue
            odx, ody, odz = self.facing_to_output_delta(info2.facing)
            if (cand2[0] + odx, cand2[1] + ody, cand2[2] + odz) == imd:
                return cand2
        return None

    def get_next_pos(self, pos: tuple[int, int, int], info: CmdBlockInfo):
        # 严格按当前方块朝向前进
        dx, dy, dz = self.facing_to_output_delta(info.facing)
        nxt_pos = (pos[0] + dx, pos[1] + dy, pos[2] + dz)
        if self.is_cmd_block(nxt_pos):
            return nxt_pos
        gap_pos = (pos[0] + 2 * dx, pos[1] + 2 * dy, pos[2] + 2 * dz)
        if self.is_cmd_block(gap_pos):
            return "deny"
        return None

    def find_next_cmd_block(self, pos: tuple[int, int, int], info: CmdBlockInfo):
        nxt = self.get_next_pos(pos, info)
        if nxt is None:
            return None
        if nxt == "deny":
            # 仅要求缺失后一块为 setblock，且朝向一致
            nxt2 = self.find_next_after_gap(pos, info)
            if nxt2 is None:
                return None
            _, nxt2_info = nxt2
            if not self.is_setblock_command(nxt2_info.command):
                return None
            return "deny"
        nxt_info = self.get_cmd_block_info(nxt)
        if nxt_info is None:
            return None
        return nxt, nxt_info

    def find_first_gap_pos(self, pos: tuple[int, int, int], info: CmdBlockInfo):
        # 缺失位置即朝向前进的一格
        dx, dy, dz = self.facing_to_output_delta(info.facing)
        return (pos[0] + dx, pos[1] + dy, pos[2] + dz)

    def find_next_after_gap(self, pos: tuple[int, int, int], info: CmdBlockInfo):
        # 缺失后一格即朝向前进两格
        dx, dy, dz = self.facing_to_output_delta(info.facing)
        cand2 = (pos[0] + 2 * dx, pos[1] + 2 * dy, pos[2] + 2 * dz)
        if not self.is_cmd_block(cand2):
            return None
        ninfo2 = self.get_cmd_block_info(cand2)
        if ninfo2 is None:
            return None
        return cand2, ninfo2

    def is_cmd_block(self, pos: tuple[int, int, int]) -> bool:
        block = self.get_block_cached(pos[0], pos[1], pos[2])
        if block is None:
            return False
        # 前景/背景任一层是命令方块即可
        names: list[str] = []
        if block.foreground is not None:
            try:
                names.append(block.foreground.name.value)
            except Exception:
                names.append(str(block.foreground.name).strip('"'))
        if block.background is not None:
            try:
                names.append(block.background.name.value)
            except Exception:
                names.append(str(block.background.name).strip('"'))
        target = (
            "minecraft:command_block",
            "minecraft:repeating_command_block",
            "minecraft:chain_command_block",
        )
        return any(n in target for n in names)

    def get_cmd_block_info(self, pos: tuple[int, int, int]) -> CmdBlockInfo | None:
        block = self.get_block_cached(pos[0], pos[1], pos[2])
        if block is None:
            return None
        layer = block.foreground or block.background
        if layer is None:
            return None
        try:
            name = layer.name.value
        except Exception:
            name = str(layer.name).strip('"')
        if name not in (
            "minecraft:command_block",
            "minecraft:repeating_command_block",
            "minecraft:chain_command_block",
        ):
            return None

        entity = block.entity_data or {}
        command = str(entity.get("Command", ""))
        tick_delay = int(entity.get("TickDelay", 0))
        cb_name = str(entity.get("CustomName", ""))
        conditional = bool(entity.get("conditionalMode", 0))
        need_redstone = not bool(entity.get("auto", 1))

        states = layer.states
        facing = int(states.get("facing_direction", 0))

        if name == "minecraft:command_block":
            mode = 0
        elif name == "minecraft:repeating_command_block":
            mode = 1
        else:
            mode = 2

        info = CmdBlockInfo(
            position=pos,
            mode=mode,
            conditional=conditional,
            need_redstone=need_redstone,
            facing=facing,
            tick_delay=tick_delay,
            name=cb_name,
            command=command,
        )
        return info

    # 调试工具已移除

    # ---- 区块缓存与读取 ----
    def _chunk_key(self, x: int, y: int, z: int) -> tuple[int, int, int]:
        # Python 整除向下取整，适用于负坐标
        cx = x // self._chunk_size
        cy = (y - self._y_min) // self._y_slice
        cz = z // self._chunk_size
        return (cx, cy, cz)

    def _chunk_origin(self, cx: int, cy: int, cz: int) -> tuple[int, int, int]:
        return (
            cx * self._chunk_size,
            self._y_min + cy * self._y_slice,
            cz * self._chunk_size,
        )

    def ensure_chunk_loaded(self, cx: int, cy: int, cz: int) -> None:
        if (cx, cy, cz) in self._chunk_cache:
            return
        if self.world_api is None:
            return
        origin = self._chunk_origin(cx, cy, cz)
        try:
            struct = self.world_api.get_structure(
                origin,
                (self._chunk_size, self._y_slice, self._chunk_size),
            )
            self._chunk_cache[(cx, cy, cz)] = struct
        except Exception:
            # 加载失败则留空，后续访问返回 None
            self._chunk_cache[(cx, cy, cz)] = None

    def get_block_cached(self, x: int, y: int, z: int):
        cx, cy, cz = self._chunk_key(x, y, z)
        self.ensure_chunk_loaded(cx, cy, cz)
        struct = self._chunk_cache.get((cx, cy, cz))
        if struct is None:
            return None
        # 计算区块内相对坐标
        rx = x - cx * self._chunk_size
        ry = y - (self._y_min + cy * self._y_slice)
        rz = z - cz * self._chunk_size
        try:
            return struct.get_block((rx, ry, rz))
        except Exception:
            return None

    # ---- 导入逻辑 ----
    def on_import_cmd(self, args: list[str]):
        api = self.world_api
        if api is None:
            fmts.print_err("未找到前置-世界交互 API")
            return
        # 列出数据目录文件
        files = sorted([p.name for p in self.data_path.glob("*.txt")])
        if not files:
            fmts.print_err("数据目录下没有可导入的txt文件")
            return
        self.print("可导入的文件:")
        for idx, fn in enumerate(files, 1):
            self.print(f"  {idx}. {fn}")
        try:
            choice = input("请输入要导入的序号: ").strip()
            if not choice.isdigit() or int(choice) not in range(1, len(files) + 1):
                fmts.print_err("输入不合法")
                return
            filename = files[int(choice) - 1]
        except Exception:
            fmts.print_err("输入错误")
            return

        # 输入目标坐标
        try:
            sx = int(input("请输入目标起点x: ").strip())
            sy = int(input("请输入目标起点y: ").strip())
            sz = int(input("请输入目标起点z: ").strip())
        except Exception:
            fmts.print_err("坐标输入错误")
            return

        file_path = self.data_path / filename
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except Exception as err:
            fmts.print_err(f"读取文件失败: {err}")
            return

        self.print(f"开始导入: 文件={filename}, 起点=({sx},{sy},{sz})")
        try:
            self.import_chain((sx, sy, sz), lines)
        except Exception as err:
            fmts.print_err(f"导入失败: {err}")
            return
        fmts.print_suc("导入完成")

    def import_chain(self, start_pos: tuple[int, int, int], lines: list[str]):
        api = self.world_api
        assert api is not None

        cur = start_pos
        for raw in lines:
            if raw.startswith("[deny]"):
                # 解析 [deny][~dx ~dy ~dz] 并在缺失位置放置拒绝方块
                rdx, rdy, rdz = self.parse_deny_line(raw)
                deny_pos = (cur[0] + rdx, cur[1] + rdy, cur[2] + rdz)
                self.place_deny_block(deny_pos)
                # 注意：deny 不更新 cur，后续命令的相对位移仍以上一个命令方块为基准
                continue
            # 解析一行: [abcd]<x?>[~dx ~dy ~dz]<name?> command
            flags, delay, rel, name, command = self.parse_export_line(raw)

            # 相对位移 -> 绝对
            dx, dy, dz = rel
            cur = (cur[0] + dx, cur[1] + dy, cur[2] + dz)

            # flags 解码
            a, b, c, d = flags
            # 按导出保持一致: 0=脉冲, 1=循环, 2=连锁
            mode = a
            need_redstone = (c == 0)
            conditional = (b == 1)
            facing = d

            # 生成并放置
            pkt = api.make_packet_command_block_update(
                position=cur,
                command=command,
                mode=mode,
                need_redstone=need_redstone,
                tick_delay=delay or 0,
                conditional=conditional,
                name=name or "",
                should_track_output=True,
                execute_on_first_tick=True,
            )
            # 使用带回执的可靠路径，确保在无足够权限/异步场景下也能成功
            api.place_command_block(pkt, facing=facing, limit_seconds=0.0, limit_seconds2=0.0)

    def parse_export_line(self, raw: str):
        # 解析 [abcd]
        if not raw.startswith("["):
            raise ValueError(f"非法行: {raw}")
        r = raw
        p1 = r.find("]")
        flags_str = r[1:p1]
        if len(flags_str) != 4 or not flags_str.isdigit():
            raise ValueError(f"非法flags: {flags_str}")
        a, b, c, d = (int(flags_str[0]), int(flags_str[1]), int(flags_str[2]), int(flags_str[3]))

        r = r[p1 + 1 :].lstrip()
        delay = 0
        if r.startswith("<"):
            p2 = r.find(">")
            delay_str = r[1:p2].strip()
            delay = int(delay_str) if delay_str else 0
            r = r[p2 + 1 :].lstrip()

        # [~dx ~dy ~dz]
        if not r.startswith("["):
            raise ValueError("缺少相对位移段")
        p3 = r.find("]")
        rel_str = r[1:p3].strip()
        parts = rel_str.split()
        if len(parts) != 3:
            raise ValueError("相对位移格式错误")
        def parse_tilde(s: str) -> int:
            if not s.startswith("~"):
                raise ValueError("相对坐标需以~开头")
            v = s[1:]
            return int(v) if v else 0
        dx, dy, dz = (parse_tilde(parts[0]), parse_tilde(parts[1]), parse_tilde(parts[2]))
        r = r[p3 + 1 :].lstrip()

        # <name> 可选
        name = ""
        if r.startswith("<"):
            p4 = r.find(">")
            name = r[1:p4]
            r = r[p4 + 1 :].lstrip()

        # 剩余为 command
        command = r
        return (a, b, c, d), delay, (dx, dy, dz), name, command

    def parse_deny_line(self, raw: str) -> tuple[int, int, int]:
        # 形如: [deny][~dx ~dy ~dz]
        if not raw.startswith("[deny]"):
            raise ValueError(f"非法deny行: {raw}")
        r = raw[len("[deny]") :].lstrip()
        if not r.startswith("["):
            raise ValueError("deny 缺少相对位移段")
        p = r.find("]")
        rel_str = r[1:p].strip()
        parts = rel_str.split()
        if len(parts) != 3:
            raise ValueError("deny 相对位移格式错误")
        def parse_tilde(s: str) -> int:
            if not s.startswith("~"):
                raise ValueError("相对坐标需以~开头")
            v = s[1:]
            return int(v) if v else 0
        dx, dy, dz = (parse_tilde(parts[0]), parse_tilde(parts[1]), parse_tilde(parts[2]))
        return dx, dy, dz

    def place_deny_block(self, pos: tuple[int, int, int]) -> None:
        # 尝试放置拒绝方块
        x, y, z = pos
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(f"/setblock {x} {y} {z} deny")
            if getattr(resp, "SuccessCount", 0) == 0:
                self.game_ctrl.sendwscmd_with_resp(f"/setblock {x} {y} {z} minecraft:deny")
        except Exception:
            # 降级尝试无回调
            try:
                self.game_ctrl.sendcmd(f"/setblock {x} {y} {z} deny")
            except Exception:
                self.game_ctrl.sendcmd(f"/setblock {x} {y} {z} minecraft:deny")

    def is_setblock_command(self, cmd: str) -> bool:
        t = cmd.strip()
        if not t:
            return False
        if t.startswith("/"):
            t = t[1:]
        low = t.lower()
        # 直接 setblock 或 execute ... run setblock 或 execute ... run /setblock
        if low.startswith("setblock "):
            return True
        if " run setblock " in low:
            return True
        if " run /setblock " in low:
            return True
        return False

    def facing_to_output_delta(self, facing: int) -> tuple[int, int, int]:
        # 基于Bedrock方块朝向: 0=下 1=上 2=北 3=南 4=西 5=东
        mapping = {
            0: (0, -1, 0),
            1: (0, 1, 0),
            2: (0, 0, -1),
            3: (0, 0, 1),
            4: (-1, 0, 0),
            5: (1, 0, 0),
        }
        return mapping.get(facing, (0, 0, 0))

    def facing_to_input_delta(self, facing: int) -> tuple[int, int, int]:
        dx, dy, dz = self.facing_to_output_delta(facing)
        return (-dx, -dy, -dz)

    def calc_rel_pos(
        self, base: tuple[int, int, int], target: tuple[int, int, int]
    ) -> str:
        dx = target[0] - base[0]
        dy = target[1] - base[1]
        dz = target[2] - base[2]
        return f"~{dx} ~{dy} ~{dz}"

    def encode_flags(self, info: CmdBlockInfo) -> str:
        # [abcd]: a 模式(0脉冲/1条件/2循环) — 注意用户给的定义：
        # 需求解释里第一位=0脉冲,1条件,2循环；但Bedrock有连锁。此处按用户描述：
        # 0=脉冲, 1=条件, 2=循环。连锁模式在mode=2时视作循环的特殊派生？
        # 为与“解释2”的四位编码对齐，采用：第一位=0/1/2（三态），第二位=条件0/1，第三位=红石0/1，第四位=朝向0~5
        a = info.mode if info.mode in (0, 1, 2) else 0
        b = 1 if info.conditional else 0
        c = 0 if info.need_redstone else 1
        d = max(0, min(5, info.facing))
        return f"[{a}{b}{c}{d}]"

    def format_line(
        self, info: CmdBlockInfo, prev_pos: tuple[int, int, int] | None
    ) -> str:
        flags = self.encode_flags(info)
        delay_part = f"<{info.tick_delay}>" if info.tick_delay else ""
        rel = self.calc_rel_pos(prev_pos or info.position, info.position)
        name_part = f"<{info.name}>" if info.name else ""
        # 目标格式: "[xxxx]<x>[~~~]<name> gamemode c @a"
        space = " " if name_part else " "  # noqa: RUF034
        return f"{flags}{delay_part}[{rel}]{name_part}{space}{info.command}".strip()


entry = plugin_entry(ChainExporter)


