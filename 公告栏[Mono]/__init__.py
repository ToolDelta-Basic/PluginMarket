import datetime
import time
from tooldelta import utils, cfg, Plugin, Print, plugin_entry

import pytz
from tooldelta.constants import PacketIDS

packets = PacketIDS


class BetterAnnounce(Plugin):
    name = "公告栏"
    author = "Mono"
    version = (1, 0, 3)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPacket([packets.IDSetScore], self.on_setscore)

    def on_def(self):
        """
        公告修改手册:
        1.直接修改下面的列表,排列顺序(上->下),提供的可供更换的文本有:
            {num_players} : 在线人数
            {week_day}    : 周几
            {tps}         : tps
            {year}        : 年
            {month}       : 月
            {day}         : 日
            {time_cn}     : 时间中文
            {time_color}  : 时间颜色
            {hour}        : 小时
            {minute}      : 分钟
            {second}      : 秒
            {run_time}    : 运行时间
        2.修改title 修改标题,默认为"公告栏"
        3.修改刷新时间 修改刷新时间,默认为1秒
        4.最好别乱改,运行不了删了重新从插件市场下载
        5.已自动同步北京时间(UTC+8),一般面板时间不会影响到显示时间
        注:因为写个配置太麻烦了,所以就没有设置,直接修改本文件即可

        修改下面的self.ads_texts_bak 修改公告栏内容
        """
        self.ads_texts_bak = [
            "§7***************",
            "§7| §7{year}/{month}/{day} {week_day}",
            "§b| §7已运行{run_time}",
            "§b| §7{time_cn} §{time_color}{hour}:{minute}:{second}",
            "§b",
            "§b| §f延迟 : {tps}§r",
            "§b| §f在线 §r§7: §e{num_players}",
            "§r§7",
            "§r§7***************",
        ]
        self.刷新时间 = 1
        self.title = "公告栏"
        self.tpscalc = self.GetPluginAPI("tps计算器", (0, 0, 1), True)
        self.on_first_run = True
        self.start_time = time.time()
        self.record_del_and_create = {"create": {}}

    def on_inject(self):
        time.sleep(1)
        self.flush_gg()
        time.sleep(1)
        self.flush_scoreboard_text()

    def flush_gg(self):
        repeat_times = 0
        have_scoreboard = False
        res = self.game_ctrl.sendwscmd(
            "/scoreboard objectives list", waitForResp=True, timeout=5
        )
        if res:
            if len(res.OutputMessages) > 0:
                for i in res.OutputMessages:
                    if i.Success and i.Parameters[0] == "公告":
                        have_scoreboard = True
                        break
            if not have_scoreboard:
                self.print("§e公告栏不存在,尝试创建公告栏")
                self.game_ctrl.sendwocmd(
                    f"/scoreboard objectives add 公告 dummy {self.title}"
                )
        else:
            raise KeyError("获取计分板列表失败")
        while True:
            if repeat_times > 5:
                self.print(
                    "重试次数过多,可能无法正常显示公告栏,请确认租赁是否服流畅,这可能导致命令发送失败"
                )
                raise TimeoutError("公告栏重试失败次数过多.")
            self.print("§e尝试删除重建公告栏[1/3]")
            res = self.game_ctrl.sendwscmd(
                "/scoreboard objectives remove 公告", waitForResp=True, timeout=3
            )
            if res:
                if res.SuccessCount == 0:
                    repeat_times += 1
                    self.print(f"§c删除公告栏失败§f,将在§e{repeat_times * 3}s§f后重试")
                    time.sleep(repeat_times * 3)
                    continue
                else:
                    self.print("§a删除公告栏成功")
            else:
                repeat_times += 1
                self.print(f"§c删除公告栏失败§f,将在§e{repeat_times * 3}s§f后重试")
                time.sleep(repeat_times * 3)
                continue
            time.sleep(0.3)
            self.print("§e尝试创建公告栏[2/3]")
            res = self.game_ctrl.sendwscmd(
                f"/scoreboard objectives add 公告 dummy {self.title}",
                timeout=3,
                waitForResp=True,
            )
            if res:
                if res.SuccessCount == 0:
                    repeat_times += 1
                    self.print(f"§c创建公告栏失败§f,将在§e{repeat_times * 3}s§f后重试")
                    time.sleep(repeat_times * 3)
                    continue
                else:
                    self.print("§a创建公告栏成功")
            else:
                repeat_times += 1
                self.print(f"§c创建公告栏失败§f,将在§e{repeat_times * 3}s§f后重试")
                time.sleep(repeat_times * 3)
                continue
            time.sleep(0.3)
            self.print("§e尝试创建公告栏[3/3]")
            res = self.game_ctrl.sendwscmd(
                "/scoreboard objectives setdisplay sidebar 公告",
                timeout=3,
                waitForResp=True,
            )
            if res:
                if res.SuccessCount == 0:
                    repeat_times += 1
                    self.print(f"§c显示公告栏失败§f,将在§e{repeat_times * 3}s§f后重试")
                    time.sleep(repeat_times * 3)
                    continue
                else:
                    self.print("§a显示公告栏成功")
            else:
                repeat_times += 1
                self.print(f"§c显示公告栏失败§f,将在§e{repeat_times * 3}s§f后重试")
                time.sleep(repeat_times * 3)
                continue
            break

    def get_tps_str(self, color=False):
        if self.tpscalc is None:
            return "§c无前置tps计算器"
        elif color:
            return self.get_tps_color() + str(round(self.tpscalc.get_tps(), 1))
        else:
            return str(round(self.tpscalc.get_tps(), 1))

    def get_tps_color(self):
        tps = self.tpscalc.get_tps()
        if tps > 14:
            return "§a"
        elif tps > 10:
            return "§6"
        else:
            return "§c"

    def get_time_color(self, nowTime):
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
        else:
            return_value = ("未知", "f")
        return return_value

    @Utils.thread_func("计分板公告文字刷新")
    def flush_scoreboard_text(self):
        self.lastest_texts = []
        beijing_tz = pytz.timezone("Asia/Shanghai")
        while True:
            nowTime = datetime.datetime.now(beijing_tz)
            return_value = self.get_time_color(nowTime)
            (self.time_cn, self.time_color) = return_value
            scb_score = len(self.ads_texts_bak)
            self.lastest_texts_bak = self.lastest_texts.copy()
            self.lastest_texts_bak.reverse()
            self.lastest_texts = []
            endime = time.time()
            difference = endime - self.start_time
            for text in self.ads_texts_bak:
                text = utils.simple_fmt(
                    {
                        "{num_players}": len(self.game_ctrl.allplayers),
                        "{week_day}": "周" + "一二三四五六日"[time.localtime().tm_wday],
                        "{tps}": self.get_tps_str(True),
                        "{year}": nowTime.strftime("%Y"),
                        "{month}": nowTime.strftime("%m"),
                        "{day}": nowTime.strftime("%d"),
                        "{time_cn}": self.time_cn,
                        "{time_color}": self.time_color,
                        "{hour}": nowTime.strftime("%H"),
                        "{minute}": nowTime.strftime("%M"),
                        "{second}": nowTime.strftime("%S"),
                        "{run_time}": str(int(difference // 86400))
                        + "天"
                        + str(int((difference % 86400) // 3600))
                        + "小时"
                        + str(int((difference % 3600) // 60))
                        + "分",
                    },
                    text,
                )
                scb_score -= 1
                if self.on_first_run:
                    repeat_times = 0
                    while True:
                        repeat_times += 1
                        if repeat_times > 5:
                            self.print(f"§c多次尝试设置公告栏内容['{text}']失败§f")
                            raise TimeoutError(f"多次尝试设置公告栏内容['{text}']失败")
                        res = self.game_ctrl.sendwscmd(
                            f'/scoreboard players set "{text}" 公告 {scb_score}',
                            waitForResp=True,
                            timeout=3,
                        )
                        if res:
                            if res.SuccessCount == 0:
                                self.print(
                                    f"§c设置公告栏内容['{text}']失败§f,将在§e{repeat_times * 3}s§f后重试"
                                )
                                time.sleep(repeat_times * 3)
                                continue
                        else:
                            self.print(
                                f"§c设置公告栏内容['{text}']失败§f,将在§e{repeat_times * 3}s§f后重试"
                            )
                            continue
                        break
                else:
                    if self.lastest_texts_bak[scb_score] == text:
                        self.lastest_texts.append(text)
                        continue
                    self.game_ctrl.sendwocmd(
                        f'/scoreboard players reset "{self.lastest_texts_bak[scb_score]}" 公告'
                    )
                    self.game_ctrl.sendwocmd(
                        f'/scoreboard players set "{text}" 公告 {scb_score}'
                    )
                self.lastest_texts.append(text)
            self.on_first_run = False
            time.sleep(self.刷新时间)

    def on_setscore(self, packet: dict):
        if packet.get("ActionType", None) is not None:
            if packet["ActionType"] == 1:
                for i in packet["Entries"]:
                    if i["ObjectiveName"] == "公告":
                        self.record_del_and_create["create"][i["EntryID"]] = i[
                            "DisplayName"
                        ]
            else:
                for i in packet["Entries"]:
                    if i["EntryID"] in self.record_del_and_create["create"]:
                        del self.record_del_and_create["create"][i["EntryID"]]
            if len(self.record_del_and_create["create"]) > 3:
                for i, v in self.record_del_and_create["create"].items():
                    self.game_ctrl.sendwocmd(f'/scoreboard players reset "{v}" 公告')
                self.record_del_and_create["create"] = {}
        return False


entry = plugin_entry(BetterAnnounce)
