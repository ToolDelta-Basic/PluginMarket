"""流式gzip/NBT扫描工具"""

from __future__ import annotations

import gzip
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, BinaryIO, cast

MAX_DECOMPRESSED_BYTES = 1 << 30
MAX_DEPTH = 128
COPY_BUFFER_SIZE = 1 << 20

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


class NBTStreamError(ValueError):
    """流式 NBT 数据无效"""


@dataclass(frozen=True)
class ExtractedArray:
    path: Path
    length: int


@dataclass(frozen=True)
class ExtractedNumericList:
    path: Path
    length: int
    tag_type: int


@dataclass(frozen=True)
class TaggedValue:
    value: Any
    tag_type: int


@dataclass(frozen=True)
class ScanResult:
    root_name: str
    values: dict[tuple[str, ...], Any]
    arrays: dict[tuple[str, ...], ExtractedArray]
    list_lengths: dict[tuple[str, ...], int]
    numeric_lists: dict[tuple[str, ...], ExtractedNumericList]
    compound_children: dict[tuple[str, ...], tuple[str, ...]]


class _LimitedReader:
    def __init__(self, source: BinaryIO, limit: int) -> None:
        self.source = source
        self.limit = limit
        self.total = 0

    def read_exact(self, size: int) -> bytes:
        if size < 0:
            raise NBTStreamError(f"NBT 长度不能为负数: {size}")
        if self.total + size > self.limit:
            raise NBTStreamError(f"NBT 解压数据超过限制: {self.limit} 字节")
        data = self.source.read(size)
        if len(data) != size:
            raise NBTStreamError("NBT 数据意外结束")
        self.total += size
        return data

    def copy_exact(self, size: int, target: BinaryIO | None = None) -> None:
        remaining = size
        while remaining:
            chunk = self.read_exact(min(remaining, COPY_BUFFER_SIZE))
            if target is not None:
                target.write(chunk)
            remaining -= len(chunk)


