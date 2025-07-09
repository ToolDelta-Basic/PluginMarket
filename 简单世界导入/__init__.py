import os
import json
import threading
import time
import uuid
from tooldelta import (
    FrameExit,
    Plugin,
    Frame,
    fmts,
    utils,
    plugin_entry,
)
from tooldelta.utils.tooldelta_thread import ToolDeltaThread


class SimpleWorldImport(Plugin):
    name = "简单世界导入"
    author = "YoRHa"
    version = (0, 2, 0)

    should_close: bool = False
    running_mutex: threading.Lock

    flowers_for_machines: "FlowersForMachine | None"
    _chest_cache_requester: str

    def __init__(self, frame: Frame):
        self.frame = frame
        self.game_ctrl = frame.get_game_control()

        self.should_close = False
        self.running_mutex = threading.Lock()

        self.flowers_for_machines = None
        self._chest_cache_requester = str(uuid.uuid4())

        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_close)
        self.make_data_path()

    def on_def(self):
        global bwo, nbtlib, FlowersForMachine

        pip = self.GetPluginAPI("pip")
        self.flowers_for_machines = self.GetPluginAPI("献给机械の花束", (1, 0, 0))

        if 0:
            from pip模块支持 import PipSupport
            from 前置_献给机械的花束 import FlowersForMachine

            pip: PipSupport
        pip.require({"bedrock-world-operator": "bedrockworldoperator"})

        import bedrockworldoperator as bwo
        import nbtlib

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["import/"],
            " ".join(
                [
                    "[存档文件夹名(位于 插件数据文件/简易世界导入/)]",
                    "[要导入建筑物所在维度 | 0=主世界, 1=下界, 2=末地]",
                    "[要导入建筑物在存档内的起始坐标 | 形如(x,y,z)]",
                    "[要导入建筑物在存档内的终点坐标 | 形如(x,y,z)]",
                    "[要导入到游戏的哪里 | 形如(x,y,z)]",
                ],
            ),
            "导入存档内的建筑物",
            self.runner,
        )

    def on_close(self, _: FrameExit):
        self.should_close = True
        self.running_mutex.acquire()
        self.running_mutex.release()

    def as_pos(self, string: str) -> tuple[int, int, int]:
        """
        e.g.
            as_pos(self, "(1,2,3)") -> (1, 2, 3)
        """
        s = string.replace("(", "", 1).replace(")", "", 1).split(",")
        return int(s[0]), int(s[1]), int(s[2])

    def get_start_and_end_pos(
        self, start: tuple[int, int, int], end: tuple[int, int, int]
    ) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """
        e.g.
            get_start_and_end_pos(self, (-1, -2, 9), (8, 6, -8))
            ->
            ((-1, -2, -8), (8, 6, 9))
        """
        min_pos = (min(start[0], end[0]), min(start[1], end[1]), min(start[2], end[2]))
        max_pos = (max(start[0], end[0]), max(start[1], end[1]), max(start[2], end[2]))
        return min_pos, max_pos

    def compute_path(self, start: tuple[int, int], end: tuple[int, int]):
        """
        e.g.
            compute_path(self, (0,0), (64,64))
            ->
            [
                (0,0), (1,0), (2,0), (3,0), (4,0),
                (4,1), (3,1), (2,1), (1,1), (0,1),
                (0,2), (1,2), (2,2), (3,2), (4,2),
                (4,3), (3,3), (2,3), (1,3), (0,3),
                (0,4), (1,4), (2,4), (3,4), (4,4)
            ]
        """
        result: list[bwo.ChunkPos] = []

        start_chunk_pos = (start[0] >> 4, start[1] >> 4)
        end_chunk_pos = (end[0] >> 4, end[1] >> 4)
        direction = 1

        for z in range(start_chunk_pos[1], end_chunk_pos[1] + 1):
            if direction == 1:
                for x in range(start_chunk_pos[0], end_chunk_pos[0] + 1):
                    result.append(bwo.ChunkPos(x, z))
            else:
                for x in range(end_chunk_pos[0], start_chunk_pos[0] - 1, -1):
                    result.append(bwo.ChunkPos(x, z))
            direction *= -1

        return result

    def is_include(
        self,
        pos: tuple[int, int, int],
        start: tuple[int, int, int],
        end: tuple[int, int, int],
    ) -> bool:
        """is_include checks whether pos is within the cuboid area enclosed by start and end"""
        return (
            start[0] <= pos[0] <= end[0]
            and start[1] <= pos[1] <= end[1]
            and start[2] <= pos[2] <= end[2]
        )

    def as_block_states_string(self, states) -> str:  # type: ignore
        """
        as_block_states_string convert states (nbtlib.tag.Compound)
        to string that could used on setblock command.
        """
        states: bwo.Compound
        out = ""

        for i in states:
            v = states[i]
            match type(v):
                case bwo.Int | bwo.String:
                    out += (
                        ","
                        + json.dumps(i, ensure_ascii=False)
                        + "="
                        + json.dumps(v, ensure_ascii=False)
                    )
                case bwo.Byte:
                    if v == 1:
                        out += "," + json.dumps(i, ensure_ascii=False) + "=true"
                    else:
                        out += "," + json.dumps(i, ensure_ascii=False) + "=false"

        return "[" + out[1:] + "]"

    def send_build_command(self, pos: tuple[int, int, int], block_runtime_id):
        """
        send_build_command make the bot place a block whose block runtime id
        is block_runtime_id at position (pos[0], pos[1], pos[2]).
        """
        block_states = bwo.runtime_id_to_state(block_runtime_id)
        try:
            self.game_ctrl.sendwocmd(
                f"setblock {pos[0]} {pos[1]} {pos[2]} {block_states.Name} {self.as_block_states_string(block_states.States)}"
            )
        except Exception:
            pass

    @utils.thread_func("世界导入进程", thread_level=ToolDeltaThread.SYSTEM)
    def do_world_import(self, cmd: list[str]):
        if self.flowers_for_machines is None:
            fmts.print_err("do_world_import: Should nerver happened")
            return

        if not self.running_mutex.acquire(timeout=0):
            fmts.print_err("同一时刻最多处理一个导入任务")
            return

        if not self.should_close:
            self._do_world_import(cmd)
            self.flowers_for_machines.get_chest_cache().remove_all_chests(
                self._chest_cache_requester
            )

        self.running_mutex.release()

    def _do_world_import(self, cmd: list[str]):
        if self.flowers_for_machines is None:
            fmts.print_err("_do_world_import: Should nerver happened")
            return

        try:
            filename = cmd[0]
            if not filename.endswith(".mcworld"):
                filename.removesuffix(".mcworld")
            world_path = self.format_data_path(filename)
            dm = bwo.Dimension(int(cmd[1]))

            # start_pos 和 end_pos 是原始存档中建筑物的起止坐标
            start_pos, end_pos = self.get_start_and_end_pos(
                self.as_pos(cmd[2]), self.as_pos(cmd[3])
            )

            # result_start_pos 是导入点,
            # 而 result_end_pos 是计算得到的, 导入后的终止坐标
            result_start_pos = self.as_pos(cmd[4])
            result_end_pos = (
                result_start_pos[0] + (end_pos[0] - start_pos[0]),
                result_start_pos[1] + (end_pos[1] - start_pos[1]),
                result_start_pos[2] + (end_pos[2] - start_pos[2]),
            )
        except Exception as err:
            fmts.print_err(f"命令参数不足或填写不正确: {err}")
            return

        if not os.path.isdir(world_path):
            fmts.print_err(f"未找到路径为 {world_path} 的存档文件夹")
            return

        world = bwo.new_world(world_path)
        if not world.is_valid():
            fmts.print_err(
                "无法打开存档, 请检查存档是否正被使用或 level.dat 文件是否正确"
            )
            return

        # 我们基于要导入的建筑在原始存档的起始坐标和终点坐标,
        # 进行蛇形区块分块, 然后机器人将按照这个路径遍历原始
        # 存档里面的各个区块。
        #
        #   一个可视化图像如下。
        #   ---------------> x
        #   ↓ 00 01 02 03
        #   ↓ 07 06 05 04
        #   ↓ 08 09 10 11
        #   ↓ 15 14 13 12
        #   z
        #
        bot_path = self.compute_path(
            (start_pos[0], start_pos[2]),
            (end_pos[0], end_pos[2]),
        )

        progress = 0
        for origin_chunk_pos in bot_path:
            # 检查用户是否重载
            if self.should_close:
                world.close_world()
                return

            # 显示处理进度
            finish_ratio = round(progress / (len(bot_path)) * 100)
            fmts.print_inf(f"正在处理 {origin_chunk_pos} 处的区块 ({finish_ratio}%)")
            progress += 1

            # 尝试加载遍历到的区块
            chunk = world.load_chunk(origin_chunk_pos, dm)
            chunk_range = chunk.range()
            if not chunk.is_valid():
                fmts.print_war(f"位于 {origin_chunk_pos} 的区块没有找到, 跳过")
                continue

            # (sub_x, sub_z) 相对于当前正在处理的区
            # 块的原点的“平面方块相对坐标”是 (0, 0)
            sub_x = origin_chunk_pos.x << 4
            sub_z = origin_chunk_pos.z << 4

            # sub-start_pos 先计算出相对于原始存档的坐标。
            # 完了后, 再加上 result_start_pos 以将坐标系
            # 转换到以实际导入地点为原点时的绝对坐标
            pen_x = sub_x - start_pos[0] + result_start_pos[0]
            pen_z = sub_z - start_pos[2] + result_start_pos[2]

            # 加载 NBT 方块，
            # 并保存方块坐标到 NBT 方块数据的映射。
            # 注：这个坐标是 实际导入 时的方块坐标
            nbts = world.load_nbt(origin_chunk_pos, dm)
            block_pos_to_nbt: dict[tuple[int, int, int], nbtlib.tag.Compound] = {}
            for i in nbts:
                posx = int(i["x"]) - start_pos[0] + result_start_pos[0]
                posy = int(i["y"]) - start_pos[1] + result_start_pos[1]
                posz = int(i["z"]) - start_pos[2] + result_start_pos[2]
                block_pos_to_nbt[(posx, posy, posz)] = i

            try:
                pen_position_str = f"{pen_x} {result_start_pos[1]} {pen_z}"
                # 我们现在已经准备好处理 origin_chunk_pos 所指示的区块了,
                # 然后计算得到这个区块在目标导入地点的平面坐标是 (pen_x, pen_z),
                # 于是我们把机器人 tp 到这个区块以做好准备
                self.game_ctrl.sendwocmd(
                    f'execute as @a[name="{self.game_ctrl.bot_name}"] at @s run tp {pen_position_str}'
                )
                # 发送指令等待返回, 让机器人确保在进行下一步前租赁服已经将机器人传送到目标地点
                # 对于租赁服较为卡顿的时候, 它的作用尤为明显
                self.game_ctrl.sendwscmd_with_resp("testforblock ~ ~ ~ air")
            except Exception:
                pass

            # 我们严格区分 区块 和 子区块, 因为子区块实际上只是一个 16*16*16 的区域,
            # 但整个区块可以是 16*16*384 的区域。但不管怎么样, 游戏储存区块的最细颗粒度
            # 是 子区块 而非 区块, 这一点需要重点关注！
            #
            # 我们目前已经是在一个“区块”中了, 然后下一步是遍历这个区块里面的所有子区块。
            # 然而, 并非这个区块里面所有的子区块都需要遍历, 因为用户可能只导入其中一部分
            # 的高度, 于是我们用 start_pos[1] >> 4 得到起始子区块的 Y 坐标, 然后用
            # end_pos[1] >> 4 求出终止子区块的 Y 坐标, 然后循环即可。
            #
            # 需要额外关注的是, 用户可能会提供超越当前区块高度范围的值, 所以这里用 min 确保范围不会超限。
            # 另外, 上面说的子区块 Y 坐标并不是 方块坐标, 方块坐标可以是 -64~319 之间的数,
            # 而子区块的 Y 坐标只可能是 -64>>4 到 319>>4 之间的数。
            # -64>>4 到 319>>4 只是个例子！因为整个区块的高度限制还取决于维度
            for sub_y_pos in range(
                start_pos[1] >> 4,
                min((chunk_range.end_range >> 4) + 1, (end_pos[1] >> 4) + 1),
            ):
                # 检查用户是否重载
                if self.should_close:
                    world.close_world()
                    return

                # 由于每次子区块的 Y 坐标都会变化,
                # 所以每次都有必要重新通过转换坐标系
                # 以得到以实际导入地点为原点时的绝对 Y 坐标。
                #
                # 前面的 X 和 Z 坐标只转换一次是因为
                # 我们目前是在操作一个区块内的子区块,
                # 而不是跨区块的操作
                sub_y = sub_y_pos << 4
                pen_y = sub_y - start_pos[1] + result_start_pos[1]

                # 上面的 min 只确保用户提供的导入范围不会高于当前区块的高度范围,
                # 但实际上也可能低于, 然后这里进行了判断。
                # 需要明确说明的是, 如果不进行范围检查, 直接去请求这片无效子区块
                # 会导致整个程序都崩掉, 无论是否有使用 try 语句
                if chunk_range.start_range > sub_y:
                    continue

                # 然后, 现在我们可以舒适的访问目标子区块了
                sub_chunk = chunk.sub_chunk(sub_y)
                if not sub_chunk.is_valid():
                    fmts.print_war(
                        f"位于 ({origin_chunk_pos.x},{sub_y_pos},{origin_chunk_pos.z}) 的子区块没有找到, 跳过"
                    )
                    continue

                # 这个子区块是空的（全是空气）,
                # 所以完全安全地跳过
                if sub_chunk.empty():
                    continue

                # 现在, 我们获取这个子区块前景层和背景层的方块。
                # 正常情况下, 大多数方块都集中在前景层, 并且不使用背景层。
                # 一般而言, 只有含水方块会使用背景层, 并且背景层就是水方块
                forceground_blocks = sub_chunk.blocks(0)
                background_blocks = sub_chunk.blocks(1)

                for comb_pos in range(4096):
                    # 检查用户是否重载
                    if self.should_close:
                        world.close_world()
                        return

                    # 其实原来的写法是这样的
                    # for y in range(16):
                    #     for z in range(16):
                    #         for x in range(16):
                    #             ...
                    # 不过这样三层套下来缩进有点太难看了,
                    # 于是用的下面的方式来计算 x y z。
                    #
                    # 不知道你还记不记得, 我们目前正在访问的
                    # 是一个子区块, 而子区块的尺寸永远是 16*16*16,
                    # 于是我们可以计算出 x y z 的值了。
                    #
                    # 但可能你觉得下面的写法很抽象,
                    # 因为全都是位运算......
                    # 好吧, 实际上它们的原版写法是这样的：
                    #       y = comb_pos//(16*16)
                    #       z = (comb_pos % (16*16)) // 16
                    #       x = comb_pos % 16
                    #
                    # 那为什么就变成下面的这么复杂了呢？
                    # 因为 16*16 是 256, 是 2 的 8 次幂,
                    # 然后就可以用移位代替整除了。
                    # 关于模运算的部分, 其实它也是类似的思维方式
                    y = comb_pos >> 8
                    z = (comb_pos - ((comb_pos >> 8) << 8)) >> 4
                    x = comb_pos - ((comb_pos >> 4) << 4)

                    # 把 (pen_x, pen_y, pen_z) 加上 x y z 偏移后,
                    # 就是当前方块实际要导入的坐标了
                    final_pos = (pen_x + x, pen_y + y, pen_z + z)

                    # 这里需要检验一下当前方块的位置是否是用户要导入的区域,
                    # 如果不是就可以直接跳过了
                    if not self.is_include(
                        final_pos,
                        result_start_pos,
                        result_end_pos,
                    ):
                        continue

                    # 拿一下前景层和背景层的方块运行时 ID
                    rid0 = forceground_blocks.block(x, y, z)
                    rid1 = background_blocks.block(x, y, z)

                    # 这个可能是一个 NBT 方块，
                    # 因此我们提前开一些变量以方便后边的赋值
                    nbt_block_structure_id = ""
                    is_chest_block = False
                    place_nbt_block_success = False

                    # 如果前景层和背景层都是空气,
                    # 那么我们可以不用管了, 直接跳过
                    if (
                        rid0 == bwo.AIR_BLOCK_RUNTIME_ID
                        and rid1 == bwo.AIR_BLOCK_RUNTIME_ID
                    ):
                        continue

                    # 背景层不是空气, 说明可能是含水方块的水方块,
                    # 我们需要优先放置水方块, 然后再放置被含的方块
                    if rid1 != bwo.AIR_BLOCK_RUNTIME_ID:
                        self.send_build_command(final_pos, rid1)

                    # 如果这是一个 NBT 方块
                    if final_pos in block_pos_to_nbt:
                        states = bwo.runtime_id_to_state(rid0)
                        if "chest" in states.Name:
                            is_chest_block = True

                        resp = (
                            self.flowers_for_machines.place_nbt_block.place_nbt_block(
                                final_pos,
                                states.Name,
                                self.as_block_states_string(states.States),
                                block_pos_to_nbt[final_pos],
                            )
                        )
                        if not resp.success:
                            fmts.print_war(
                                f"简单世界导入: 处理 {final_pos} 处的 NBT 方块时出现错误"
                            )

                        place_nbt_block_success = resp.success
                        if not resp.can_fast:
                            nbt_block_structure_id = resp.structure_unique_id
                    # 正常放置前景层的方块
                    else:
                        self.send_build_command(final_pos, rid0)

                    # 如果这是箱子，我们尝试测试它是否是大箱子。
                    # 如果是大箱子，让我们开始进行特殊的处理
                    if is_chest_block and place_nbt_block_success:
                        # 取得箱子缓存数据集
                        chest_cache = self.flowers_for_machines.get_chest_cache()
                        # 先把当前这个箱子变成 PairChest
                        pair_chest = chest_cache.nbt_to_chest(
                            final_pos, block_pos_to_nbt[final_pos]
                        )
                        # 如果 pair_chest 不是 None，则这个箱子是大箱子的一部分
                        if pair_chest is not None:
                            # 设置这个箱子对应的结构 Unique ID
                            pair_chest.set_structure_unique_id(nbt_block_structure_id)
                            # 把当前这个箱子加入到箱子缓存数据集
                            chest_cache.add_chest(
                                self._chest_cache_requester, pair_chest
                            )
                            # 试图查找这个箱子的配对是否存在。
                            # 如果存在，则放置大箱子
                            if (
                                chest_cache.find_chest(
                                    self._chest_cache_requester, pair_chest, True
                                )
                                is not None
                            ):
                                # 获取大箱子的方块状态
                                states = bwo.runtime_id_to_state(rid0)
                                # 放置大箱子
                                resp = self.flowers_for_machines.place_large_chest.place_large_chest(
                                    self._chest_cache_requester,
                                    states.Name,
                                    self.as_block_states_string(states.States),
                                    pair_chest,
                                )
                                if not resp.success:
                                    fmts.print_war(
                                        f"简单世界导入: 处理 {final_pos} 处的大箱子时出现错误"
                                    )
                                # 相应的大箱子已经处理完毕了，无论是否成功，我们从箱子缓存中回收它们
                                chest_cache.remove_chest_and_its_pair(
                                    self._chest_cache_requester, pair_chest
                                )

                    # 这里是保证 1 秒钟最多导入 1000 个方块。
                    # 0.001 = 1/1000
                    time.sleep(0.001)

        # 一定要记得关掉打开的存档哟,
        # 千万别忘了
        world.close_world()
        fmts.print_suc("已完成导入")

    def runner(self, cmd: list[str]):
        self.do_world_import(cmd)


entry = plugin_entry(SimpleWorldImport)
