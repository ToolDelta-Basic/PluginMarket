"""
反作弊-移动检测 (MUNAN)
包含飞行、平地飞、回弹飞、加速度、速度、上升速度等多维度检测。
"""
import time
import math
import json
from collections import deque
from tooldelta import Plugin, InternalBroadcast, fmts, plugin_entry, cfg as config


class SimpleAntiCheat(Plugin):
    """多维移动反作弊插件，支持自定义阈值与骑马检测。"""

    name = "反作弊-移动检测(MUNAN)"
    author = "Assistant"
    version = (0, 0, 4)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenInternalBroadcast("ggpp:publish_player_position", self.on_pos_data)
        self.pos_history = {}
        self.rollback_history = {}
        self.last_pos = {}
        self.air_pos_history = {}
        self.last_print_time = 0
        self.last_admin_show_time = 0
        self.rollback_count = {}

        DEFAULT_CFG = {
            # 开关
            "飞行检测开关": True,
            "平地飞检测开关": True,
            "回弹飞检测开关": True,
            "预测检测开关": True,
            "控制台打印位置": True,
            "加速度检测开关": True,
            "速度检测开关": True,
            "上升速度检测开关": True,
            "管理员显示加速度": True,
            # 飞行检测
            "飞行最小水平速度": 12.0,
            "飞行下落检测秒数": 3.0,
            "飞行最大可通过下落": -0.8,
            "飞行最小下落速度": -2.0,
            "飞行跳跃上升阈值": 1.2,
            "飞行最小悬空秒数": 0.5,
            "飞行脚下检测距离": 1.0,
            "飞行连续拉回次数阈值": 3,
            # 平地飞检测
            "平地飞水平速度阈值": 7.74545,
            "平地飞Y轴标准差阈值": 0.35,
            "平地飞水平加速度阈值": 6.54055,
            # 回弹飞检测
            "回弹飞最小持续秒数": 4.0,
            "回弹飞最小波动次数": 3,
            "回弹飞最小波幅": 0.4,
            "回弹飞最大波幅": 2.5,
            "回弹飞最低水平速度": 2.0,
            # 预测检测
            "预测时间_秒": 0.5,
            "预测基础误差_米": 22.45173,
            "预测速度误差因子": 0.3,
            "预测速度不稳定放宽因子": 3.0,
            "预测速度稳定性阈值": 0.45,
            # 通用
            "回拉秒数": 3.0,
            "位置打印间隔_秒": 5.0,
            # 加速度检测
            "加速度异常水平阈值": 12.42526,
            "加速度异常垂直阈值": 21.89734,
            # 速度检测
            "速度异常水平阈值": 8.0,
            "骑马速度水平阈值": 18.0,
            # 上升速度检测
            "上升速度阈值": 4.5,
            # 管理员显示
            "管理员显示间隔_秒": 0.5,
            # 豁免
            "速度检测下落豁免": True,
        }

        STD_CFG = {
            "飞行检测开关": bool,
            "平地飞检测开关": bool,
            "回弹飞检测开关": bool,
            "预测检测开关": bool,
            "控制台打印位置": bool,
            "加速度检测开关": bool,
            "速度检测开关": bool,
            "上升速度检测开关": bool,
            "管理员显示加速度": bool,
            "飞行最小水平速度": (int, float),
            "飞行下落检测秒数": (int, float),
            "飞行最大可通过下落": (int, float),
            "飞行最小下落速度": (int, float),
            "飞行跳跃上升阈值": (int, float),
            "飞行最小悬空秒数": (int, float),
            "飞行脚下检测距离": (int, float),
            "飞行连续拉回次数阈值": int,
            "平地飞水平速度阈值": (int, float),
            "平地飞Y轴标准差阈值": (int, float),
            "平地飞水平加速度阈值": (int, float),
            "回弹飞最小持续秒数": (int, float),
            "回弹飞最小波动次数": int,
            "回弹飞最小波幅": (int, float),
            "回弹飞最大波幅": (int, float),
            "回弹飞最低水平速度": (int, float),
            "预测时间_秒": (int, float),
            "预测基础误差_米": (int, float),
            "预测速度误差因子": (int, float),
            "预测速度不稳定放宽因子": (int, float),
            "预测速度稳定性阈值": (int, float),
            "回拉秒数": (int, float),
            "位置打印间隔_秒": (int, float),
            "加速度异常水平阈值": (int, float),
            "加速度异常垂直阈值": (int, float),
            "速度异常水平阈值": (int, float),
            "骑马速度水平阈值": (int, float),
            "上升速度阈值": (int, float),
            "管理员显示间隔_秒": (int, float),
            "速度检测下落豁免": bool,
        }

        self.cfg, _ = config.get_plugin_config_and_version(
            self.name, STD_CFG, DEFAULT_CFG, self.version
        )
        fmts.print_inf("[MUNAN ANTI CHEAT] 所有模块配置已加载")

    # ---------- 工具方法 ----------
    def is_bypass(self, name: str) -> bool:
        """检查玩家是否拥有 bypass 豁免标签。"""
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(
                f"/execute as {name} if entity @s[tag=bypass]"
            )
            return resp.SuccessCount > 0
        except Exception:
            return False

    def _is_riding(self, name: str) -> bool:
        """检查玩家是否骑乘实体（通过 RootVehicle 或 on vehicle 命令）。"""
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(
                f"/data get entity {name} RootVehicle"
            )
            if resp.SuccessCount > 0:
                return True
        except Exception:
            pass
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(
                f"/execute as {name} on vehicle"
            )
            if resp.SuccessCount > 0:
                return True
        except Exception:
            pass
        return False

    def _is_unsupported(self, name: str) -> bool:
        """检查脚下是否没有固体支撑（空气或可攀爬方块）。"""
        distance = self.cfg["飞行脚下检测距离"]
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(
                f"/execute as {name} at @s if block ~ ~-{distance} ~ air"
            )
            if resp.SuccessCount > 0:
                return True
        except Exception:
            pass
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(
                f"/execute as {name} at @s if block ~ ~-{distance} ~ "
                f"#minecraft:climbable"
            )
            if resp.SuccessCount > 0:
                return True
        except Exception:
            pass
        return False

    def _update_history(self, name: str, pos: dict, now: float) -> None:
        """更新玩家坐标历史，空中与地面分开存储。"""
        if self._is_unsupported(name):
            if name not in self.air_pos_history:
                self.air_pos_history[name] = deque(maxlen=5)
            self.air_pos_history[name].append(
                (pos["x"], pos["y"], pos["z"], now)
            )
            return
        x, y, z = pos["x"], pos["y"], pos["z"]
        self.last_pos[name] = (x, y, z, now)
        if name not in self.pos_history:
            self.pos_history[name] = deque(maxlen=20)
        self.pos_history[name].append((x, y, z, now))
        if name in self.air_pos_history:
            del self.air_pos_history[name]

    def _get_position_at(self, name: str, target_time: float,
                         use_rollback: bool = False):
        """从历史中获取最接近 target_time 的坐标。"""
        history = (
            self.rollback_history.get(name)
            if use_rollback
            else self.pos_history.get(name)
        )
        if not history:
            return None
        best = None
        best_diff = float("inf")
        for x, y, z, t in history:
            diff = abs(t - target_time)
            if diff < best_diff:
                best_diff = diff
                best = (x, y, z)
        return best

    def _is_y_rising(self, name: str, count: int = 3) -> bool:
        """检查最近几次地面历史中 Y 坐标是否严格递增。"""
        history = self.pos_history.get(name)
        if not history or len(history) < count:
            return False
        points = list(history)[-count:]
        for i in range(1, len(points)):
            if points[i][1] <= points[i - 1][1]:
                return False
        return True

    def _record_rollback_target(self, name: str, x: float, y: float,
                                z: float, now: float) -> None:
        """记录一次成功的拉回目标坐标。"""
        if name not in self.rollback_history:
            self.rollback_history[name] = deque(maxlen=50)
        self.rollback_history[name].append((x, y, z, now))

    def _rollback(self, name: str, smart: bool = False,
                  to_earliest: bool = False) -> None:
        """执行拉回操作，支持智能拉回和渐进回溯。"""
        now = time.time()
        if smart:
            self._smart_rollback(name, now, to_earliest)
        else:
            self._normal_rollback(name, now)

    def _smart_rollback(self, name: str, now: float,
                        to_earliest: bool) -> None:
        """智能拉回：利用历史坐标或备用历史。"""
        current = self.last_pos.get(name)
        if not current:
            return
        cx, cy, cz, _ = current
        history = self.pos_history.get(name)
        r_history = self.rollback_history.get(name)

        if to_earliest:
            self._earliest_rollback(name, cx, cy, cz, history, r_history, now)
            return

        if not history or len(history) < 2:
            if r_history and len(r_history) > 0:
                x, y, z, _ = r_history[-1]
                self._tp_and_record(name, x, y, z, "最近安全位置", now)
            else:
                fmts.print_war(f"[反作弊] {name} 无可用历史坐标，拉回失败")
            if name in self.pos_history:
                self.pos_history[name].clear()
            return

        target = self._find_change_point(history, cx, cy, cz)
        self._tp_and_record(
            name, target[0], target[1], target[2], "明显变化前位置", now
        )

        if name in self.pos_history:
            self.pos_history[name].clear()
        self._update_rollback_count(name, now)

    def _earliest_rollback(self, name: str, cx: float, cy: float,
                           cz: float, history, r_history,
                           now: float) -> None:
        """寻找最早的变化点进行拉回。"""
        target = None
        if history and len(history) > 0:
            for x, y, z, _ in history:
                if math.hypot(x - cx, y - cy, z - cz) >= 1.0:
                    target = (x, y, z)
                    break
        if not target and r_history and len(r_history) > 0:
            target = (r_history[0][0], r_history[0][1], r_history[0][2])
        elif not target and history and len(history) > 0:
            target = (history[0][0], history[0][1], history[0][2])
        if not target:
            return
        self._tp_and_record(
            name, target[0], target[1], target[2], "最早变化点", now
        )
        if name in self.pos_history:
            self.pos_history[name].clear()
        if name in self.rollback_count:
            self.rollback_count[name] = []

    @staticmethod
    def _find_change_point(history, cx: float, cy: float, cz: float):
        """从历史中找出与当前位置距离>=1.0 的点。"""
        for x, y, z, _ in reversed(list(history)[:-1]):
            if math.hypot(x - cx, y - cy, z - cz) >= 1.0:
                return (x, y, z)
        return (history[0][0], history[0][1], history[0][2])

    def _tp_and_record(self, name: str, x: float, y: float, z: float,
                       reason: str, now: float) -> None:
        """传送玩家并记录拉回目标。"""
        try:
            self.game_ctrl.sendwscmd(f"/tp {name} {x:.5f} {y:.5f} {z:.5f}")
            fmts.print_war(
                f"[反作弊] {name} 拉回至{reason} ({x:.5f}, {y:.5f}, {z:.5f})"
            )
            self._record_rollback_target(name, x, y, z, now)
        except Exception as e:
            fmts.print_err(f"[反作弊] 拉回 {name} 失败: {e}")

    def _update_rollback_count(self, name: str, now: float) -> None:
        """更新连续拉回计数，若超阈值且Y轴持续上升，触发最早变化点拉回。"""
        if name not in self.rollback_count:
            self.rollback_count[name] = []
        self.rollback_count[name].append(now)
        self.rollback_count[name] = [
            t for t in self.rollback_count[name] if now - t <= 10
        ]
        if (len(self.rollback_count[name])
                >= self.cfg["飞行连续拉回次数阈值"]
                and self._is_y_rising(name, count=3)):
            self._rollback(name, smart=True, to_earliest=True)

    def _normal_rollback(self, name: str, now: float) -> None:
        """普通拉回：渐进回溯。"""
        rollback_times = [3, 5, 10, 15, 30, 60]
        for sec in rollback_times:
            target_time = now - sec
            pos = self._get_position_at(name, target_time)
            if pos is not None:
                x, y, z = pos
                self._tp_and_record(name, x, y, z, f"{sec}秒前", now)
                if name in self.pos_history:
                    self.pos_history[name].clear()
                return

        r_history = self.rollback_history.get(name)
        if r_history and len(r_history) > 0:
            x, y, z, _ = r_history[-1]
            self._tp_and_record(name, x, y, z, "备用历史", now)
            if name in self.pos_history:
                self.pos_history[name].clear()
            return

        fmts.print_war(f"[反作弊] 无法找到 {name} 任何有效历史坐标，回退失败")

    @staticmethod
    def _calc_acceleration_from_points(p0, p1, p2, check_interval=True):
        """根据三个点计算水平和垂直加速度。"""
        dt1 = p1[3] - p0[3]
        dt2 = p2[3] - p1[3]
        if check_interval:
            if dt1 < 0.3 or dt2 < 0.3:
                return None, None
        else:
            if dt1 <= 0 or dt2 <= 0:
                return None, None
        vx1 = (p1[0] - p0[0]) / dt1
        vy1 = (p1[1] - p0[1]) / dt1
        vz1 = (p1[2] - p0[2]) / dt1
        vx2 = (p2[0] - p1[0]) / dt2
        vy2 = (p2[1] - p1[1]) / dt2
        vz2 = (p2[2] - p1[2]) / dt2
        dv_h = math.hypot(vx2 - vx1, vz2 - vz1)
        if dv_h > 15.0:
            return None, None
        ax = (vx2 - vx1) / ((dt1 + dt2) / 2)
        ay = (vy2 - vy1) / ((dt1 + dt2) / 2)
        az = (vz2 - vz1) / ((dt1 + dt2) / 2)
        h_acc = math.hypot(ax, az)
        v_acc = abs(ay)
        if h_acc > 50 or v_acc > 50:
            return None, None
        return h_acc, v_acc

    def _get_acceleration(self, name):
        """获取玩家当前精确加速度（优先地面历史，其次空中历史）。"""
        history = self.pos_history.get(name)
        if history and len(history) >= 3:
            p0, p1, p2 = list(history)[-3:]
            return self._calc_acceleration_from_points(
                p0, p1, p2, check_interval=True
            )
        air_hist = self.air_pos_history.get(name)
        if air_hist and len(air_hist) >= 3:
            p0, p1, p2 = list(air_hist)[-3:]
            return self._calc_acceleration_from_points(
                p0, p1, p2, check_interval=False
            )
        return None, None

    def _get_horizontal_speed(self, name: str, pos: dict, now: float):
        """计算玩家水平速度，优先使用空中历史以保证实时性。"""
        air_hist = self.air_pos_history.get(name)
        if air_hist and len(air_hist) >= 2:
            p1 = air_hist[-2]
            p2 = air_hist[-1]
            dt = p2[3] - p1[3]
            if dt > 0:
                return math.hypot(p2[0] - p1[0], p2[2] - p1[2]) / dt
        history = self.pos_history.get(name)
        if history and len(history) >= 2:
            p1 = history[-2]
            p2 = history[-1]
            dt = p2[3] - p1[3]
            if dt > 0:
                return math.hypot(p2[0] - p1[0], p2[2] - p1[2]) / dt
        last = self.last_pos.get(name)
        if last:
            lx, _, lz, lt = last
            dt = now - lt
            if dt > 0:
                return math.hypot(pos["x"] - lx, pos["z"] - lz) / dt
        return None

    def _get_vertical_speed(self, name: str, pos: dict, now: float) -> float:
        """计算玩家垂直速度。"""
        air_hist = self.air_pos_history.get(name)
        if air_hist and len(air_hist) >= 2:
            p1 = air_hist[-2]
            p2 = air_hist[-1]
            dt = p2[3] - p1[3]
            if dt > 0:
                return (p2[1] - p1[1]) / dt
        history = self.pos_history.get(name)
        if history and len(history) >= 2:
            p1 = history[-2]
            p2 = history[-1]
            dt = p2[3] - p1[3]
            if dt > 0:
                return (p2[1] - p1[1]) / dt
        last = self.last_pos.get(name)
        if last:
            _, ly, _, lt = last
            dt = now - lt
            if dt > 0:
                return (pos["y"] - ly) / dt
        return 0.0

    def _show_accel_to_admins(self, all_data: dict, now: float) -> None:
        """向 tag=admin 的玩家在 actionbar 显示速度和加速度信息。"""
        info_parts = [f"§a==== {time.strftime('%H:%M:%S')} ==== "]
        for name, pos in all_data.items():
            if self.is_bypass(name):
                continue
            h_acc, v_acc = self._get_acceleration(name)
            show_h_acc = h_acc if h_acc is not None else 0.0
            show_v_acc = v_acc if v_acc is not None else 0.0

            h_speed = self._get_horizontal_speed(name, pos, now)
            if h_speed is None:
                h_speed = 0.0

            info_parts.append(
                f"\n§e{name}§r: 速度§b{h_speed:.5f}§r, "
                f"水平Acc§b{show_h_acc:.5f}§r, 垂直Acc§b{show_v_acc:.5f}"
            )
        rawtext = [{"text": " ".join(info_parts)}]
        cmd = (
            f"/titleraw @a[tag=admin] actionbar "
            f'{{"rawtext":{json.dumps(rawtext)}}}'
        )
        try:
            self.game_ctrl.sendwocmd(cmd)
        except Exception:
            pass

    # ---------- 主事件 ----------
    def on_pos_data(self, event: InternalBroadcast) -> None:
        """接收前置插件广播的坐标，执行所有检测模块。"""
        data = event.data
        now = time.time()

        should_print = (
            self.cfg["控制台打印位置"]
            and (now - self.last_print_time >= self.cfg["位置打印间隔_秒"])
        )
        if should_print:
            self.last_print_time = now
            fmts.print_inf(
                f"========== 玩家位置 ({time.strftime('%H:%M:%S')}) =========="
            )

        should_show_admin = (
            self.cfg["管理员显示加速度"]
            and (now - self.last_admin_show_time
                 >= self.cfg["管理员显示间隔_秒"])
        )
        if should_show_admin:
            self.last_admin_show_time = now
            self._show_accel_to_admins(data, now)

        for name, pos in data.items():
            if self.is_bypass(name):
                continue

            self._update_history(name, pos, now)

            if should_print:
                fmts.print_inf(
                    f"  {name}: ({pos['x']:.5f}, {pos['y']:.5f}, "
                    f"{pos['z']:.5f})"
                )

            if self.cfg.get("上升速度检测开关", True):
                self._check_rise(name, pos, now)

            if self.cfg["速度检测开关"]:
                self._check_speed(name, pos, now)

            if self.cfg["飞行检测开关"]:
                self._check_flight(name, pos, now)
            if self.cfg["平地飞检测开关"]:
                self._check_groundfly(name, pos, now)
            if self.cfg["回弹飞检测开关"]:
                self._check_bounce(name, pos, now)
            if self.cfg["预测检测开关"]:
                self._check_predict_move(name, pos, now)
            if self.cfg["加速度检测开关"]:
                self._check_acceleration(name, pos, now)

    # ---------- 各检测模块 ----------
    def _check_rise(self, name: str, pos: dict, now: float) -> None:
        """上升速度检测：无支撑且垂直速度超过阈值即拉回。"""
        vy = self._get_vertical_speed(name, pos, now)
        if vy <= self.cfg["上升速度阈值"]:
            return
        if self._is_unsupported(name):
            fmts.print_war(
                f"[反作弊] {name} 上升速度异常！垂直速度={vy:.5f} m/s"
                f"（阈值{self.cfg['上升速度阈值']}）"
            )
            self._rollback(name)

    def _check_speed(self, name: str, pos: dict, now: float) -> None:
        """水平速度检测：区分骑马与普通移动，超阈值即拉回。"""
        h_speed = self._get_horizontal_speed(name, pos, now)
        if h_speed is None:
            return
        if self._is_riding(name):
            threshold = self.cfg.get("骑马速度水平阈值", 25.0)
            if h_speed > threshold:
                fmts.print_war(
                    f"[反作弊] {name} 骑马时速度异常！速度={h_speed:.5f} m/s"
                    f"（阈值{threshold}）"
                )
                self._rollback(name)
        else:
            threshold = self.cfg["速度异常水平阈值"]
            if h_speed > threshold:
                fmts.print_war(
                    f"[反作弊] {name} 水平速度异常！速度={h_speed:.5f} m/s"
                    f"（阈值{threshold}）"
                )
                self._rollback(name)

    def _check_acceleration(self, name: str, pos: dict, now: float) -> None:
        """加速度检测：水平或垂直加速度超阈值（且非正常下落）即拉回。"""
        h_acc, v_acc = self._get_acceleration(name)
        h_threshold = self.cfg["加速度异常水平阈值"]
        v_threshold = self.cfg["加速度异常垂直阈值"]

        if h_acc is not None:
            if h_acc > h_threshold:
                fmts.print_war(
                    f"[反作弊] {name} 加速度异常！水平={h_acc:.5f} m/s²"
                    f"（阈值{h_threshold}）"
                )
                self._rollback(name)
                return
            if v_acc > v_threshold:
                if 18 < v_acc < 22:
                    vy = self._get_vertical_speed(name, pos, now)
                    if vy < 0:
                        return
                fmts.print_war(
                    f"[反作弊] {name} 加速度异常！垂直={v_acc:.5f} m/s²"
                    f"（阈值{v_threshold}）"
                )
                self._rollback(name)

    def _check_flight(self, name: str, pos: dict, now: float) -> None:
        """飞行检测：无支撑且无有效下落/跳跃趋势时判定为悬空飞行。"""
        if not self._is_unsupported(name):
            return

        if not self._has_enough_air_time(name, now):
            return

        h_speed = self._get_horizontal_speed(name, pos, now) or 0.0
        vy = self._get_vertical_speed(name, pos, now)

        # 静止悬停
        if h_speed < 0.1 and abs(vy) < 0.1:
            fmts.print_war(f"[反作弊] {name} 疑似静止悬停，高度={pos['y']:.5f}")
            self._rollback(name, smart=True)
            return

        # 缓降或快速下落豁免
        if (h_speed < 0.5 and vy < 0) or vy < self.cfg["飞行最小下落速度"]:
            return

        old_y = self._get_old_y(name, now)
        if old_y is not None:
            dy = pos["y"] - old_y
            if dy < self.cfg["飞行最大可通过下落"]:
                return
            if vy > 0 and dy > self.cfg["飞行跳跃上升阈值"]:
                return

        if h_speed < self.cfg["飞行最小水平速度"]:
            return

        dy_show = pos["y"] - old_y if old_y is not None else 0.0
        fmts.print_war(
            f"[反作弊] {name} 疑似飞行（悬空），水平速度={h_speed:.5f}，"
            f"垂直速度={vy:.5f}，高度={pos['y']:.5f}，2秒下落={dy_show:.5f}"
        )
        self._rollback(name, smart=True)

    def _has_enough_air_time(self, name: str, now: float) -> bool:
        """检查悬空时间是否超过阈值。"""
        min_air_time = self.cfg.get("飞行最小悬空秒数", 0.5)
        history = self.pos_history.get(name)
        last_ground_time = None
        if history and len(history) > 0:
            last_ground_time = history[-1][3]
        elif name in self.last_pos:
            last_ground_time = self.last_pos[name][3]

        if last_ground_time is None:
            return True
        return (now - last_ground_time) >= min_air_time

    def _get_old_y(self, name: str, now: float):
        """获取过去一段时间前的 Y 坐标（用于判断下落/跳跃趋势）。"""
        lookback = self.cfg["飞行下落检测秒数"]
        target_time = now - lookback
        last = self.last_pos.get(name)
        if last and (now - last[3]) <= lookback:
            return last[1]

        old_pos = self._get_position_at(name, target_time)
        if old_pos is not None:
            return old_pos[1]
        old_pos_r = self._get_position_at(name, target_time, use_rollback=True)
        if old_pos_r is not None:
            return old_pos_r[1]
        return None

    def _check_groundfly(self, name: str, pos: dict, now: float) -> None:
        """平地飞检测：地面高速移动或异常水平加速度。"""
        if self.cfg.get("速度检测下落豁免", True):
            vy = self._get_vertical_speed(name, pos, now)
            if vy < self.cfg["飞行最小下落速度"]:
                return

        history = self.pos_history.get(name)
        if not history or len(history) < 5:
            return

        recent = [p for p in history if now - p[3] <= 3.0]
        if len(recent) < 3:
            return

        if self._has_large_y_variation(recent):
            return

        last = self.last_pos.get(name)
        if not last:
            return
        last_x, _, last_z, last_t = last
        dt = now - last_t
        if dt <= 0:
            return
        h_speed = math.hypot(pos["x"] - last_x, pos["z"] - last_z) / dt

        if h_speed > self.cfg["平地飞水平速度阈值"]:
            fmts.print_war(
                f"[反作弊] {name} 疑似平地飞，水平速度={h_speed:.5f}"
            )
            self._rollback(name)
            return

        if h_speed > 5.0 and len(recent) >= 4:
            h_acc = self._calc_horizontal_acceleration(recent)
            if h_acc > self.cfg["平地飞水平加速度阈值"]:
                fmts.print_war(
                    f"[反作弊] {name} 水平加速度异常={h_acc:.5f}，"
                    f"水平速度={h_speed:.5f}"
                )
                self._rollback(name)

    def _has_large_y_variation(self, recent_points: list) -> bool:
        """检查最近坐标的 Y 标准差是否过大（跳跃/地形）。"""
        ys = [p[1] for p in recent_points]
        mean_y = sum(ys) / len(ys)
        variance = sum((y - mean_y) ** 2 for y in ys) / len(ys)
        return variance ** 0.5 > self.cfg["平地飞Y轴标准差阈值"]

    @staticmethod
    def _calc_horizontal_acceleration(recent_points: list) -> float:
        """根据最近四个点计算水平加速度。"""
        mid = len(recent_points) // 2
        dt_half = (recent_points[-1][3] - recent_points[0][3]) / 2
        if dt_half <= 0:
            return 0.0
        v1 = math.hypot(
            recent_points[mid][0] - recent_points[0][0],
            recent_points[mid][2] - recent_points[0][2]
        ) / dt_half
        v2 = math.hypot(
            recent_points[-1][0] - recent_points[mid][0],
            recent_points[-1][2] - recent_points[mid][2]
        ) / dt_half
        return (v2 - v1) / dt_half

    def _check_bounce(self, name: str, pos: dict, now: float) -> None:
        """回弹飞行检测：周期性上下波动且水平移动。"""
        history = self.pos_history.get(name)
        if not history or len(history) < 5:
            return
        duration = self.cfg["回弹飞最小持续秒数"]
        recent = [p for p in history if now - p[3] <= duration]
        if len(recent) < 4:
            return

        cycles, avg_amplitude = self._analyze_bounce(recent)
        if cycles < self.cfg["回弹飞最小波动次数"]:
            return
        if not (self.cfg["回弹飞最小波幅"]
                <= avg_amplitude
                <= self.cfg["回弹飞最大波幅"]):
            return

        h_speed = self._calc_horizontal_speed_from_recent(recent)
        if h_speed < self.cfg["回弹飞最低水平速度"]:
            return

        fmts.print_war(
            f"[反作弊] {name} 疑似回弹飞行！波动次数={cycles}，"
            f"平均振幅={avg_amplitude:.5f}，水平速度={h_speed:.5f}"
        )
        self._rollback(name)

    @staticmethod
    def _analyze_bounce(points: list) -> tuple:
        """分析坐标序列的波峰波谷，返回(完整周期数, 平均振幅)。"""
        ys = [p[1] for p in points]
        peaks = troughs = 0
        for i in range(1, len(ys) - 1):
            if ys[i] > ys[i - 1] and ys[i] > ys[i + 1]:
                peaks += 1
            elif ys[i] < ys[i - 1] and ys[i] < ys[i + 1]:
                troughs += 1

        cycles = min(peaks, troughs)
        amplitudes = []
        for i in range(1, len(ys) - 1):
            if ys[i] > ys[i - 1] and ys[i] > ys[i + 1]:
                left_trough = min(ys[i - 1], ys[i])
                right_trough = min(ys[i + 1], ys[i])
                amp = (ys[i] - left_trough + ys[i] - right_trough) / 2
                if amp > 0:
                    amplitudes.append(amp)

        if not amplitudes:
            return 0, 0.0
        return cycles, sum(amplitudes) / len(amplitudes)

    @staticmethod
    def _calc_horizontal_speed_from_recent(points: list) -> float:
        """从最近的两个点计算水平速度。"""
        dx = points[-1][0] - points[0][0]
        dz = points[-1][2] - points[0][2]
        dt = points[-1][3] - points[0][3]
        if dt <= 0:
            return 0.0
        return math.hypot(dx, dz) / dt

    def _check_predict_move(self, name: str, pos: dict, now: float) -> None:
        """移动预测检测：基于历史轨迹预测位置，偏差过大即拉回。"""
        if self.cfg.get("速度检测下落豁免", True):
            vy_current = self._get_vertical_speed(name, pos, now)
            if vy_current < self.cfg["飞行最小下落速度"]:
                return

        history = self.pos_history.get(name)
        if not history or len(history) < 4:
            return
        p0, p1, p2, _ = list(history)[-4:]
        dt1 = p1[3] - p0[3]
        dt2 = p2[3] - p1[3]
        if dt1 <= 0 or dt2 <= 0:
            return

        vx1 = (p1[0] - p0[0]) / dt1
        vy1 = (p1[1] - p0[1]) / dt1
        vz1 = (p1[2] - p0[2]) / dt1
        vx2 = (p2[0] - p1[0]) / dt2
        vy2 = (p2[1] - p1[1]) / dt2
        vz2 = (p2[2] - p1[2]) / dt2

        avg_vx = (vx1 + vx2) / 2
        avg_vy = (vy1 + vy2) / 2
        avg_vz = (vz1 + vz2) / 2

        predict_dt = self.cfg["预测时间_秒"]
        predicted_x = p2[0] + avg_vx * predict_dt
        predicted_y = p2[1] + avg_vy * predict_dt
        predicted_z = p2[2] + avg_vz * predict_dt

        actual_x, actual_y, actual_z = pos["x"], pos["y"], pos["z"]
        dist = math.hypot(
            actual_x - predicted_x,
            actual_y - predicted_y,
            actual_z - predicted_z
        )
        speed = math.hypot(avg_vx, avg_vy, avg_vz)

        threshold = (
            self.cfg["预测基础误差_米"]
            + speed * self.cfg["预测速度误差因子"]
        )
        speed1 = math.hypot(vx1, vy1, vz1)
        speed2 = math.hypot(vx2, vy2, vz2)
        max_speed = max(speed1, speed2)
        if max_speed > 0:
            speed_change_ratio = abs(speed2 - speed1) / max_speed
        else:
            speed_change_ratio = 0
        if speed_change_ratio > self.cfg["预测速度稳定性阈值"]:
            threshold *= self.cfg["预测速度不稳定放宽因子"]

        if speed > 0:
            dot = vx1 * vx2 + vz1 * vz2
            mag = math.hypot(vx1, vz1) * math.hypot(vx2, vz2)
            if mag > 0:
                cos_angle = max(-1, min(1, dot / mag))
                angle = math.acos(cos_angle)
                if angle > math.radians(90):
                    threshold *= 2.0

        if dist > threshold:
            fmts.print_war(
                f"[反作弊] {name} 移动预测异常：偏差={dist:.5f} 米"
                f"（阈值{threshold:.5f}），速度={speed:.5f} m/s"
            )
            self._rollback(name)


entry = plugin_entry(SimpleAntiCheat, "反作弊-移动检测")