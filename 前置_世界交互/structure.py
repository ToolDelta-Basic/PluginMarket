from dataclasses import dataclass
import nbtlib
import numpy


@dataclass
class BlockLayer:
    "记录了一个方块中某一层的数据"

    name: nbtlib.tag.String
    "方块 ID 名称"
    states: nbtlib.tag.Compound
    "方块状态数据"
    val: nbtlib.tag.Short
    "方块特殊值"
    version: nbtlib.tag.Int
    "此方块的版本"


@dataclass
class Block:
    "记录了结构中某一个方块的数据"

    foreground: BlockLayer | None
    """
    这个方块的前景层。
    可能不存在
    """
    background: BlockLayer | None
    """
    这个方块的背景层。可能不存在。
    这一层通常是不存在的，除非这是一个含水方块
    """
    entity_data: nbtlib.tag.Compound | None
    """
    方块实体数据。
    可能不存在
    """


class Structure:
    "记录了获取的世界结构 (不含实体数据)"

    format_version: nbtlib.tag.Compound
    "目前始终为 1"
    size: nbtlib.tag.List[nbtlib.tag.Int]
    "由三个整数组成的列表，描述结构的尺寸"
    structure_world_origin: nbtlib.tag.List[nbtlib.tag.Int]
    """
    由三个整数组成的列表，描述结构最初保存在何处。

    等于保存结构方块的位置与设置的偏移量的加和。
    这用于确定结构在加载时，相应实体的加载位置。

    实体会在这个坐标的计算结果上加载：
        它在结构中旧位置减去 structure_world_origin，
        再加上结构加载位置的原点。
    """

    _block_matrix_0: numpy.ndarray
    _block_matrix_1: numpy.ndarray
    _palette: list[BlockLayer]
    _block_entity_data: dict[int, nbtlib.tag.Compound]

    def __init__(self, template: nbtlib.tag.Compound):
        # This is the data we can get immediately
        self.format_version = template["format_version"]
        self.size = template["size"]
        self.structure_world_origin = template["structure_world_origin"]

        # These data must get step by step
        structure: nbtlib.tag.Compound = template["structure"]
        block_palettes: nbtlib.tag.List = structure["palette"]["default"][
            "block_palette"
        ]
        block_position_data: nbtlib.tag.Compound = structure["palette"]["default"][
            "block_position_data"
        ]

        # Then, we can start to init the block matrix and block palette
        self._block_matrix_0 = numpy.array(
            structure["block_indices"][0], dtype=numpy.int32
        )
        self._block_matrix_1 = numpy.array(
            structure["block_indices"][1], dtype=numpy.int32
        )
        self._palette = [
            BlockLayer(i["name"], i["states"], i["val"], i["version"])
            for i in block_palettes
        ]

        # At last, we get the block entity data
        self._block_entity_data = {}
        for key, value in block_position_data.items():
            value: nbtlib.tag.Compound

            block_entity_data: nbtlib.tag.Compound | None = value.get(
                "block_entity_data"
            )
            if block_entity_data is None:
                continue

            self._block_entity_data[int(key)] = block_entity_data

    def get_block(self, position: tuple[int, int, int]) -> Block:
        """
        获取该结构中的一个方块的数据。
        使用者应当确保返回的 Block 不被修改

        Args:
            position (tuple[int, int, int]): 此方块在结构内的相对坐标
        Raises:
            ValueError: 超出结构尺寸
        Returns:
            Block: 方块数据类
        """

        # Get basic data
        x, y, z = position
        size_x, size_y, size_z = int(self.size[0]), int(self.size[1]), int(self.size[2])  # type: ignore

        # Check out of index
        if x not in range(size_x) or y not in range(size_y) or z not in range(size_z):
            raise ValueError(f"超出结构尺寸: ({x}, {y}, {z})")

        # Get index and init some vars
        index = x * size_y * size_z + y * size_z + z
        fore_ground = None
        back_ground = None
        entity_data = None

        # Get id of forceground and background
        force_ground_id = self._block_matrix_0[index]
        back_ground_id = self._block_matrix_1[index]

        # Get block from layer
        if force_ground_id != -1:
            fore_ground = self._palette[force_ground_id]
        if back_ground_id != -1:
            back_ground = self._palette[back_ground_id]

        # Get block NBT data
        if index in self._block_entity_data:
            entity_data = self._block_entity_data[index]

        # Return
        return Block(fore_ground, back_ground, entity_data)

    def block_palette(self) -> list[BlockLayer]:
        """
        block_palette 返回当前结构的底层调色板。
        使用者应保证返回的列表不被修改

        Returns:
            list[BlockLayer]: 当前结构的底层调色板
        """
        return self._palette

    def block_matrix(self, layer: int) -> numpy.ndarray:
        """
        block_matrix 返回 layer 所指示的层的密集方块矩阵。
        返回的密集方块矩阵的元素都是 numpy.int32 类型。
        使用者应保证返回的密集方块矩阵不被修改

        Args:
            layer (int): 要获取的层

        Returns:
            numpy.ndarray: 目标层的密集方块矩阵表示
        """
        if layer == 0:
            return self._block_matrix_0
        return self._block_matrix_1

    def block_nbt_data(self) -> list[nbtlib.tag.Compound]:
        """
        block_nbt_data 返回该结构中所有的 NBT 方块
        使用者应保证返回的字典不被修改

        Returns:
            list[nbtlib.tag.Compound]: 该结构中所有的 NBT 方块
        """
        result: list[nbtlib.tag.Compound] = []
        for _, value in self._block_entity_data.items():
            result.append(value)
        return result
