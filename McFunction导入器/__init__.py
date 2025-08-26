import os
import re
import time
import math
from typing import List, Tuple, Optional, Dict
from tooldelta import plugin_entry, Plugin, Player, cfg, utils, fmts, Print

class McFunctionImporter(Plugin):
    """McFunction导入器插件 - 将mcfunction文件导入为游戏内指令方块链"""
    
    name = "McFunction导入器"
    author = "Q3CC & Claude"
    version = (1, 0, 0)
    description = "将mcfunction文件导入为游戏内指令方块链，支持自定义延展方向和尺寸"
    
    def __init__(self, frame):
        super().__init__(frame)
        
        # 默认配置
        CONFIG_DEFAULT = {
            "默认X轴延展长度": 10,
            "默认Z轴延展长度": 1, 
            "默认Y轴高度": 5,
            "放置延迟": 0.1,
            "支持的文件扩展名": [".mcfunction", ".txt"]
        }
        
        # 配置验证
        CONFIG_STD = {
            "默认X轴延展长度": cfg.PInt,
            "默认Z轴延展长度": cfg.PInt,
            "默认Y轴高度": cfg.PInt,
            "放置延迟": cfg.PFloat,
            "支持的文件扩展名": cfg.JsonList(str)
        }
        
        # 加载配置
        self.config, _ = cfg.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        
        # 验证配置
        if self.config["放置延迟"] < 0.01:
            fmts.print_err(f"[{self.name}] 配置错误: 放置延迟不能小于0.01秒，当前值: {self.config['放置延迟']}")
            raise ValueError("放置延迟配置无效")
        
        # 运行时变量
        self.world_api = None
        
        # 注册事件监听
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
    
    def on_preload(self):
        """预加载阶段获取所需API"""
        try:
            # 获取世界交互API
            self.world_api = self.GetPluginAPI("前置-世界交互")
            if not self.world_api:
                fmts.print_err(f"[{self.name}] 未找到世界交互API，插件功能将受限")
                
        except Exception as e:
            fmts.print_err(f"[{self.name}] 预加载时发生错误: {e}")
    
    def on_active(self):
        
        # 创建数据文件夹
        self.make_data_path()
        
        # 检查必要的文件夹
        mcf_folder = self.format_data_path("mcfunction")
        if not os.path.exists(mcf_folder):
            os.makedirs(mcf_folder)
        
        # 注册控制台命令
        self.register_console_commands()
    
    def register_console_commands(self):
        """注册控制台命令"""
        try:
            # 注册mcf文件选择和导入命令
            self.frame.add_console_cmd_trigger(
                ["mcf"],
                "[文件名/编号] [X坐标] [Y坐标] [Z坐标] [X延展] [Z延展]",
                "导入mcfunction文件",
                self.console_list_command
            )
            
            
        except Exception as e:
            fmts.print_err(f"[{self.name}] 注册控制台命令失败: {e}")
    
    def parse_mcfunction(self, file_path: str) -> List[str]:
        """解析mcfunction文件，返回有效指令列表"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            commands = []
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                
                # 移除行内注释
                if '#' in line:
                    line = line.split('#')[0].strip()
                    if not line:
                        continue
                
                # 确保指令以/开头
                if not line.startswith('/'):
                    line = '/' + line
                
                commands.append(line)
            
            fmts.print_suc(f"[{self.name}] 成功解析 {len(commands)} 条指令")
            return commands
            
        except FileNotFoundError:
            fmts.print_err(f"[{self.name}] 文件不存在: {file_path}")
            return []
        except UnicodeDecodeError:
            fmts.print_err(f"[{self.name}] 文件编码错误，请使用UTF-8编码")
            return []
        except Exception as e:
            fmts.print_err(f"[{self.name}] 解析文件失败: {e}")
            return []
    
    def calculate_block_position(self, index: int, x_size: int, z_size: int, 
                               start_pos: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """
        计算指定索引的指令方块应该放置的坐标
        使用真正的3D蛇形布局算法
        """
        x_start, y_start, z_start = start_pos
        
        # 特殊处理单行布局(z_size=1) - X轴蛇形，Y层间反向
        if z_size == 1:
            y_layer = index // x_size
            x_in_layer = index % x_size
            
            # 蛇形：偶数层从左到右，奇数层从右到左
            if y_layer % 2 == 1:  # 奇数层反向
                x_in_layer = x_size - 1 - x_in_layer
                
            final_x = x_start + x_in_layer
            final_y = y_start + y_layer
            final_z = z_start
            
        # 特殊处理单列布局(x_size=1) - Z轴蛇形，Y层间反向
        elif x_size == 1:
            y_layer = index // z_size
            z_in_layer = index % z_size
            
            # 蛇形：偶数层从前到后，奇数层从后到前
            if y_layer % 2 == 1:  # 奇数层反向
                z_in_layer = z_size - 1 - z_in_layer
                
            final_x = x_start
            final_y = y_start + y_layer
            final_z = z_start + z_in_layer
            
        else:
            # 标准布局：真正的3D蛇形 - XZ平面蛇形，Y层间反向蛇形
            blocks_per_layer = x_size * z_size
            y_layer = index // blocks_per_layer
            layer_index = index % blocks_per_layer
            
            # 在XZ平面内的蛇形坐标计算
            x_in_layer = layer_index // z_size
            z_in_layer = layer_index % z_size
            
            # XZ平面内的蛇形：奇数X行反向Z
            if x_in_layer % 2 == 1:
                z_in_layer = z_size - 1 - z_in_layer
            
            # Y层间的蛇形：奇数层反向整个XZ布局
            if y_layer % 2 == 1:
                # 反向layer_index
                layer_index = blocks_per_layer - 1 - layer_index
                # 重新计算x_in_layer和z_in_layer
                x_in_layer = layer_index // z_size
                z_in_layer = layer_index % z_size
                # 再次应用XZ平面内蛇形
                if x_in_layer % 2 == 1:
                    z_in_layer = z_size - 1 - z_in_layer
            
            final_x = x_start + x_in_layer
            final_y = y_start + y_layer
            final_z = z_start + z_in_layer
        
        return (final_x, final_y, final_z)
    
    def determine_block_type(self, index: int, command: str) -> int:
        """
        确定指令方块类型
        根据API文档：0=脉冲型, 1=循环型, 2=连锁型
        """
        if index == 0:
            return 0  # 第一个总是脉冲型
        
        # 检查是否是循环相关的指令 - 只检查明确的循环关键词
        command_lower = command.lower()
        
        # 只检查明确的循环关键词，避免误判
        explicit_loop_patterns = [
            'schedule function',
            'schedule clear',
            '/schedule',
            'repeating',
            'loop'
        ]
        
        for pattern in explicit_loop_patterns:
            if pattern in command_lower:
                return 1  # 循环型（API中1=循环型）
        
        # 检查以时间单位结尾的schedule命令（如20t, 1s等）
        words = command_lower.split()
        for word in words:
            # 检查是否是时间格式（数字+时间单位）
            if word.endswith('t') and word[:-1].isdigit():  # 如 20t
                if 'schedule' in command_lower:
                    return 1  # 循环型
            if word.endswith('s') and word[:-1].isdigit():  # 如 5s  
                if 'schedule' in command_lower:
                    return 1  # 循环型
        
        return 2  # 默认连锁型（API中2=连锁型）
    
    def determine_facing_direction(self, index: int, x_size: int, z_size: int) -> int:
        """
        确定指令方块朝向
        基于3D蛇形布局确定最优朝向
        朝向值: 0=下, 1=上, 2=北, 3=南, 4=西, 5=东
        """
        # 计算当前方块和下一个方块的坐标
        if index + 1 >= x_size * z_size * 100:  # 假设不超过100层
            return 1  # 最后一个方块朝上
            
        current_pos = self.calculate_block_position(index, x_size, z_size, (0, 0, 0))
        next_pos = self.calculate_block_position(index + 1, x_size, z_size, (0, 0, 0))
        
        # 计算相对位置
        dx = next_pos[0] - current_pos[0]
        dy = next_pos[1] - current_pos[1]  
        dz = next_pos[2] - current_pos[2]
        
        # 优先考虑Y方向（垂直）
        if dy > 0:
            return 1  # 朝上
        elif dy < 0:
            return 0  # 朝下
        # 然后考虑X和Z方向（水平）
        elif dx > 0:
            return 5  # 朝东
        elif dx < 0:
            return 4  # 朝西
        elif dz > 0:
            return 3  # 朝南
        elif dz < 0:
            return 2  # 朝北
        else:
            return 1  # 默认朝上
    
    def calculate_placing_order(self, commands: List[str], x_size: int, z_size: int, 
                              start_pos: Tuple[int, int, int]) -> List[Dict]:
        """计算指令方块的放置顺序和属性"""
        blocks_data = []
        
        for i, command in enumerate(commands):
            pos = self.calculate_block_position(i, x_size, z_size, start_pos)
            block_type = self.determine_block_type(i, command)
            facing = self.determine_facing_direction(i, x_size, z_size)
            
            block_info = {
                'position': pos,
                'command': command,
                'mode': block_type,  # 0=脉冲, 1=连锁, 2=循环
                'facing_direction': facing,
                'conditional': False,
                'auto': False if i == 0 else True,  # 第一个脉冲方块需要红石激活(False)，连锁方块保持开启(True)
                'tick_delay': 0
            }
            
            blocks_data.append(block_info)
        
        return blocks_data
    
    def place_command_blocks(self, player: Player, blocks_data: List[Dict]) -> bool:
        """放置所有指令方块"""
        if not self.world_api:
            player.show("§c错误: 世界交互API不可用")
            return False
        
        try:
            total_blocks = len(blocks_data)
            player.show(f"§a开始放置 {total_blocks} 个指令方块...")
            
            for i, block_info in enumerate(blocks_data):
                # 创建指令方块更新数据包
                packet = self.world_api.make_packet_command_block_update(
                    position=block_info['position'],
                    command=block_info['command'],
                    mode=block_info['mode'],
                    need_redstone=not block_info['auto'],
                    tick_delay=block_info['tick_delay'],
                    conditional=block_info['conditional'],
                    name="",
                    should_track_output=True,
                    execute_on_first_tick=True
                )
                
                # 放置指令方块
                self.world_api.place_command_block(
                    packet,
                    facing=block_info['facing_direction'],
                    limit_seconds=self.config["放置延迟"],
                    limit_seconds2=self.config["放置延迟"],
                    in_dim="overworld"
                )
                
                # 显示进度
                if i % 10 == 0 or i == total_blocks - 1:
                    progress = (i + 1) / total_blocks * 100
                    player.show(f"§e放置进度: {i + 1}/{total_blocks} ({progress:.1f}%)")
                
                # 延迟以避免过快放置
                time.sleep(self.config["放置延迟"])
            
            player.show(f"§a成功放置了 {total_blocks} 个指令方块！")
            return True
            
        except Exception as e:
            player.show(f"§c放置指令方块时发生错误: {e}")
            fmts.print_err(f"[{self.name}] 放置错误: {e}")
            return False
    
    def console_list_command(self, args: list[str]):
        """处理控制台文件选择和导入命令"""
        try:
            mcf_folder = self.format_data_path("mcfunction")
            
            if not os.path.exists(mcf_folder):
                Print.print_err("mcfunction文件夹不存在")
                return
            
            # 获取所有支持的文件
            files = []
            for ext in self.config["支持的文件扩展名"]:
                for file in os.listdir(mcf_folder):
                    if file.endswith(ext):
                        files.append(file)
            
            if not files:
                Print.print_war("未找到mcfunction文件")
                Print.print_inf(f"请将文件放入: {mcf_folder}")
                return
            
            # 如果有参数，使用命令行模式
            if args:
                # 命令行参数模式: mcf <文件名或编号> <X> <Y> <Z> [X延展] [Z延展]
                if len(args) < 4:
                    Print.print_inf("用法: mcf <文件名或编号> <X坐标> <Y坐标> <Z坐标> [X延展] [Z延展]")
                    return
                
                # 解析文件参数
                file_param = args[0]
                
                # 判断是文件名还是编号
                selected_file = None
                if file_param.isdigit():
                    # 按编号选择
                    file_index = int(file_param) - 1
                    if 0 <= file_index < len(files):
                        selected_file = files[file_index]
                    else:
                        Print.print_err(f"无效的文件编号: {file_param}")
                        Print.print_inf("可用文件:")
                        for i, file in enumerate(files, 1):
                            Print.print_inf(f" {i} - {file}")
                        return
                else:
                    # 按文件名选择
                    if not file_param.endswith(('.mcfunction', '.txt')):
                        file_param += '.mcfunction'
                    
                    if file_param in files:
                        selected_file = file_param
                    else:
                        Print.print_err(f"文件不存在: {file_param}")
                        Print.print_inf("可用文件:")
                        for i, file in enumerate(files, 1):
                            Print.print_inf(f" {i} - {file}")
                        return
                
                # 解析坐标和尺寸参数
                try:
                    x_coord = int(args[1])
                    y_coord = int(args[2])
                    z_coord = int(args[3])
                    x_size = int(args[4]) if len(args) > 4 else self.config["默认X轴延展长度"]
                    z_size = int(args[5]) if len(args) > 5 else self.config["默认Z轴延展长度"]
                    
                    # 验证参数
                    if x_size <= 0 or z_size <= 0:
                        Print.print_err("延展长度必须大于0！")
                        return
                    
                    if x_size > 50 or z_size > 100:
                        Print.print_err("延展长度不能超过100，以避免性能问题！")
                        return
                    
                    # 开始导入
                    self.import_mcfunction_file(selected_file, x_coord, y_coord, z_coord, x_size, z_size)
                    
                except ValueError:
                    Print.print_err("参数错误: 请检查坐标和延展长度是否为有效数字")
                
                return
            
            # 无参数时进入交互式模式
            Print.print_inf(f"文件搜索路径: {mcf_folder}")
            Print.print_inf("请选择导入的 mcfunction 文件:")
            
            # 显示文件列表
            for i, file in enumerate(files, 1):
                file_path = os.path.join(mcf_folder, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = len([line for line in f if line.strip() and not line.strip().startswith('#')])
                    Print.print_inf(f" {i} - {file} ({lines}条指令)")
                except:
                    Print.print_inf(f" {i} - {file} (读取失败)")
            
            # 选择文件
            resp = utils.try_int(input(fmts.fmt_info(f"请选择 (1~{len(files)}): ")))
            if not resp or resp not in range(1, len(files) + 1):
                Print.print_err("输入错误, 已退出")
                return
            
            selected_file = files[resp - 1]
            Print.print_suc(f"已选择文件: {selected_file}")
            
            # 输入坐标
            Print.print_inf("请选择坐标获取方式:")
            Print.print_inf(" 1 - 手动输入坐标")
            Print.print_inf(" 2 - 从玩家位置获取坐标")
            
            coord_method = utils.try_int(input(fmts.fmt_info("请选择 (1~2): ")))
            if not coord_method or coord_method not in range(1, 3):
                Print.print_err("输入错误, 已退出")
                return
            
            if coord_method == 1:
                # 手动输入坐标
                Print.print_inf("请输入导入坐标:")
                x_input = input(fmts.fmt_info("X坐标: "))
                y_input = input(fmts.fmt_info("Y坐标: "))
                z_input = input(fmts.fmt_info("Z坐标: "))
                
                try:
                    x_coord = int(x_input)
                    y_coord = int(y_input)
                    z_coord = int(z_input)
                except ValueError:
                    Print.print_err("坐标输入错误, 已退出")
                    return
            else:
                # 从玩家位置获取坐标
                avali_players = list(self.game_ctrl.players)
                if not avali_players:
                    Print.print_err("当前没有在线玩家，无法获取坐标")
                    return
                
                if len(avali_players) == 1:
                    player_get = avali_players[0]
                    Print.print_inf(f"自动选择唯一在线玩家: {player_get.name}")
                else:
                    Print.print_inf("请选择玩家以获取其坐标:")
                    for i, j in enumerate(avali_players):
                        Print.print_inf(f" {i + 1} - {j.name}")
                    resp = utils.try_int(
                        input(fmts.fmt_info(f"请选择 (1~{len(avali_players)}): "))
                    )
                    if not resp or resp not in range(1, len(avali_players) + 1):
                        Print.print_err("输入错误, 已退出")
                        return
                    player_get = avali_players[resp - 1]
                
                try:
                    _, x_coord, y_coord, z_coord = player_get.getPos()
                    Print.print_suc(f"成功获取 {player_get.name} 的坐标: ({x_coord}, {y_coord}, {z_coord})")
                except Exception as e:
                    Print.print_err(f"获取玩家坐标失败: {e}")
                    return
            
            # 输入尺寸 (可选)
            Print.print_inf("请输入布局尺寸 (按回车使用默认值):")
            x_size_input = input(fmts.fmt_info(f"X轴延展长度 (默认{self.config['默认X轴延展长度']}): "))
            z_size_input = input(fmts.fmt_info(f"Z轴延展长度 (默认{self.config['默认Z轴延展长度']}): "))
            
            # 解析尺寸参数
            x_size = self.config["默认X轴延展长度"]
            z_size = self.config["默认Z轴延展长度"]
            
            if x_size_input.strip():
                try:
                    x_size = int(x_size_input)
                except ValueError:
                    Print.print_war("X轴延展长度输入错误，使用默认值")
            
            if z_size_input.strip():
                try:
                    z_size = int(z_size_input)
                except ValueError:
                    Print.print_war("Z轴延展长度输入错误，使用默认值")
            
            # 验证参数
            if x_size <= 0 or z_size <= 0:
                Print.print_err("延展长度必须大于0！")
                return
            
            if x_size > 50 or z_size > 50:
                Print.print_err("延展长度不能超过50，以避免性能问题！")
                return
            
            # 确认导入
            Print.print_inf(f"确认导入设置:")
            Print.print_inf(f"  文件: {selected_file}")
            Print.print_inf(f"  坐标: ({x_coord}, {y_coord}, {z_coord})")
            Print.print_inf(f"  尺寸: {x_size}x{z_size}")
            
            confirm = input(fmts.fmt_info("确认导入? (y/N): ")).lower()
            if confirm not in ['y', 'yes']:
                Print.print_inf("已取消导入")
                return
            
            # 开始导入
            self.import_mcfunction_file(selected_file, x_coord, y_coord, z_coord, x_size, z_size)
            
        except KeyboardInterrupt:
            Print.print_inf("用户取消操作")
        except Exception as e:
            Print.print_err(f"处理命令时发生错误: {e}")
    
    def import_mcfunction_file(self, file_name: str, x_coord: int, y_coord: int, z_coord: int, x_size: int, z_size: int):
        """导入mcfunction文件"""
        try:
            file_path = self.format_data_path("mcfunction", file_name)
            
            Print.print_suc(f"正在解析文件: {file_name}")
            Print.print_inf(f"起始坐标: ({x_coord}, {y_coord}, {z_coord})")
            Print.print_inf(f"布局尺寸: {x_size}x{z_size}")
            
            # 使用用户提供的坐标
            start_pos = (x_coord, y_coord, z_coord)
            
            # 解析mcfunction文件
            commands = self.parse_mcfunction(file_path)
            if not commands:
                Print.print_err("文件解析失败或无有效指令")
                return
            
            Print.print_suc(f"解析到 {len(commands)} 条指令")
            
            # 计算总需要的方块数和层数
            total_per_layer = x_size * z_size
            needed_layers = math.ceil(len(commands) / total_per_layer)
            
            if needed_layers > self.config["默认Y轴高度"]:
                Print.print_war(f"需要 {needed_layers} 层高度，可能超出限制")
                Print.print_inf("建议增大X或Z延展长度以减少层数")
            
            # 计算放置方案
            blocks_data = self.calculate_placing_order(commands, x_size, z_size, start_pos)
            
            # 开始放置
            success = self.place_command_blocks_console(blocks_data, file_name)
            
            if success:
                Print.print_suc("导入完成！指令方块链已生成")
                Print.print_inf(f"提示: 对第一个指令方块 {start_pos} 给予红石信号即可启动")
                
        except Exception as e:
            Print.print_err(f"导入文件时发生错误: {e}")
    
    def place_command_blocks_console(self, blocks_data: List[Dict], file_name: str = "") -> bool:
        """控制台版本的放置指令方块函数"""
        if not self.world_api:
            Print.print_err("世界交互API不可用")
            return False
        
        try:
            total_blocks = len(blocks_data)
            start_time = time.time()  # 记录开始时间
            Print.print_inf(f"开始放置 {total_blocks} 个指令方块...")
            
            # 发送开始导入的游戏内提示
            start_msg = f'execute as @a at @s run titleraw @s actionbar {{"rawtext":[{{"text":"开始导入 {file_name} ({total_blocks}个指令方块)"}}]}}'
            
            try:
                self.game_ctrl.sendcmd(start_msg)
            except:
                pass
            
            for i, block_info in enumerate(blocks_data):
                # 创建指令方块更新数据包
                packet = self.world_api.make_packet_command_block_update(
                    position=block_info['position'],
                    command=block_info['command'],
                    mode=block_info['mode'],
                    need_redstone=not block_info['auto'],
                    tick_delay=block_info['tick_delay'],
                    conditional=block_info['conditional'],
                    name="",
                    should_track_output=True,
                    execute_on_first_tick=True
                )
                
                # 放置指令方块
                self.world_api.place_command_block(
                    packet,
                    facing=block_info['facing_direction'],
                    limit_seconds=self.config["放置延迟"],
                    limit_seconds2=self.config["放置延迟"],
                    in_dim="overworld"
                )
                
                # 显示控制台进度
                if i % 10 == 0 or i == total_blocks - 1:
                    progress = (i + 1) / total_blocks * 100
                    elapsed_time = time.time() - start_time
                    Print.print_inf(f"放置进度: {i + 1}/{total_blocks} ({progress:.1f}%) - 用时 {elapsed_time:.1f}秒")
                    
                    # 每10个方块或最后一个方块发送游戏内进度提示
                    current = i + 1
                    progress_msg = f'execute as @a at @s run titleraw @s actionbar {{"rawtext":[{{"text":"正在导入 {file_name}: {current}/{total_blocks} ({progress:.1f}%) - {elapsed_time:.1f}秒"}}]}}'
                    
                    try:
                        self.game_ctrl.sendcmd(progress_msg)
                    except:
                        pass
                
                # 延迟以避免过快放置
                time.sleep(self.config["放置延迟"])
            
            # 发送完成提示
            total_time = time.time() - start_time
            complete_msg = f'execute as @a at @s run titleraw @s actionbar {{"rawtext":[{{"text":"导入完成！{file_name} ({total_blocks}个方块已生成) - 总用时 {total_time:.1f}秒"}}]}}'
            try:
                self.game_ctrl.sendcmd(complete_msg)
            except:
                pass
            
            Print.print_suc(f"成功放置了 {total_blocks} 个指令方块！总用时 {total_time:.1f}秒")
            return True
            
        except Exception as e:
            Print.print_err(f"放置指令方块时发生错误: {e}")
            return False


# 注册插件
entry = plugin_entry(McFunctionImporter)