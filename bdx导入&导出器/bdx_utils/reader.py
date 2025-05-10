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

    def read_string(self) -> str:
        result = bytearray()
        while True:
            b = self.reader.read(1)
            if b == b'\x00' or not b:
                break
            result.extend(b)
        return result.decode('utf-8')

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


def read_bdx_file(file_path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """读取BDX文件，返回作者信息和所有方块信息"""
    with open(file_path, "rb") as f:
        header = f.read(3)
        if header != b"BD@":
            raise ValueError("不是有效的BDX文件")
        
        compressed_data = f.read()
        decompressed_data = brotli.decompress(compressed_data)
        
        if not decompressed_data.startswith(b"BDX\x00"):
            raise ValueError("BDX文件格式错误")
            
        # 提取作者信息
        author_end = decompressed_data.find(b'\x00', 4)
        author = decompressed_data[4:author_end].decode('utf-8')
        
        # 提取BDX内容
        content_start = author_end + 1
        content_end = decompressed_data.rfind(b"XE")
        
        if content_end == -1:
            content_end = len(decompressed_data)
            
        content = decompressed_data[content_start:content_end]
        
        reader = BDXContentReader(content)
        blocks = reader.parse_content()
        
        return author, blocks
