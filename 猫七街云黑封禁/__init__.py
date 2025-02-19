from tooldelta import Plugin, plugins, Config, Print, Utils
import os, json, requests, time
from urllib.parse import quote
from typing import List

@plugins.add_plugin
class CloudBlacklist(Plugin):
    name = "云黑"
    author = "猫七街"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._default_cfg = {
            "中心服务器": "129.204.12.111:2000",
            "接入黑名单": "官方云黑列表",
            "启用同步": True,
            "超时时间（秒）": 10,
            "检测时间（秒）": 30
        }
        self._std_cfg = {
            "中心服务器": str,
            "接入黑名单": str,
            "启用同步": bool,
            "超时时间（秒）": int,
        }
        
        try:
            self._cfg, self.cfg_version = Config.get_plugin_config_and_version(
                self.name, 
                self._std_cfg,
                self._default_cfg,
                self.version
            )
        except Exception as e:
            Print.print_err(f"配置加载失败: {e}")
            self._cfg = self._default_cfg.copy()
            self.cfg_version = self.version
        
        self.url = f"http://{self._cfg['中心服务器']}"
        self._init_data_file()

    def _init_data_file(self):
        data_path = os.path.join(self.data_path, "blacklist.json")
        if not os.path.exists(data_path):
            with open(data_path, "w") as f:
                json.dump({}, f, indent=2)

    def on_inject(self):
        self._setup_commands()
        if self._cfg["启用同步"]:
            self.Pull_Clouds_blacklist([])

        self.bot_name = self.game_ctrl.bot_name

        Utils.createThread(self.auto_check_blacklist, (), "黑名单检测")

    def on_def(self):
        self.api_get_xuid = plugins.get_plugin_api("XUID获取")
    def _setup_commands(self):
        triggers = [
            ("拉取云黑", self.Pull_Clouds_blacklist, "从服务器拉取黑名单数据"),
            ("更换黑名单接入", self.Replace_list, "切换黑名单数据源"),
            ("创建黑名单服务器", self.Create_blacklist_server, "创建新黑名单服务器"),
            ("删除黑名单服务器", self.Delete_blacklist_server, "删除黑名单服务器"),
            ("更新黑名单服务器云黑数据", self.Update_blacklist_server, "将本地的黑名单数据上传到自己的黑名单服务器"),
            ("添加黑名单", self.add_black_list, "将曾经加入过服务器的玩家添加进本地黑名单"),
            ("移除黑名单", self.remove_black_list, "将本地黑名单中的玩家移除"),
        ]
        for cmd, func, desc in triggers:
            self.frame.add_console_cmd_trigger([cmd], None, desc, func)

    def _safe_request(self, url: str) -> requests.Response:
        try:
            response = requests.get(
                url,
                timeout=self._cfg["超时时间（秒）"]
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"请求失败: {str(e)}")

    def Pull_Clouds_blacklist(self, args: List[str]):
        try:
            encoded_dir = quote(self._cfg["接入黑名单"], safe="")
            url = f"{self.url}/{encoded_dir}/get_blacklist"
            
            response = self._safe_request(url)
            new_data = response.json()
            
            data_path = os.path.join(self.data_path, "blacklist.json")
            
            if args:
                with open(data_path, 'w') as f:
                    json.dump(new_data, f, indent=2)
                Print.print_suc(f"成功覆盖 {len(new_data)} 条黑名单数据！")
            else:
                with open(data_path, 'r+') as f:
                    try:
                        current_data = json.load(f)
                    except json.JSONDecodeError:
                        current_data = {}
                    current_data.update(new_data)
                    f.seek(0)
                    json.dump(current_data, f, indent=2)
                    f.truncate()
                Print.print_suc(f"成功合并 {len(new_data)} 条黑名单数据！")
                
        except Exception as e:
            Print.print_err(f"拉取失败: {str(e)}")

    def Replace_list(self, args: List[str]):
        try:
            response = self._safe_request(f"{self.url}/get_list")
            dirs = response.json()["subfolders"]
            
            for idx, name in enumerate(dirs, 1):
                Print.print_suc(f"{idx}. {name}")
                
            while True:
                try:
                    choice = input("请输入序号：")
                    if not choice.isdigit():
                        raise ValueError
                    num = int(choice)
                    if 1 <= num <= len(dirs):
                        selected = dirs[num-1]
                        break
                    raise ValueError
                except:
                    Print.print_err("输入无效，请重新输入！")
            
            encoded_dir = quote(selected, safe="")
            
            test_url = f"{self.url}/{encoded_dir}/get_blacklist"
            test_response = self._safe_request(test_url)
            if test_response.status_code != 200:
                raise RuntimeError(f"目录验证失败: {test_response.text}")
            
            self._cfg["接入黑名单"] = selected
            
            Config.upgrade_plugin_config(
                plugin_name=self.name,
                configs=self._cfg,
                version=self.cfg_version
            )
            
            self.Pull_Clouds_blacklist(["1"])
            Print.print_suc(f"已切换到: {selected}")
            
        except Exception as e:
            Print.print_err(f"切换失败: {str(e)}")

    def Create_blacklist_server(self, args: List[str]):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            target_dir = os.path.abspath(os.path.join(
                current_dir,
                "..", "..", "..",
                "ToolDelta基本配置.json"
            ))
            
            if not os.path.exists(target_dir):
                raise FileNotFoundError("找不到基本配置文件")
            
            with open(target_dir, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            
            server_number = config_data["NeOmega接入点启动模式"]["服务器号"]

            while True:
                password = input("请输入管理密码（至少16位）: ").strip()
                if len(password) < 16:
                    Print.print_err("密码长度必须至少16位")
                    continue
                    
                confirm = input("请再次输入密码确认: ").strip()
                if password != confirm:
                    Print.print_err("两次输入的密码不一致")
                else:
                    break

            local_blacklist_path = os.path.join(self.data_path, "blacklist.json")
            if not os.path.exists(local_blacklist_path):
                raise FileNotFoundError("本地黑名单文件不存在")

            with open(local_blacklist_path, "r", encoding="utf-8") as f:
                blacklist_data = json.load(f)

            upload_url = f"{self.url}/create_new/{server_number}"
            try:
                response = requests.post(
                    upload_url,
                    json={
                        "password": password,
                        "blacklist": blacklist_data
                    },
                    timeout=self._cfg["超时时间（秒）"]
                )
                response.raise_for_status()
                
                result = response.json()
                if result.get("status") == "success":
                    Print.print_suc("云黑服务器创建成功！")
                else:
                    Print.print_err(f"创建失败: {result.get('message', '未知错误')}")
                    
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                if status_code == 400:
                    err_msg = e.response.json().get("message", "请求参数错误")
                elif status_code == 409:
                    err_msg = "该服务器号已存在"
                else:
                    err_msg = f"HTTP错误 ({status_code})"
                Print.print_err(f"服务器拒绝请求: {err_msg}")
                
            except requests.exceptions.Timeout:
                Print.print_err("请求超时，请检查网络连接")
                
            except requests.exceptions.RequestException as e:
                Print.print_err(f"网络请求异常: {str(e)}")

        except FileNotFoundError as e:
            Print.print_err(f"文件未找到: {str(e)}")
        except json.JSONDecodeError:
            Print.print_err("配置文件解析失败，请检查文件格式")
        except KeyError as e:
            Print.print_err(f"配置文件缺少必要字段: {str(e)}")
        except Exception as e:
            Print.print_err(f"未知错误: {str(e)}")

    def Delete_blacklist_server(self, args: List[str]):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            target_dir = os.path.abspath(os.path.join(
                current_dir,
                "..", "..", "..",
                "ToolDelta基本配置.json"
            ))
            
            if not os.path.exists(target_dir):
                raise FileNotFoundError("找不到基本配置文件")
            
            with open(target_dir, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            
            server_number = config_data["NeOmega接入点启动模式"]["服务器号"]

            password = input("请输入管理员密码: ").strip()

            delete_url = f"{self.url}/remove/{server_number}"
            try:
                response = requests.post(
                    delete_url,
                    json={"password": password},
                    timeout=self._cfg["超时时间（秒）"]
                )
                response.raise_for_status()
                
                result = response.json()
                if result.get("status") == "success":
                    Print.print_suc(f"黑名单服务器 {server_number} 删除成功")
                else:
                    Print.print_err(f"删除失败: {result.get('message', '未知错误')}")

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                if status_code == 400:
                    err_msg = e.response.json().get("message", "请求参数错误")
                elif status_code == 403:
                    err_msg = "密码错误或权限不足"
                elif status_code == 404:
                    err_msg = "服务器号不存在"
                else:
                    err_msg = f"HTTP错误 ({status_code})"
                Print.print_err(f"服务器拒绝请求: {err_msg}")
                
            except requests.exceptions.Timeout:
                Print.print_err("请求超时，请检查网络连接")
                
            except requests.exceptions.RequestException as e:
                Print.print_err(f"网络请求异常: {str(e)}")

        except FileNotFoundError as e:
            Print.print_err(f"文件未找到: {str(e)}")
        except json.JSONDecodeError:
            Print.print_err("配置文件解析失败，请检查文件格式")
        except KeyError as e:
            Print.print_err(f"配置文件缺少必要字段: {str(e)}")
        except Exception as e:
            Print.print_err(f"未知错误: {str(e)}")

    def Update_blacklist_server(self, args: List[str]):
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            target_dir = os.path.abspath(os.path.join(
                current_dir,
                "..", "..", "..",
                "ToolDelta基本配置.json"
            ))
            
            if not os.path.exists(target_dir):
                raise FileNotFoundError("找不到基本配置文件")
            
            with open(target_dir, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            
            server_number = config_data["NeOmega接入点启动模式"]["服务器号"]

            password = input("请输入管理员密码: ").strip()

            verify_url = f"{self.url}/verify_password/{server_number}"
            try:
                response = requests.post(
                    verify_url,
                    json={"password": password},
                    timeout=self._cfg["超时时间（秒）"]
                )
                response.raise_for_status()
                
                result = response.json()
                if result.get("status") != "success":
                    Print.print_err(f"密码验证失败: {result.get('message', '未知错误')}")
                    return

                local_blacklist_path = os.path.join(self.data_path, "blacklist.json")
                if not os.path.exists(local_blacklist_path):
                    raise FileNotFoundError("本地黑名单文件不存在")

                with open(local_blacklist_path, "r", encoding="utf-8") as f:
                    blacklist_data = json.load(f)

                upload_url = f"{self.url}/upload_blacklist/{server_number}"
                try:
                    response = requests.post(
                        upload_url,
                        json={"blacklist": blacklist_data},
                        timeout=self._cfg["超时时间（秒）"]
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    if result.get("status") == "success":
                        Print.print_suc("云黑列表上传成功")
                    else:
                        Print.print_err(f"上传失败: {result.get('message', '未知错误')}")

                except requests.exceptions.RequestException as e:
                    Print.print_err(f"上传失败: {str(e)}")

            except requests.exceptions.RequestException as e:
                Print.print_err(f"密码验证失败: {str(e)}")

        except FileNotFoundError as e:
            Print.print_err(f"文件未找到: {str(e)}")
        except json.JSONDecodeError:
            Print.print_err("配置文件解析失败，请检查文件格式")
        except KeyError as e:
            Print.print_err(f"配置文件缺少必要字段: {str(e)}")
        except Exception as e:
            Print.print_err(f"未知错误: {str(e)}")
    
    def on_player_join(self, player_name: str):
        time.sleep(4)
        self.check_blacklist(player_name)

    def check_blacklist(self, player_name: str):
        data_path = os.path.join(self.data_path, "blacklist.json")
        black_list = {}
        with open(data_path, "r", encoding="utf-8") as f:
            black_list = json.load(f)
        
        if not black_list:
            return
        
        player_uuid = self.api_get_xuid.get_xuid_by_name(player_name, True)
        if player_name == self.bot_name:
            return

        if player_uuid in black_list:
            self.game_ctrl.sendwocmd(f"kick {player_name} 您被禁止加入服务器\n原因：处于黑名单列表")

            if black_list[player_uuid] != player_name:
                black_list[player_uuid] = player_name
                with open(data_path, "w", encoding="utf-8") as f:
                    json.dump(black_list, f, indent=4)

        return
    
    def auto_check_blacklist(self):
        while True:
            time.sleep(self._cfg["检测时间（秒）"])
            players = self.game_ctrl.allplayers
            for player_name in players:
                self.check_blacklist(player_name)
    
    def add_black_list(self, args: List[str]):
        player_name = input("请输入玩家名：")
        try:
            player_uuid = self.api_get_xuid.get_xuid_by_name(player_name, True)

        except:
            Print.print_err("该玩家未加入过服务器")   

        with open(self.data_path + "/blacklist.json", "r", encoding="utf-8") as f:
            black_list = json.load(f)
        
        black_list[player_uuid] = player_name
        with open(self.data_path + "/blacklist.json", "w", encoding="utf-8") as f:
            json.dump(black_list, f, indent=4)
            Print.print_suc("添加成功")

    def remove_black_list(self, args: List[str]):
        player_name = input("请输入玩家名：")
        try:
            player_uuid = self.api_get_xuid.get_xuid_by_name(player_name, True)
        
        except:
            Print.print_err("该玩家不存在于黑名单中")

        with open(self.data_path + "/blacklist.json", "r", encoding="utf-8") as f:
            black_list = json.load(f)
        
        if player_uuid in black_list:
            del black_list[player_uuid]
            with open(self.data_path + "/blacklist.json", "w", encoding="utf-8") as f:
                json.dump(black_list, f, indent=4)
                Print.print_suc("删除成功")
    