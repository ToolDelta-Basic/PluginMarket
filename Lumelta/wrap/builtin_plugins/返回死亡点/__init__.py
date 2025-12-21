# Lumega内置插件示例：返回死亡点

import time
import json
from tooldelta import Plugin, plugin_entry, utils
from tooldelta.utils.cfg import get_plugin_config_and_version, upgrade_plugin_config, check_auto, auto_to_std

class ReturnDeathPointPlugin(Plugin):
    name = "返回死亡点"
    author = "Yeah"
    version = (0, 0, 2) # 与配置的 Version 相同

    def __init__(self, frame):
        super().__init__(frame)
        self.default = {
            "不满足返回死亡点玩家选择器时提示": "不满足返回条件!",
            "复活时执行指令": [
                "tell [player] 你逝于 [dead_dimension] 维度的 [dead_pos], 不要灰心喔!"
            ],
            "提示信息": "你逝于 [dead_dimension] 维度的 [dead_pos], 要重返那里么?",
            "死亡玩家选择器": "@a[rm=0.01,name=[player]]",
            "满足返回死亡点玩家选择器时提示": "你即将被传送至死亡点",
            "询问是否返回死亡点": True,
            "输入有误时提示": "无法理解你的回答, 因为[error]",
            "返回死亡点后执行指令": [
                "tell @a[name=[player]] 已成功将你传送回死亡点, 继续探索吧!"
            ],
            "返回死亡点指令": [
                {
                    "备注": "WO指令会在主世界执行, 配合rm=0.01限制仅主世界可传送, 可能需要随机巡逻将机器人固定在主世界",
                    "指令": "execute in [dead_dimension] run tp [player] [dead_pos]",
                    "身份": "WO"
                }
            ],
            "返回死亡点玩家选择器": "@a[name=[player]]"
        }
        self.standard_type = auto_to_std(self.default)
        self.dimensions = ["overworld", "nether", "the_end"]
        self.yes = ["是", "Y", "y"]
        self.no = ["否", "N", "n"]
        self.identity_map = {
            "Player": self.frame.game_ctrl.sendcmd,
            "WS": self.frame.game_ctrl.sendwscmd,
            "WO": self.frame.game_ctrl.sendwocmd
        }
        # 如果要获取配置和更新配置，必须按照下面的方法
        # 在运行时下面的方法会被修改为正确的（必须是这两个键名）
        self.get_plugin_config_and_version = get_plugin_config_and_version
        self.upgrade_plugin_config = upgrade_plugin_config
        self.ListenActive(self.active)

    # 加载内置插件的时候已经完成了 Preload 操作，所以初始化应该写在 Active 里面
    def active(self):
        self.config, self.config_version = self.get_plugin_config_and_version(
            self.name, self.standard_type, self.default, self.version
        )
        self.frame.packet_handler.add_dict_packet_listener(9, self.intercept)

    def _replace_keywords(self, string, replacements):
        """统一的关键词替换方法"""
        for key, value in replacements.items():
            string = string.replace(f"[{key}]", str(value))
        return string

    def execute_commands(self, commands, replacements):
        """执行命令列表的模块化函数"""
        for cmd_entry in commands:
            # 解析命令条目
            if isinstance(cmd_entry, dict):
                cmd = cmd_entry.get("指令", "")
                identity = cmd_entry.get("身份", "WS")
            else:
                cmd = cmd_entry
                identity = "WS"

            # 获取发送方法
            send_func = self.identity_map.get(identity, self.frame.game_ctrl.sendwscmd)

            # 执行关键词替换
            formatted_cmd = self._replace_keywords(cmd, replacements)

            # 执行命令
            try:
                send_func(formatted_cmd)
            except Exception as e:
                self.print(f"执行命令时出错: {str(e)}")

    def handle_death(self, player_name, dead_dimension, dead_pos):
        """处理死亡逻辑的模块化函数"""
        player = self.frame.game_ctrl.players.getPlayerByName(player_name)
        replacements = {
            "player": f'"{player_name}"',
            "dead_dimension": dead_dimension,
            "dead_pos": dead_pos
        }

        # 执行复活时指令
        self.execute_commands(self.config["复活时执行指令"], replacements)

        # 处理返回逻辑
        if self.config["询问是否返回死亡点"]:
            # 构建提示信息
            prompt = self._replace_keywords(self.config["提示信息"], replacements)
            response = player.input(prompt, 60)
            
            if not response:
                error_msg = self._replace_keywords(
                    self.config["输入有误时提示"],
                    {"error": "超时"}
                )
                player.show(error_msg)
                return
            if response in self.no:
                return
            if response not in self.yes:
                error_msg = self._replace_keywords(
                    self.config["输入有误时提示"],
                    {"error": "无效的输入"}
                )
                player.show(error_msg)
                return

        # 检查返回条件
        target_selector = self._replace_keywords(
            self.config["返回死亡点玩家选择器"],
            replacements
        )
        resp = self.frame.game_ctrl.sendwscmd_with_resp(f"/testfor {target_selector}")
        if resp.SuccessCount == 0:
            error_msg = self._replace_keywords(
                self.config["不满足返回死亡点玩家选择器时提示"],
                replacements
            )
            player.show(error_msg)
        else:
            success_msg = self._replace_keywords(
                self.config["满足返回死亡点玩家选择器时提示"],
                replacements
            )
            player.show(success_msg)
            self.execute_commands(self.config["返回死亡点指令"], replacements)

    def intercept(self, packet):
        @utils.thread_func("返回死亡点")
        def handle():
            if packet["TextType"] == 2 and packet["NeedsTranslation"] and "death" in packet["Message"]:
                player_name = packet["Parameters"][0]
                target_selector = self._replace_keywords(
                    self.config["死亡玩家选择器"],
                    {"player": f'"{player_name}"'}
                )

                # 获取坐标信息
                resp = self.frame.game_ctrl.sendwscmd_with_resp(f"/querytarget {target_selector}")
                if not resp.OutputMessages[0].Success:
                    self.print(f"无法获取坐标信息：{resp.OutputMessages[0].Message}")
                    return

                # 解析坐标数据
                try:
                    param_str = resp.OutputMessages[0].Parameters[0]
                    parameter = json.loads(param_str)
                    if isinstance(parameter, str):
                        raise ValueError(f"无效的坐标数据: {param_str}")
                except Exception as e:
                    self.print(f"坐标解析失败：{str(e)}")
                    return

                pos_data = parameter[0]["position"]
                dimension_id = parameter[0]["dimension"]

                # 计算坐标
                x = int(pos_data["x"]) if pos_data["x"] >= 0 else int(pos_data["x"] - 1)
                y = int(pos_data["y"] - 1.6200103759765)
                z = int(pos_data["z"]) if pos_data["z"] >= 0 else int(pos_data["z"] - 1)

                # 确定维度名称
                dead_dimension = (
                    self.dimensions[dimension_id]
                    if dimension_id < len(self.dimensions)
                    else f"dim{dimension_id}"
                )
                dead_pos = f"{x} {y} {z}"

                # 等待玩家复活
                while True:
                    resp = self.frame.game_ctrl.sendwscmd_with_resp(f"/testfor {target_selector}")
                    if resp.SuccessCount != 0:
                        break
                    time.sleep(3)

                # 处理后续逻辑
                self.handle_death(player_name, dead_dimension, dead_pos)

        handle()
        return False

entry = plugin_entry(ReturnDeathPointPlugin)