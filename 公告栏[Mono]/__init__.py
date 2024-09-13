import datetime
import time, random ,threading

from tooldelta import Plugin, plugins, Config, Builtins, Print




@plugins.add_plugin
class BetterAnnounce(Plugin):
    name = "公告栏"
    author = "Mono"
    version = (0, 0, 2)
    def on_def(self):
        self.funclib = plugins.get_plugin_api("基本插件功能库")
        self.menu = plugins.get_plugin_api("聊天栏菜单")
        self.menu.add_trigger(["ad", "公告"], "公告栏菜单", "<reload>",self.ad_menu)
        self.CFG={
            "模式":"默认",
            "公告计分板":"公告",
            "公告名称":"公告",
            "内容":[
                "§7***************",
                "§7 ",
                "§b| §7{year}/{month}/{day} {week_day}",
                "§b| §7{time_cn} §{time_color}{hour}:{minute}:{second}",
                "§b",
                "§b| §f延迟 : §{tps_color}{tps}§r",
                "§b| §f在线 §r§7: §e{num_players}",
                "§r§k",
                "§7§7***************"
            ],
            "预设":[
                ["§r§4_§6_§e_§a_§2_§b_§d_§c_§5_§4_§6_§e_§a_§2_",
                 "§l§d|§6_§c_§a-§b•公§e告•§a-§e_§6_§4|",
                 "§6•§f§7{time_cn} §{time_color}{hour}:{minute}:{second}",
                 "§l----------------",
                 "§6•§f延 迟: §{tps_color}{tps}",
                 "§6•§f服 主-§eMono",
                 "§6•§f交 流-§amono2023",
                 "§l---------------§f-",
                 "§f在线玩家 : {num_players}"
                 ],
                 [
                "§7***************",
                "§7 ",
                "§b| §7{year}/{month}/{day} {week_day}",
                "§b| §7{time_cn} §{time_color}{hour}:{minute}:{second}",
                "§b",
                "§b| §f延迟 : §{tps_color}{tps}§r",
                "§b| §f在线 §r§7: §e{num_players}",
                "§r§k",
                "§7§7***************"
                ]
            ],
            "闪字":{
                "是否启用":False,
                "内容":"ToolDelta_for_NEMC_2024",
                "滚动长度":10
            }
        }
        self.std = Config.auto_to_std(self.CFG)
        self.read_config()


    def read_config(self):
        cfg, _ = Config.getPluginConfigAndVersion(self.name, self.std, self.CFG, self.version)
        self.ano_name,self.ano_score = cfg["公告名称"],cfg["公告计分板"]
        self.context = cfg["内容"]
        if cfg["闪字"]["是否启用"]:
            self.flash_text = cfg["闪字"]["内容"]
            self.flash_text_len = cfg["闪字"]["滚动长度"]
            self.flash_mode=0
            self.text=self.flash_text
            self.flash_text_start_num=0
        self.time_cn="未知"
        self.tps=0.0
        self.tps_color="f"
        self.context_bak={}
        self.oneSay=""
        self.time_color="9"
        nowTime = datetime.datetime.now()
        self.year = nowTime.strftime("%Y")
        self.month = nowTime.strftime("%m")
        self.day = nowTime.strftime("%d")
        self.hour=nowTime.strftime("%H")
        self.minute=nowTime.strftime("%M")
        self.second=nowTime.strftime("%S")
        self.weekday = nowTime.strftime("%A")
        self.num_players = 0
        self.replaceContent = {"{time_color}":self.time_color,"{year}":self.year,"{month}":self.month,"{day}":self.day,"{hour}":self.hour,"{minute}":self.minute,"{second}":self.second,"{week_day}":self.weekday,"{num_players}":self.num_players,"{oneSay}":self.oneSay,"{tps}":self.tps,"{tps_color}":self.tps_color,"{time_cn}":self.time_cn}

    def flash_text_flush(self):
        flash_text_back=""
        text_len=len(self.text)
        if self.flash_mode == 0:
            if self.flash_text_start_num+self.flash_text_len > text_len:
                flash_text_back=self.text[self.flash_text_start_num:text_len]
                num = abs(text_len-self.flash_text_start_num-self.flash_text_len)
                flash_text_back+=self.text[0:num]
            else:
                flash_text_back=self.text[self.flash_text_start_num:self.flash_text_start_num+self.flash_text_len]
            if self.flash_text_start_num>=text_len:
                self.flash_text_start_num=0
            self.flash_text_start_num+=1
            return flash_text_back
        ...

    def ad_menu(self,player: str, args: list[str]):
        if args[0]=="reload":
            self.read_config()
        self.game_ctrl.say_to(player,"公告栏 | §a重载完成.")

    @Builtins.thread_func("内容刷新")
    def context_flush(self):
        while True:
            self.replaceContent = {"{time_color}":self.time_color,"{year}":self.year,"{month}":self.month,"{day}":self.day,"{hour}":self.hour,"{minute}":self.minute,"{second}":self.second,"{week_day}":self.weekday,"{num_players}":self.num_players,"{oneSay}":self.oneSay,"{tps}":self.tps,"{tps_color}":self.tps_color,"{time_cn}":self.time_cn}
            text=[]
            for i in self.context:
                for j in self.replaceContent:
                    if j in i:
                        i=i.replace(j, str(self.replaceContent[j]))
                text.append(i)
            self.context_bak=text
            time.sleep(0.3)

    def on_inject(self):
        self.start()
        self.time_update()
        self.context_flush()
        self.flush()

    @plugins.add_packet_listener(23)
    def on_pkt(self, packet: dict):
        ClientRequestTimestamp=packet["ClientRequestTimestamp"]
        ServerReceptionTimestamp=packet["ServerReceptionTimestamp"]
        difference = abs(ServerReceptionTimestamp - ClientRequestTimestamp)
        if 0 <= difference <= 10:
            self.tps = "{:.1f}".format(20.0 - (difference / 10) * 2)
            self.tps_color = "a"
        elif 10 < difference <= 25:
            self.tps = "{:.1f}".format(18.0 - ((difference - 10) / 15) * 6)
            self.tps_color = "e"
        elif 25 < difference <= 40:
            self.tps = "{:.1f}".format(12.0 - ((difference - 25) / 25) * 5)
            self.tps_color = "d"
        elif 40 < difference <= 50:
            self.tps = "{:.1f}".format(7.0 - ((difference - 40) / 10) * 7)
            self.tps_color = "c"
        else:
            self.tps = "0.0"
            self.tps_color = "f"
        return False

    @Builtins.thread_func("时间+玩家更新")
    def time_update(self):
        while True:
            nowTime = datetime.datetime.now()
            self.year = nowTime.strftime("%Y")
            self.month = nowTime.strftime("%m")
            self.day = nowTime.strftime("%d")
            self.hour=nowTime.strftime("%H")
            self.minute=nowTime.strftime("%M")
            self.second=nowTime.strftime("%S")
            self.weekday = nowTime.strftime("%A")
            self.num_players = self.game_ctrl.allplayers.__len__()
            hour = int(nowTime.strftime("%H"))
            if 4 <= hour < 7:
                return_value = ("清晨", "9")
            elif 7 <= hour < 11:
                return_value = ("早晨", "a")
            elif 11 <= hour < 13:
                return_value = ("午时", "c")
            elif 13 <= hour < 17:
                return_value = ("下午", "g")
            elif 17 <= hour < 22:
                return_value = ("夜晚", "b")
            elif (22 <= hour <= 23) or (0 <= hour < 4):
                return_value = ("深夜", "3")
            self.time_cn=return_value[0]
            self.time_color=return_value[1]
            time.sleep(0.3)

    @Builtins.thread_func
    def start(self):
        self.game_ctrl.sendwocmd(f"/scoreboard objectives remove {self.ano_score}")
        time.sleep(0.3)
        self.game_ctrl.sendwocmd(
            f'''/scoreboard objectives add {self.ano_score} dummy {self.ano_name}'''
        )
        self.game_ctrl.sendwocmd(f"/scoreboard objectives setdisplay sidebar {self.ano_score}")

    @Builtins.thread_func("公告刷新")
    def flush(self):
        while True:
            self.game_ctrl.sendwocmd(f"/scoreboard players reset * {self.ano_score}")
            score=0
            try:
                flash_text=self.flash_text_flush()
                if flash_text:
                    self.game_ctrl.sendwocmd(f'/scoreboard players set "{flash_text}" {self.ano_score} -1')
                for text in self.context_bak[::-1]:
                    score+=1
                    self.game_ctrl.sendwocmd(f'/scoreboard players set "{text}" {self.ano_score} {score}')
                time.sleep(0.5)
            except KeyError as e:
                time.sleep(0.5)
