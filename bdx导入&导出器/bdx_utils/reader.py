from io import BytesIO, BufferedReader
from struct import unpack
import brotli
from typing import List, Dict, Tuple, Optional, Any
from .structs import ChestSlot, ChestData


class BDXContentReader:
    def __init__(self, data: bytes):
        self.reader = BytesIO(data)
        self.position = 0
        self.constants: Dict[int, str] = {}
        self.x, self.y, self.z = 0, 0, 0

    def read_op(self) -> int:
        op_byte = self.reader.read(1)
        if not op_byte:
            return -1  # EOF
        return int.from_bytes(op_byte, byteorder="big")

    def read_string(self):
        # 添加错误处理，使用替代字符替换无法解码的字节
        try:
            result = self.read_bytes(self.read_int())
            return result.decode('utf-8', errors='replace')
        except Exception as e:
            # 如果解码失败，尝试使用其他编码或者返回占位符
            fmts.print_err(f"字符串解码错误: {e}")
            return f"[无法解码的字符串-{len(result)}字节]"

    def parse_content(self) -> List[Dict[str, Any]]:
        """解析BDX内容，返回所有放置的方块信息"""
        blocks = []
        
        while True:
            op = self.read_op()
            if op == -1:  # EOF
                break
                
            # 处理常量字符串定义
            if op == 1:  # CreateConstantString
                string = self.read_string()
                self.constants[len(self.constants)] = string
                
            # 处理坐标变化
            elif op == 14:  # AddXValue
                self.x += 1
            elif op == 15:  # SubtractXValue
                self.x -= 1
            elif op == 16:  # AddYValue
                self.y += 1
            elif op == 17:  # SubtractYValue
                self.y -= 1
            elif op == 18:  # AddZValue
                self.z += 1
            elif op == 19:  # SubtractZValue
                self.z -= 1
            elif op == 20:  # AddInt16XValue
                self.x += unpack(">h", self.reader.read(2))[0]
            elif op == 22:  # AddInt16YValue
                self.y += unpack(">h", self.reader.read(2))[0]
            elif op == 24:  # AddInt16ZValue
                self.z += unpack(">h", self.reader.read(2))[0]
            elif op == 21:  # AddInt32XValue
                self.x += unpack(">i", self.reader.read(4))[0]
            elif op == 23:  # AddInt32YValue
                self.y += unpack(">i", self.reader.read(4))[0]
            elif op == 25:  # AddInt32ZValue
                self.z += unpack(">i", self.reader.read(4))[0]
            elif op == 28:  # AddInt8XValue
                self.x += int.from_bytes(self.reader.read(1), byteorder="big", signed=True)
            elif op == 29:  # AddInt8YValue
                self.y += int.from_bytes(self.reader.read(1), byteorder="big", signed=True)
            elif op == 30:  # AddInt8ZValue
                self.z += int.from_bytes(self.reader.read(1), byteorder="big", signed=True)
                
            # 处理方块放置指令
            elif op == 7:  # PlaceBlock
                block_id = unpack(">H", self.reader.read(2))[0]
                block_data = unpack(">H", self.reader.read(2))[0]
                block_name = self.constants.get(block_id, "unknown")
                blocks.append({
                    "type": "simple",
                    "name": block_name,
                    "data": block_data,
                    "x": self.x,
                    "y": self.y,
                    "z": self.z
                })
                
            elif op == 5:  # PlaceBlockWithBlockStates
                block_id = unpack(">H", self.reader.read(2))[0]
                states_id = unpack(">H", self.reader.read(2))[0]
                block_name = self.constants.get(block_id, "unknown")
                block_states = self.constants.get(states_id, "{}")
                blocks.append({
                    "type": "states",
                    "name": block_name,
                    "states": block_states,
                    "x": self.x,
                    "y": self.y,
                    "z": self.z
                })
                
            elif op == 36:  # PlaceCommandBlockWithCommandBlockData
                data = unpack(">H", self.reader.read(2))[0]
                mode = unpack(">I", self.reader.read(4))[0]
                command = self.read_string()
                custom_name = self.read_string()
                last_output = self.read_string()
                tick_delay = unpack(">I", self.reader.read(4))[0]
                execute_on_first_tick = bool(int.from_bytes(self.reader.read(1), byteorder="big"))
                track_output = bool(int.from_bytes(self.reader.read(1), byteorder="big"))
                conditional = bool(int.from_bytes(self.reader.read(1), byteorder="big"))
                needs_redstone = bool(int.from_bytes(self.reader.read(1), byteorder="big"))
                
                block_types = ["command_block", "repeating_command_block", "chain_command_block"]
                block_name = f"minecraft:{block_types[mode]}"
                
                blocks.append({
                    "type": "command",
                    "name": block_name,
                    "data": data,
                    "command": command,
                    "custom_name": custom_name,
                    "last_output": last_output,
                    "tick_delay": tick_delay,
                    "execute_on_first_tick": execute_on_first_tick,
                    "track_output": track_output,
                    "conditional": conditional,
                    "needs_redstone": needs_redstone,
                    "x": self.x,
                    "y": self.y,
                    "z": self.z
                })
                
            elif op == 40:  # PlaceBlockWithChestData
                block_id = unpack(">H", self.reader.read(2))[0]
                block_data = unpack(">H", self.reader.read(2))[0]
                slot_count = int.from_bytes(self.reader.read(1), byteorder="big")
                
                chest_slots = []
                for _ in range(slot_count):
                    item_name = self.read_string()
                    count = int.from_bytes(self.reader.read(1), byteorder="big")
                    data = unpack(">H", self.reader.read(2))[0]
                    slot_id = int.from_bytes(self.reader.read(1), byteorder="big")
                    chest_slots.append({
                        "item": item_name,
                        "count": count,
                        "data": data,
                        "slot": slot_id
                    })
                
                block_name = self.constants.get(block_id, "unknown")
                blocks.append({
                    "type": "chest",
                    "name": block_name,
                    "data": block_data,
                    "items": chest_slots,
                    "x": self.x,
                    "y": self.y,
                    "z": self.z
                })
                
        return blocks


