from tooldelta import Plugin, plugin_entry, game_utils, utils, cfg
import json
import os
import time

class BankPlugin(Plugin):
    name = "银行"
    author = "笛卡尔似的梦"
    version = (0, 0, 1)
  
    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        
        # 自动生成 datas.json
        self.generate_datas_json()
        
        # 默认配置
        CONFIG_DEFAULT = {
            "货币计分板名": "money",
            "利息率": 0.001,  # 每小时0.1%
            "银行名称": "§b§l蔚蓝之空银行",
            "初始存款": 0,
            "最大存款": 1000000
        }
      
        # 配置标准
        CONFIG_STD = {
            "货币计分板名": str,
            "利息率": float,
            "银行名称": str,
            "初始存款": int,
            "最大存款": int
        }
      
        # 加载配置
        config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
      
        self.money_scb_name = config["货币计分板名"]
        self.interest_rate = config["利息率"]
        self.bank_name = config["银行名称"]
        self.initial_balance = config["初始存款"]
        self.max_balance = config["最大存款"]
      
        # 银行数据文件路径
        self.bank_data_path = self.format_data_path("bank_data.json")
      
        # 初始化银行数据
        self.bank_data = {}
        self.load_bank_data()
      
        # 利息发放线程
        self.interest_thread = None

    def generate_datas_json(self):
        """自动生成 datas.json 文件"""
        datas_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datas.json")
        
        if not os.path.exists(datas_path):
            datas_content = {
                "plugin-id": "银行",
                "author": "笛卡尔似的梦",
                "version": "0.0.1",
                "description": "一个完整的银行系统插件，玩家可以存款、取款、查看利息，银行每小时向在线玩家发放利息",
                "plugin-type": "classic",
                "pre-plugins": {
                    "聊天栏菜单": "0.0.1",  # 改回原来的聊天栏菜单
                    "XUID获取": "0.0.7"
                }
            }
            
            try:
                with open(datas_path, 'w', encoding='utf-8') as f:
                    json.dump(datas_content, f, ensure_ascii=False, indent=2)
                print(f"[银行] datas.json 文件已创建")
            except Exception as e:
                print(f"[银行] 创建 datas.json 失败: {str(e)}")
        else:
            print(f"[银行] datas.json 文件已存在，跳过创建")

    def on_preload(self):
        # 获取聊天栏菜单API - 改回原来的API名称
        try:
            self.chatbar = self.GetPluginAPI("聊天栏菜单")  # 修正API名称
            print(f"[银行] 成功获取聊天栏菜单API")
        except Exception as e:
            print(f"[银行] 获取聊天栏菜单API失败: {str(e)}")
            # 如果获取失败，设置chatbar为None避免后续错误
            self.chatbar = None
      
        try:
            # 获取XUID获取API
            self.GetPluginAPI("XUID获取")
            print(f"[银行] 成功获取XUID获取API")
        except Exception as e:
            print(f"[银行] 获取XUID获取API失败: {str(e)}")
  
    def on_active(self):
        # 确保chatbar API已成功获取
        if self.chatbar is None:
            print(f"[银行] 错误: 聊天栏菜单API未获取，无法注册命令")
            return
            
        # 注册银行命令
        self.chatbar.add_trigger(
            ["银行", "bank"], 
            None, 
            "打开银行界面", 
            self.open_bank_interface
        )
      
        print(f"[银行] 命令已注册: '银行', 'bank'")
      
        # 启动利息发放线程
        self.start_interest_thread()
        print(f"[银行] 利息线程已启动")
  
    def on_player_join(self, player: "Player"):
        # 确保新玩家有银行账户
        xuid = self.get_player_xuid(player.name)
        if xuid not in self.bank_data:
            self.bank_data[xuid] = {
                "name": player.name,
                "balance": self.initial_balance
            }
            self.save_bank_data()
            print(f"[银行] 为玩家 {player.name} 创建新账户")
  
    def load_bank_data(self):
        """加载银行数据 - 使用普通文件操作确保数据持久化"""
        try:
            if not os.path.exists(self.bank_data_path):
                print(f"[银行] 银行数据文件不存在，创建新文件")
                with open(self.bank_data_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                return {}
          
            with open(self.bank_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[银行] 银行数据加载成功，账户数: {len(data)}")
              
                # 确保所有玩家都有余额数据
                for xuid, account in data.items():
                    if "balance" not in account:
                        account["balance"] = self.initial_balance
              
                self.bank_data = data
                return data
        except Exception as e:
            print(f"[银行] 加载银行数据失败: {e}")
            return {}
  
    def save_bank_data(self):
        """保存银行数据 - 使用普通文件操作确保数据持久化"""
        try:
            with open(self.bank_data_path, 'w', encoding='utf-8') as f:
                json.dump(self.bank_data, f, ensure_ascii=False, indent=2)
            print(f"[银行] 银行数据保存成功，账户数: {len(self.bank_data)}")
        except Exception as e:
            print(f"[银行] 保存银行数据失败: {e}")
  
    def get_player_xuid(self, player_name: str) -> str:
        """获取玩家XUID"""
        try:
            # 使用XUID获取插件
            xuid_getter = self.GetPluginAPI("XUID获取")
            xuid = xuid_getter.get_xuid_by_name(player_name, allow_offline=True)
            print(f"[银行] 获取玩家 {player_name} 的XUID: {xuid}")
            return xuid
        except:
            # 如果无法获取XUID，使用玩家名作为替代
            print(f"[银行] 警告: 无法获取玩家 {player_name} 的XUID，使用玩家名替代")
            return player_name
  
    def open_bank_interface(self, player_name: str, _):
        """打开银行界面"""
        print(f"[银行] 收到银行命令请求，玩家: {player_name}")
      
        player = self.game_ctrl.players.getPlayerByName(player_name)
        if not player:
            print(f"[银行] 错误: 玩家 {player_name} 不存在")
            return
      
        xuid = self.get_player_xuid(player_name)
      
        # 确保账户存在
        if xuid not in self.bank_data:
            self.bank_data[xuid] = {
                "name": player_name,
                "balance": self.initial_balance
            }
            self.save_bank_data()
      
        account = self.bank_data[xuid]
      
        # 显示银行主界面
        self.show_bank_main_menu(player, account)
  
    def show_bank_main_menu(self, player: "Player", account: dict):
        """显示银行主菜单"""
        balance = account["balance"]
        player.show(f"§b══════ {self.bank_name} ══════")
        player.show(f"§b您的账户余额: §e{balance}蓝币")
        player.show("§a1. §b存款")
        player.show("§a2. §b取款")
        player.show("§a3. §b查看利息")
        player.show("§6请输入选项序号 (输入其他内容退出): ")
      
        # 等待玩家输入
        resp = game_utils.waitMsg(player.name)
        if resp is None:
            player.show("§c操作超时")
            return
      
        if resp == "1":
            self.deposit_menu(player, account)
        elif resp == "2":
            self.withdraw_menu(player, account)
        elif resp == "3":
            self.show_interest_info(player)
            self.show_bank_main_menu(player, account)
        else:
            player.show("§a感谢使用蔚蓝之空银行服务")
  
    def deposit_menu(self, player: "Player", account: dict):
        """存款菜单"""
        # 获取玩家当前蓝币
        try:
            player_money = game_utils.getScore(self.money_scb_name, player.name)
        except:
            player_money = 0
      
        player.show(f"§b══════ 存款 ══════")
        player.show(f"§b您的蓝币: §e{player_money}")
        player.show(f"§b账户余额: §e{account['balance']}蓝币")
        player.show("§6请输入存款金额 (输入0取消):")
      
        # 等待玩家输入
        resp = game_utils.waitMsg(player.name)
        if resp is None:
            player.show("§c操作超时")
            return
      
        try:
            amount = int(resp)
            if amount <= 0:
                player.show("§a存款已取消")
                self.show_bank_main_menu(player, account)
                return
          
            if amount > player_money:
                player.show("§c蓝币不足")
                self.deposit_menu(player, account)
                return
          
            # 检查存款上限
            new_balance = account["balance"] + amount
            if new_balance > self.max_balance:
                player.show(f"§c存款超过上限 {self.max_balance}")
                self.deposit_menu(player, account)
                return
          
            # 执行存款
            account["balance"] = new_balance
            self.game_ctrl.sendwocmd(
                f"scoreboard players remove \"{player.name}\" {self.money_scb_name} {amount}"
            )
            self.save_bank_data()  # 保存修改后的数据
          
            player.show(f"§a成功存款 §e{amount}蓝币")
            player.show(f"§a当前余额: §e{new_balance}蓝币")
            time.sleep(1)
            self.show_bank_main_menu(player, account)
        except ValueError:
            player.show("§c请输入有效数字")
            self.deposit_menu(player, account)
  
    def withdraw_menu(self, player: "Player", account: dict):
        """取款菜单"""
        player.show(f"§b══════ 取款 ══════")
        player.show(f"§b账户余额: §e{account['balance']}蓝币")
        player.show("§6请输入取款金额 (输入0取消):")
      
        # 等待玩家输入
        resp = game_utils.waitMsg(player.name)
        if resp is None:
            player.show("§c操作超时")
            return
      
        try:
            amount = int(resp)
            if amount <= 0:
                player.show("§a取款已取消")
                self.show_bank_main_menu(player, account)
                return
          
            if amount > account["balance"]:
                player.show("§c余额不足")
                self.withdraw_menu(player, account)
                return
          
            # 执行取款
            account["balance"] -= amount
            self.game_ctrl.sendwocmd(
                f"scoreboard players add \"{player.name}\" {self.money_scb_name} {amount}"
            )
            self.save_bank_data()  # 保存修改后的数据
          
            player.show(f"§a成功取款 §e{amount}蓝币")
            player.show(f"§a当前余额: §e{account['balance']}蓝币")
            time.sleep(1)
            self.show_bank_main_menu(player, account)
        except ValueError:
            player.show("§c请输入有效数字")
            self.withdraw_menu(player, account)
  
    def show_interest_info(self, player: "Player"):
        """显示利息信息"""
        # 计算百分比值并确保显示百分号
        interest_percent = self.interest_rate * 100
      
        player.show(f"§b══════ 利息信息 ══════")
        player.show(f"§b利率: §e每小时 {interest_percent:.3f}%%")
        player.show(f"§b发放时间: §e每小时整点")
        player.show(f"§b发放对象: §e所有在线玩家")
      
        # 计算下次发放时间
        minutes_left = 60 - time.localtime().tm_min
        player.show(f"§b下次发放: §e{minutes_left}分钟后")
  
    def start_interest_thread(self):
        """启动利息发放线程"""
        if self.interest_thread and self.interest_thread.is_alive():
            return
      
        def interest_loop():
            last_hour = time.localtime().tm_hour
            while True:
                now = time.localtime()
                current_hour = now.tm_hour
              
                # 每小时检查一次
                if current_hour != last_hour:
                    last_hour = current_hour
                    self.distribute_interest()
              
                time.sleep(60)  # 每分钟检查一次
      
        self.interest_thread = utils.createThread(
            interest_loop,
            usage="银行利息发放"
        )
  
    def distribute_interest(self):
        """向所有在线玩家发放利息"""
        online_players = self.game_ctrl.players.getAllPlayers()
        if not online_players:
            print("[银行] 利息发放: 没有在线玩家")
            return
      
        print(f"[银行] 开始发放利息给 {len(online_players)} 位在线玩家")
      
        # 计算百分比值并确保显示百分号
        interest_percent = self.interest_rate * 100
      
        # 广播利息发放通知
        self.game_ctrl.say_to("@a", f"§a[{self.bank_name}] §6正在发放利息 ({interest_percent:.3f}%%)...")
      
        updated = False
        for player in online_players:
            xuid = self.get_player_xuid(player.name)
          
            # 确保账户存在
            if xuid not in self.bank_data:
                self.bank_data[xuid] = {
                    "name": player.name,
                    "balance": self.initial_balance
                }
          
            account = self.bank_data[xuid]
          
            if account and account["balance"] > 0:
                # 确保利息至少为1蓝币
                interest = max(1, int(account["balance"] * self.interest_rate))
                account["balance"] += interest
                player.show(f"§a[{self.bank_name}] 您获得了 §e{interest}蓝币 §a利息")
                updated = True
                print(f"[银行] 给玩家 {player.name} 发放 {interest} 蓝币利息")
      
        if updated:
            self.save_bank_data()  # 保存修改后的数据
            self.game_ctrl.say_to("@a", f"§a[{self.bank_name}] §6利息发放完成!")
        else:
            print("[银行] 利息发放: 没有符合条件的玩家")

# 插件入口
entry = plugin_entry(BankPlugin)
