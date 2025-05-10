from typing import TYPE_CHECKING, Dict, List, Any
from tooldelta import fmts, utils
from .bdx_utils.reader import read_bdx_file
# from .state_dump import parse_block_states
import json
import os

if TYPE_CHECKING:
    from . import BDXExporter

def parse_block_states(states_str: str) -> dict:
    """将状态字符串解析为字典格式"""
    if not states_str or states_str == "{}":
        return {}
    
    try:
        # 尝试直接解析为JSON
        if states_str.startswith("{") and states_str.endswith("}"):
            return json.loads(states_str)
        
        # 尝试解析方括号格式
        if states_str.startswith("[") and states_str.endswith("]"):
            states_str = states_str[1:-1]
            result = {}
            parts = states_str.split(",")
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 去掉可能的引号
                    if key.startswith('"') and key.endswith('"'):
                        key = json.loads(key)
                    
                    # 处理布尔值
                    if value == "true":
                        value = True
                    elif value == "false":
                        value = False
                    else:
                        try:
                            value = json.loads(value)
                        except:
                            pass
                    
                    result[key] = value
            return result
        
        return {}
    except Exception:
        return {}
def import_bdx_file(sys: "BDXExporter", filepath: str, import_position):
    """导入BDX文件并在指定位置放置结构"""
    if not os.path.exists(filepath):
        fmts.print_err(f"找不到BDX文件：{filepath}")
        return False
    
    try:
        fmts.print_inf(f"正在解析BDX文件 {filepath}...")
        author, blocks = read_bdx_file(filepath)
        fmts.print_inf(f"文件作者: {author}")
        fmts.print_inf(f"包含 {len(blocks)} 个方块")
        
        # 计算偏移量
        import_x, import_y, import_z = import_position
        
        # 开始放置方块
        return place_blocks(sys, blocks, (import_x, import_y, import_z))
        
    except Exception as e:
        fmts.print_err(f"导入BDX文件时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@utils.thread_func("bdx导入线程")
def place_blocks(sys: "BDXExporter", blocks: List[Dict[str, Any]], position):
    """根据BDX文件中的方块信息放置方块"""
    import_x, import_y, import_z = position
    total_blocks = len(blocks)
    processed = 0
    
    fmts.print_inf(f"开始在 ({import_x}, {import_y}, {import_z}) 导入结构...")
    
    game_ctrl = sys.game_ctrl
    intr = sys.intr
    
    # 移动到导入位置
    game_ctrl.sendcmd(f"tp {import_x} {import_y} {import_z}")
    
    # 按类型放置方块
    chest_blocks = []
    command_blocks = []
    
    # 普通方块优先放置
    for block in blocks:
        block_type = block.get("type", "simple")
        block_name = block.get("name", "minecraft:air")
        block_x = import_x + block.get("x", 0)
        block_y = import_y + block.get("y", 0)
        block_z = import_z + block.get("z", 0)
        
        # 跳过空气方块
        if block_name == "minecraft:air":
            processed += 1
            continue
        
        # 检查方块类型，分类处理
        if block_type == "chest":
            chest_blocks.append(block)
            continue
        elif block_type == "command":
            command_blocks.append(block)
            continue
        
        # 放置普通方块或带状态的方块
        try:
            if block_type == "simple":
                block_data = block.get("data", 0)
                # 使用正确的方法放置方块，改用send_command
                cmd = f"setblock {block_x} {block_y} {block_z} {block_name} {block_data}"
                game_ctrl.sendcmd(cmd)
            elif block_type == "states":
                block_states = block.get("states", "{}")
                try:
                    states_dict = parse_block_states(block_states)
                    # 改用send_command，根据方块状态生成命令
                    states_str = json.dumps(states_dict)
                    cmd = f"setblock {block_x} {block_y} {block_z} {block_name} 0 replace {states_str}"
                    game_ctrl.sendcmd(cmd)
                except Exception as e:
                    # 如果状态解析失败，尝试直接放置方块
                    cmd = f"setblock {block_x} {block_y} {block_z} {block_name}"
                    game_ctrl.sendcmd(cmd)
            
            processed += 1
            if processed % 10 == 0:
                fmts.print_inf(f"已放置 {processed}/{total_blocks} 个方块...", end="\r")
                
        except Exception as e:
            fmts.print_err(f"放置方块 {block_name} 在 ({block_x}, {block_y}, {block_z}) 时出错: {str(e)}")
    
    # 放置带特殊数据的方块
    # 命令方块
    for block in command_blocks:
        try:
            block_name = block.get("name", "minecraft:command_block")
            block_x = import_x + block.get("x", 0)
            block_y = import_y + block.get("y", 0)
            block_z = import_z + block.get("z", 0)
            block_data = block.get("data", 0)
            command = block.get("command", "")
            
            # 首先放置命令方块，改用sendcmd
            cmd = f"setblock {block_x} {block_y} {block_z} {block_name} {block_data}"
            game_ctrl.sendcmd(cmd)
            
            # 然后设置其命令和属性
            conditional = "true" if block.get("conditional", False) else "false"
            auto = "false" if block.get("needs_redstone", True) else "true"
            
            # 使用blockdata设置命令方块数据
            cmd = f'blockdata {block_x} {block_y} {block_z} {{Command:"{command}",auto:{auto},conditionMet:{conditional}}}'
            game_ctrl.sendcmd(cmd)
            
            processed += 1
            if processed % 10 == 0:
                fmts.print_inf(f"已放置 {processed}/{total_blocks} 个方块...", end="\r")
                
        except Exception as e:
            fmts.print_err(f"放置命令方块在 ({block_x}, {block_y}, {block_z}) 时出错: {str(e)}")
    
    # 箱子类方块
    for block in chest_blocks:
        try:
            block_name = block.get("name", "minecraft:chest")
            block_x = import_x + block.get("x", 0)
            block_y = import_y + block.get("y", 0)
            block_z = import_z + block.get("z", 0)
            block_data = block.get("data", 0)
            items = block.get("items", [])
            
            # 首先放置箱子，改用sendcmd
            cmd = f"setblock {block_x} {block_y} {block_z} {block_name} {block_data}"
            game_ctrl.sendcmd(cmd)
            
            # 然后填充物品
            for item in items:
                item_name = item.get("item", "")
                count = item.get("count", 1)
                data = item.get("data", 0)
                slot = item.get("slot", 0)
                
                # 使用replaceitem命令放置物品
                cmd = f'replaceitem block {block_x} {block_y} {block_z} slot.container {slot} {item_name} {count} {data}'
                game_ctrl.sendcmd(cmd)
            
            processed += 1
            if processed % 10 == 0:
                fmts.print_inf(f"已放置 {processed}/{total_blocks} 个方块...", end="\r")
                
        except Exception as e:
            fmts.print_err(f"放置箱子 {block_name} 在 ({block_x}, {block_y}, {block_z}) 时出错: {str(e)}")
    
    fmts.print_inf(f"已完成 {processed}/{total_blocks} 个方块的导入")
    fmts.print_suc(f"结构已成功导入到 ({import_x}, {import_y}, {import_z})")
    return True