class NBTStreamScanner:
    """扫描 NBT，仅物化指定小字段，并将指定 ByteArray 提取到磁盘"""

    def __init__(
        self,
        scalar_paths: set[tuple[str, ...]],
        compound_paths: set[tuple[str, ...]],
        byte_array_paths: set[tuple[str, ...]],
        list_count_paths: set[tuple[str, ...]],
        output_directory: Path,
        *,
        numeric_list_paths: set[tuple[str, ...]] | None = None,
        typed_paths: set[tuple[str, ...]] | None = None,
        long_array_paths: set[tuple[str, ...]] | None = None,
        compound_name_paths: set[tuple[str, ...]] | None = None,
        record_callbacks: dict[tuple[str, ...], Callable[[str, Any], None]]
        | None = None,
        max_decompressed_bytes: int = MAX_DECOMPRESSED_BYTES,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        self.scalar_paths = scalar_paths
        self.compound_paths = compound_paths
        self.byte_array_paths = byte_array_paths
        self.list_count_paths = list_count_paths
        self.output_directory = output_directory
        self.numeric_list_paths = numeric_list_paths or set()
        self.typed_paths = typed_paths or set()
        self.long_array_paths = long_array_paths or set()
        self.compound_name_paths = compound_name_paths or set()
        self.record_callbacks = record_callbacks or {}
        self.max_decompressed_bytes = max_decompressed_bytes
        self.max_depth = max_depth
        self.values: dict[tuple[str, ...], Any] = {}
        self.arrays: dict[tuple[str, ...], ExtractedArray] = {}
        self.list_lengths: dict[tuple[str, ...], int] = {}
        self.numeric_lists: dict[tuple[str, ...], ExtractedNumericList] = {}
        self.compound_children: dict[tuple[str, ...], list[str]] = {}
        self.byteorder = ">"
        all_paths = (
            scalar_paths
            | compound_paths
            | byte_array_paths
            | list_count_paths
            | self.numeric_list_paths
            | self.typed_paths
            | self.long_array_paths
            | self.compound_name_paths
            | set(self.record_callbacks)
        )
        self.prefixes = {
            path[:index] for path in all_paths for index in range(1, len(path) + 1)
        }

    def scan_gzip(self, path: str | Path) -> ScanResult:
        return self.scan(path, gzipped=True, byteorder="big")

    def scan(
        self,
        path: str | Path,
        *,
        gzipped: bool,
        byteorder: str,
    ) -> ScanResult:
        if byteorder not in ("big", "little"):
            raise ValueError(f"不支持的 NBT 字节序: {byteorder}")
        self.byteorder = ">" if byteorder == "big" else "<"
        try:
            opener = gzip.open(path, "rb") if gzipped else Path(path).open("rb")
            with opener as stream:
                reader = _LimitedReader(
                    cast(BinaryIO, stream), self.max_decompressed_bytes
                )
                root_type = self._u8(reader)
                if root_type != TAG_COMPOUND:
                    raise NBTStreamError(f"NBT 根标签不是 Compound: {root_type}")
                root_name = self._string(reader)
                self._read_compound(reader, (), False, False, 0)
                # 强制读取到文件尾；gzip 输入同时验证 CRC。
                if stream.read(1):
                    raise NBTStreamError("NBT 根标签结束后存在多余数据")
        except (gzip.BadGzipFile, OSError, EOFError) as error:
            raise NBTStreamError(f"无法读取 gzip/NBT 数据: {error}") from error
        return ScanResult(
            root_name,
            self.values,
            self.arrays,
            self.list_lengths,
            self.numeric_lists,
            {path: tuple(names) for path, names in self.compound_children.items()},
        )

    def _read_compound(
        self,
        reader: _LimitedReader,
        path: tuple[str, ...],
        materialize: bool,
        preserve_types: bool,
        depth: int,
    ) -> dict[str, Any] | None:
        self._check_depth(depth)
        result: dict[str, Any] | None = {} if materialize else None
        record_callback = self.record_callbacks.get(path)
        while True:
            tag_type = self._u8(reader)
            if tag_type == TAG_END:
                return result
            name = self._string(reader)
            if path in self.compound_name_paths:
                self.compound_children.setdefault(path, []).append(name)
            child_path = (*path, name)
            child_materialize = (
                materialize
                or record_callback is not None
                or child_path in self.compound_paths
            )
            child_preserve = preserve_types or child_path in self.typed_paths
            interested = child_materialize or child_path in self.prefixes
            value = self._read_payload(
                reader,
                tag_type,
                child_path,
                child_materialize,
                interested,
                child_preserve,
                depth + 1,
            )
            if record_callback is not None:
                record_callback(name, value)
            elif materialize and result is not None:
                result[name] = value
            elif child_path in self.scalar_paths or child_path in self.compound_paths:
                self.values[child_path] = value

    def _read_payload(
        self,
        reader: _LimitedReader,
        tag_type: int,
        path: tuple[str, ...],
        materialize: bool,
        interested: bool,
        preserve_types: bool,
        depth: int,
    ) -> Any:
        self._check_depth(depth)
        formats = {
            TAG_BYTE: (">b", 1),
            TAG_SHORT: (">h", 2),
            TAG_INT: (">i", 4),
            TAG_LONG: (">q", 8),
            TAG_FLOAT: (">f", 4),
            TAG_DOUBLE: (">d", 8),
        }
        if tag_type in formats:
            fmt, size = formats[tag_type]
            value = struct.unpack(self.byteorder + fmt[1:], reader.read_exact(size))[0]
            return TaggedValue(value, tag_type) if preserve_types else value
        if tag_type == TAG_STRING:
            value = self._string(reader)
            return TaggedValue(value, tag_type) if preserve_types else value
        if tag_type == TAG_BYTE_ARRAY:
            length = self._length(reader)
            if path in self.byte_array_paths:
                output = self.output_directory / f"array_{len(self.arrays)}.bin"
                with output.open("wb") as target:
                    reader.copy_exact(length, target)
                self.arrays[path] = ExtractedArray(output, length)
                return None
            if materialize:
                value = reader.read_exact(length)
                return TaggedValue(value, tag_type) if preserve_types else value
            reader.copy_exact(length)
            return None
        if tag_type in (TAG_INT_ARRAY, TAG_LONG_ARRAY):
            length = self._length(reader)
            item_size = 4 if tag_type == TAG_INT_ARRAY else 8
            if tag_type == TAG_LONG_ARRAY and path in self.long_array_paths:
                output = self.output_directory / f"long_array_{len(self.arrays)}.bin"
                with output.open("wb") as target:
                    reader.copy_exact(length * item_size, target)
                self.arrays[path] = ExtractedArray(output, length)
                return None
            if materialize or path in self.scalar_paths:
                raw = reader.read_exact(length * item_size)
                code = "i" if tag_type == TAG_INT_ARRAY else "q"
                value = list(struct.unpack(f"{self.byteorder}{length}{code}", raw))
                return TaggedValue(value, tag_type) if preserve_types else value
            reader.copy_exact(length * item_size)
            return None
        if tag_type == TAG_LIST:
            child_type = self._u8(reader)
            length = self._length(reader)
            if path in self.list_count_paths:
                self.list_lengths[path] = length
            if path in self.numeric_list_paths:
                sizes = {
                    TAG_BYTE: 1,
                    TAG_SHORT: 2,
                    TAG_INT: 4,
                    TAG_LONG: 8,
                    TAG_FLOAT: 4,
                    TAG_DOUBLE: 8,
                }
                if child_type not in sizes:
                    raise NBTStreamError(
                        f"目标数值列表 {path} 的子标签不是数值类型: {child_type}"
                    )
                output = self.output_directory / f"list_{len(self.numeric_lists)}.bin"
                with output.open("wb") as target:
                    reader.copy_exact(length * sizes[child_type], target)
                self.numeric_lists[path] = ExtractedNumericList(
                    output, length, child_type
                )
                return None
            values = [] if materialize else None
            for index in range(length):
                value = self._read_payload(
                    reader,
                    child_type,
                    (*path, str(index)),
                    materialize,
                    interested,
                    preserve_types,
                    depth + 1,
                )
                if values is not None:
                    values.append(value)
            return values
        if tag_type == TAG_COMPOUND:
            return self._read_compound(
                reader, path, materialize, preserve_types, depth + 1
            )
        raise NBTStreamError(f"未知 NBT 标签类型: {tag_type}")

    def _check_depth(self, depth: int) -> None:
        if depth > self.max_depth:
            raise NBTStreamError(f"NBT 嵌套深度超过限制: {self.max_depth}")

    @staticmethod
    def _u8(reader: _LimitedReader) -> int:
        return reader.read_exact(1)[0]

    def _length(self, reader: _LimitedReader) -> int:
        length = struct.unpack(self.byteorder + "i", reader.read_exact(4))[0]
        if length < 0:
            raise NBTStreamError(f"NBT 长度不能为负数: {length}")
        return length

    def _string(self, reader: _LimitedReader) -> str:
        length = struct.unpack(self.byteorder + "H", reader.read_exact(2))[0]
        try:
            return reader.read_exact(length).decode("utf-8")
        except UnicodeDecodeError as error:
            raise NBTStreamError(f"NBT 字符串不是有效 UTF-8: {error}") from error


def close_memmap(array: Any) -> None:
    """关闭 numpy.memmap 的底层 mmap；普通 ndarray 不做处理"""
    mmap = getattr(array, "_mmap", None)
    if mmap is not None:
        mmap.close()


def remove_directory(path: Path) -> None:
    """删除临时目录，供数据对象在关闭映射后调用"""
    shutil.rmtree(path)
