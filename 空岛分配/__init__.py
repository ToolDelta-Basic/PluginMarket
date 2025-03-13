from tooldelta import (
    Plugin,
    cfg,
    Print,
    Frame,
    game_utils,
    utils,
    Chat,
    plugin_entry,
)

from tooldelta.internal.launch_cli import FrameNeOmgAccessPoint
import time, json, os

TMPJson = utils.TMPJson


class Sky_Island_Allocation(Plugin):
    name = "空岛分配"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._default_cfg = {
            "提示": "更改了配置文件后想要生效必须删除数据文件中的空岛数据.json然后reload",
            "分配提示词": "分配空岛",
            "起点坐标": (0, 0, 0),
            "玩家传送坐标偏移": (0, 0, 0),
            "空岛x方向数量": 100,
            "空岛z方向数量": 100,
            "空岛间距(区块)": 100,
            "结构名字": "空岛模板",
            "临时常加载名字": "Temp",
            "空岛唯一性": True,
            "重复分配提示": "你已经分配过空岛了",
            "正在分配提示": "检查成功，正在分配空岛",
            "分配成功提示": "分配成功",
            "空岛分配上限提示": "已无可供分配空岛",
        }
        self._std_cfg = {
            "提示": str,
            "分配提示词": str,
            "起点坐标": list,
            "玩家传送坐标偏移": list,
            "空岛x方向数量": int,
            "空岛z方向数量": int,
            "空岛间距(区块)": int,
            "结构名字": str,
            "临时常加载名字": str,
            "空岛唯一性": bool,
            "重复分配提示": str,
            "正在分配提示": str,
            "分配成功提示": str,
            "空岛分配上限提示": str,
        }
        try:
            self._cfg, _ = cfg.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )
        except Exception as e:
            Print.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()
        data_dir = self.data_path
        data_path = os.path.join(data_dir, "空岛数据.json")
        self.Sky_Island_data = []
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                self.Sky_Island_data = json.load(f)
        except Exception as e:
            self.Sky_Island_data = [
                {
                    "是否分配": False,
                    "玩家信息": {"player_uuid": None, "player_name": None},
                    "x": x * self._cfg["空岛间距(区块)"] * 16
                    + self._cfg["起点坐标"][0],
                    "y": self._cfg["起点坐标"][1],
                    "z": z * self._cfg["空岛间距(区块)"] * 16
                    + self._cfg["起点坐标"][2],
                }
                for x in range(self._cfg["空岛x方向数量"])
                for z in range(self._cfg["空岛z方向数量"])
            ]
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(self.Sky_Island_data, f, indent=4, ensure_ascii=False)
        self.ListenChat(self.on_player_message)

    def on_player_message(self, chat: Chat):
        player_name = chat.player.name
        msg = chat.msg

        if msg == self._cfg["分配提示词"]:
            player_uuid = self.game_ctrl.players_uuid[player_name]
            with open(self.data_path + "/空岛数据.json", "r", encoding="utf-8") as f:
                Sky_Island_data = json.load(f)
            if self._cfg["空岛唯一性"]:
                for i in range(len(Sky_Island_data)):
                    if Sky_Island_data[i]["玩家信息"]["player_uuid"] == player_uuid:
                        self.game_ctrl.say_to(player_name, self._cfg["重复分配提示"])
                        return
            for i in range(len(Sky_Island_data)):
                if not Sky_Island_data[i]["是否分配"]:
                    self.game_ctrl.say_to(player_name, self._cfg["正在分配提示"])
                    self.game_ctrl.sendwocmd(
                        f"/tickingarea add circle {Sky_Island_data[i]['x']} 0 {Sky_Island_data[i]['z']} 4 {self._cfg['临时常加载名字']}"
                    )
                    time.sleep(1)
                    self.game_ctrl.sendwocmd(
                        f"/structure load {self._cfg['结构名字']} {Sky_Island_data[i]['x']} {self._cfg['起点坐标'][1]} {Sky_Island_data[i]['z']}"
                    )
                    self.game_ctrl.sendwocmd(
                        f"/tickingarea remove {self._cfg['临时常加载名字']}"
                    )
                    Sky_Island_data[i]["是否分配"] = True
                    Sky_Island_data[i]["玩家信息"]["player_uuid"] = player_uuid
                    Sky_Island_data[i]["玩家信息"]["player_name"] = player_name
                    self.game_ctrl.say_to(player_name, self._cfg["分配成功提示"])
                    self.game_ctrl.sendwocmd(
                        f"/tp {player_name} {Sky_Island_data[i]['x'] + self._cfg['玩家传送坐标偏移'][0]} {Sky_Island_data[i]['y'] + self._cfg['玩家传送坐标偏移'][1]} {Sky_Island_data[i]['z'] + self._cfg['玩家传送坐标偏移'][2]}"
                    )
                    break
            with open(self.data_path + "/空岛数据.json", "w", encoding="utf-8") as f:
                json.dump(Sky_Island_data, f, indent=4, ensure_ascii=False)
        return


entry = plugin_entry(Sky_Island_Allocation)
