from tooldelta import Plugin, plugins, Config, Print, Frame  # type: ignore
import os
import json


@plugins.add_plugin_as_api("玩家数据管理")
class 数据管理(Plugin):
    name = "数据管理系统"
    author = "猫七街"
    version = (2, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._default_cfg = {
            "提示词": {
                "上传": "上传数据",
                "下载": "下载数据",
            }
        }

        self._std_cfg = {
            "提示词": {
                "上传": str,
                "下载": str,
            }
        }

        try:
            self._cfg, _ = Config.get_plugin_config_and_version(
                self.name, self._std_cfg, self._default_cfg, self.version
            )
        except Exception as e:
            Print.print_err(f"加载配置文件出错: {e}")
            self._cfg = self._default_cfg.copy()

    def on_player_message(self, player: str, msg: str):
        upload_trigger = self._cfg["提示词"]["上传"]
        download_trigger = self._cfg["提示词"]["下载"]

        if msg.strip() == upload_trigger:
            player_uuid = self.game_ctrl.players_uuid[player]
            data_path = self.format_data_path(player_uuid + ".json")

            try:
                with open(data_path, "w", encoding="utf-8") as f:
                    player_data = json.load(f)
                    if player_data["玩家基本信息"].get("玩家名称", None) != player:
                        player_data["玩家基本信息"]["玩家名称"] = player
                        f.write(json.dumps(player_data, ensure_ascii=False, indent=4))

            except Exception:
                player_data = {
                    "玩家基本信息": {"玩家UUID": player_uuid, "玩家名称": player},
                    "玩家计分板信息": {},
                }

            output = self.game_ctrl.sendwscmd_with_resp(
                f"scoreboard players list {player}"
            ).as_dict
            output = output["OutputMessages"]
            num = output[0]["Parameters"][0]
            for i in range(int(num)):
                data = output[i + 1]["Parameters"]
                player_data["玩家计分板信息"][data[2]] = data[0]

            try:
                with open(data_path, "w", encoding="utf-8") as f:
                    f.write(json.dumps(player_data, ensure_ascii=False, indent=4))
            except Exception as e:
                self.game_ctrl.say_to(player, f"§c数据上传失败！错误信息：{e}")

        elif msg.strip() == download_trigger:
            player_uuid = self.game_ctrl.players_uuid[player]
            data_path = self.format_data_path(player_uuid + ".json")
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    player_data = json.load(f)
                    for i in player_data["玩家计分板信息"]:
                        print(
                            f"scoreboard players set {player} {i} {player_data['玩家计分板信息'][i]}"
                        )
                        self.game_ctrl.sendwscmd(
                            f"scoreboard players set {player} {i} {player_data['玩家计分板信息'][i]}"
                        )
            except Exception as e:
                pass

    def on_inject(self):
        self.frame.add_console_cmd_trigger(
            ["玩家数据管理"],
            None,
            "在控制台对玩家的计分板数据进行操作（需要先上传）",
            self.console_set,
        )

    def console_set(self, args: list[str]):
        now = 1
        files = os.listdir(self.data_path)
        count = len(files)
        player_datas = []

        if count == 0:
            Print.print_inf("没有保存的玩家数据")
            return

        for file in files:
            with open(os.path.join(self.data_path, file), "r", encoding="utf-8") as f:
                player_data = json.load(f)
                player_datas.append(player_data)

        if count % 10 == 0:
            total_page = count // 10

        else:
            total_page = count // 10 + 1

        for i in range(10):
            out = i + (now - 1) * 10 + 1
            Print.print_inf(
                f"{out}.  {player_datas[out - 1]['玩家基本信息']['玩家名称']}"
            )
            if i >= count - 1:
                break

        print()
        Print.print_inf(f"     第 {now}/{total_page} 页")
        while True:
            try:
                choice = input(
                    "请输入玩家序号进行操作（输入 -/+ 上/下翻页，输入 q 退出）："
                )
                if choice == "q":
                    Print.print_inf("已退出")
                    return

                elif choice == "+":
                    now += 1
                    now = min(now, total_page)
                    for i in range(10):
                        out = i + (now - 1) * 10 + 1
                        print(out, count)
                        Print.print_inf(
                            f"{out}.  {player_datas[out - 1]['玩家基本信息']['玩家名称']}"
                        )
                        if out >= count:
                            break

                    print()
                    Print.print_inf(f"     第 {now}/{total_page} 页")
                    continue

                elif choice == "-":
                    now -= 1
                    now = max(now, 1)
                    for i in range(10):
                        out = i + (now - 1) * 10 + 1
                        Print.print_inf(
                            f"{out}.  {player_datas[out - 1]['玩家基本信息']['玩家名称']}"
                        )
                        if i >= count - 1:
                            break

                    print()
                    Print.print_inf(f"     第 {now}/{total_page} 页")
                    continue

                else:
                    choice = int(choice)
                    if choice > 0 and choice <= count:
                        break

                    else:
                        Print.print_err("输入错误，请重新输入！")
                        print(choice)

            except Exception as e:
                print(e)
                Print.print_err("输入错误，请重新输入！")

        if choice == "q":
            Print.print_inf("已退出操作")
            return

        player_data = player_datas[choice - 1]
        Print.print_inf(
            f"正在操作玩家 {player_data['玩家基本信息']['玩家名称']} 的数据"
        )
        count = len(player_data["玩家计分板信息"])
        player_data_temp = player_data.get("玩家计分板信息", {})
        player_uuid = player_data["玩家基本信息"]["玩家UUID"]
        player_data = player_data["玩家计分板信息"]
        if count == 0:
            Print.print_inf("玩家没有计分板数据")
            return

        if count % 10 == 0:
            total_page = count / 10

        else:
            total_page = count // 10 + 1

        now = 1
        temp_dic = {}
        a = 1
        for k, v in player_data_temp.items():
            temp_dic[f"{a}"] = [k, v]
            a += 1

        while True:
            for i in range(10):
                out = i + (now - 1) * 10 + 1
                Print.print_inf(f"{out}.   ", end="")
                print(temp_dic[f"{out}"][0], end="")
                print("\t\t", end="")
                print(temp_dic[f"{out}"][1])
                if i >= count - 1:
                    break

            print()
            Print.print_inf(f"     第 {now}/{total_page} 页")
            while True:
                choice = input(
                    "请输入计分板序号进行操作（输入 -/+ 上/下翻页，输入 q 退出）："
                )
                if choice == "q":
                    Print.print_inf("已退出")
                    return

                elif choice == "+":
                    now += 1
                    now = min(now, total_page)
                    for i in range(10):
                        out = i + (now - 1) * 10 + 1
                        Print.print_inf(f"{out}.   ", end="")
                        print(temp_dic[f"{out}"][0], end="")
                        print("\t\t", end="")
                        print(temp_dic[f"{out}"][1])
                        if out >= count:
                            break

                    print()
                    Print.print_inf(f"     第 {now}/{total_page} 页")
                    continue

                elif choice == "-":
                    now -= 1
                    now = max(now, 1)
                    for i in range(10):
                        out = i + (now - 1) * 10 + 1
                        Print.print_inf(f"{out}.   ", end="")
                        print(temp_dic[f"{out}"][0], end="")
                        print("\t\t", end="")
                        print(temp_dic[f"{out}"][1])
                        if i >= count - 1:
                            break

                    print()
                    Print.print_inf(f"     第 {now}/{total_page} 页")
                    continue

                else:
                    try:
                        choice = int(choice)
                        if choice > 0 and choice <= count:
                            break

                        else:
                            Print.print_err("输入错误，请重新输入！")

                    except Exception as e:
                        Print.print_err("输入错误，请重新输入！")

            if choice == "q":
                Print.print_inf("已退出")
                break

            else:
                while True:
                    choice2 = input("请输入操作类型：1.修改 2.删除 q 退出：")
                    if choice2 == "1":
                        self.player_data_change(
                            temp_dic[f"{out}"][0], temp_dic[f"{out}"][1], player_uuid
                        )  # value1: {scoreboard_name:scoreboard_value}     value2: scoreboard_name
                        break

                    elif choice2 == "2":
                        self.player_data_delete(temp_dic[f"{out}"][0], player_uuid)
                        break

                    elif choice2 == "q":
                        Print.print_inf("已退出")
                        return

                    else:
                        Print.print_err("输入错误，请重新输入！")
            break

    def player_data_change(self, key: str, value1: int, player_uuid: str):
        playerdata_path = self.format_data_path(f"{player_uuid}.json")
        with open(playerdata_path, "r", encoding="utf-8") as f:
            player_data = json.load(f)

        while True:
            try:
                value = input("请输入修改后的值：(输入 q 退出)")
                if value == "q":
                    Print.print_inf("已退出")
                    return

                else:
                    value = int(value)
                    value = str(value)
                    player_data["玩家计分板信息"][key] = value
                    print(
                        f"修改前：{value1} \t 修改后：{player_data['玩家计分板信息'][key]}"
                    )
                    choice = input("确认修改输入“y”，输入其他取消修改")
                    if choice == "y":
                        with open(playerdata_path, "r+", encoding="utf-8") as f:
                            json.dump(player_data, f, indent=4, ensure_ascii=False)

                    else:
                        Print.print_inf("取消修改")
                        return

                    Print.print_inf("修改成功")
                    return

            except Exception as e:
                Print.print_err(str(e))
                Print.print_err("输入错误，请重新输入！")

    def player_data_delete(self, key: str, player_uuid: str):
        playerdata_path = self.format_data_path(f"{player_uuid}.json")
        with open(playerdata_path, "r", encoding="utf-8") as f:
            player_data = json.load(f)
        choice = input("确认删除输入“y”，输入其他取消删除")
        if choice == "y":
            choice = input(
                "真的要删除吗？此操作不可恢复（确认删除输入“y”，输入其他取消删除）"
            )
            if choice == "y":
                player_data["玩家计分板信息"].pop(key)
                with open(playerdata_path, "w", encoding="utf-8") as f:
                    json.dump(player_data, f, indent=4, ensure_ascii=False)
                Print.print_inf("删除成功")

            else:
                Print.print_inf("已取消")
                return

        else:
            Print.print_inf("已取消")
            return