def read_bdx_file(filepath):
    """读取BDX文件并解析成方块数据"""
    try:
        with open(filepath, "rb") as f:
            # 检查文件头
            magic = f.read(4)
            if magic != b'BDX\x00':
                raise ValueError("不是有效的BDX文件")
                
            # 读取版本号和作者信息
            reader = BDXReader(f)
            version = reader.read_byte()
            author = reader.read_string()
            
            try:
                # 尝试解析方块内容
                blocks = reader.parse_content()
                return author, blocks
            except UnicodeDecodeError:
                # 特别处理字符串解码错误
                fmts.print_err("无法解析BDX文件中的文本内容，尝试使用二进制兼容模式")
                # 重置文件指针，重新尝试读取
                f.seek(5)  # 跳过文件头和版本号
                author_len = struct.unpack('I', f.read(4))[0]
                author = f.read(author_len).decode('latin1')  # 使用latin1编码，它可以处理任何字节
                
                # 使用二进制兼容模式解析剩余内容
                blocks = BDXReader(f, binary_compatible=True).parse_content()
                return author, blocks
    except Exception as e:
        fmts.print_err(f"读取BDX文件失败: {e}")
        raise

class BDXReader:
    def __init__(self, file, binary_compatible=False):
        self.file = file
        self.binary_compatible = binary_compatible
        
    def read_string(self):
        length = self.read_int()
        if length <= 0:
            return ""
            
        data = self.read_bytes(length)
        if self.binary_compatible:
            # 使用latin1编码，它可以处理任何字节值
            return data.decode('latin1')
        
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试使用latin1
            fmts.print_err(f"UTF-8解码失败，切换到二进制兼容模式")
            return data.decode('latin1')
