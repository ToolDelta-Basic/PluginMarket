from tooldelta import plugin_entry, Plugin, ToolDelta, game_utils, fmts, Player, utils
import os
import json
import threading

class NewPlugin(Plugin):
    name = "挂机检测"
    author = "衍"
    version = (0, 0, 1)  # 插件版本号, 可选, 是一个三元整数元组

    # 初始化插件类实例
    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.s = 60 # 每隔60秒检测一次玩家坐标
        self.say = "长时间在原地不动判定为挂机"
        self.bot = None # 机器人名称
        self.player_list = dict() # 玩家坐标存储消息

        # 插件读取完成、进入租赁服前
        self.ListenPreload(self.Preload)

        # 有玩家进服
        self.ListenPlayerJoin(self.on_player_join)
        # 有玩家退服
        self.ListenPlayerLeave(self.on_player_leave)

        # 进入租赁服，初始化完成时
        self.ListenActive(self.get_list)






    def Preload(self):
        self.xuid_getter = self.GetPluginAPI("XUID获取")
        from 前置_玩家XUID获取 import XUIDGetter

        self.xuid_getter: XUIDGetter
        if not os.path.isfile("插件配置文件/挂机检测配置.json"):
            fmts.print_load("检测到没有初始文件已加载")
            with open("插件配置文件/挂机检测配置.json", 'w', encoding='utf-8') as f:
                f.write(
"""{
    "配置版本": "0.0.1",
    "配置项": {
        "检测周期/秒": 60,
        "踢出理由": "长时间在原地不动判定为挂机"
    }
}""")

        else:
            with open("插件配置文件/挂机检测配置.json", 'r', encoding='utf-8') as f:
                dict_list = f.read()
                self.s = int(json.loads(dict_list)["配置项"]['检测周期/秒'])
                self.say = json.loads(dict_list)["配置项"]['踢出理由']
                fmts.print_load(f"延迟检测时间是：{self.s}s")


    def get_list(self):
        # 获取机器人名称
        self.bot = self.game_ctrl.bot_name
        name_list = game_utils.getTarget("@a")
        fmts.print_load(f"玩家列表{name_list}")

        # 获取玩家坐标然后存起来用以下次判断时执行
        for id in name_list:
            if id != self.bot:
                player_pos = game_utils.getPosXYZ(id)
                self.player_list[id] = [{"x": player_pos[0], "y": player_pos[1], "z": player_pos[2]}, self.s]

        threading.Timer(self.s, self.time_list).start()
        fmts.print_suc(self.player_list)
        self.time_list()


    def on_player_leave(self, player: Player):
        # 玩家退出服务器删除字典的缓存数据
        if player.name in self.player_list:
            self.player_list.pop(player.name)
            fmts.print_suc(self.player_list)


    def on_player_join(self, player: Player):
        # 玩家进入服务器在字典内创建一个值
        data = game_utils.getPosXYZ(player.name)
        self.player_list[player.name] = [{"x": data[0], "y": data[1], "z": data[2]}, self.s]
        fmts.print_suc(self.player_list)

    #utils.timer_events.timer_events_clear()



    # 每秒执行一次
    @utils.timer_event(1, "每个一段时间检测一次")
    def time_list(self):
        try:
            # 字典在遍历的时候是不能修改的这里创建一个副本
            dict_list = self.player_list
            # 遍历玩家字典的内容
            for i in dict_list:
                # 每次遍历都会-1也就是减去一秒
                dict_list[i][1] = dict_list[i][1] - 1
                if dict_list[i][1] == 0:
                    dict_list[i][1] = self.s
                    name = i
                    pos = game_utils.getPosXYZ(name)
                    if dict_list[i][0]['x'] == pos[0] and dict_list[i][0]['y'] == pos[1] and dict_list[i][0]['z'] == pos[2]:
                        fmts.print_suc(f"玩家{name}长时间挂机")
                        xuid = self.xuid_getter.get_xuid_by_name(name)
                        game_utils.sendcmd(f'/kick {xuid} {self.say}')
                    else:
                        dict_list[i] = [{"x": pos[0], "y": pos[1], "z": pos[2]}, self.s]
            # 重新赋值回去
            self.player_list = dict_list
        except:
            fmts.print_err(f"出现未知错误")

















# 主线程
entry = plugin_entry(NewPlugin)
