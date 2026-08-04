"""BDX解析器"""

from __future__ import annotations

import shutil
import struct
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import brotli

MAX_DECOMPRESSED_BYTES = 1 << 30
MAX_STRING_BYTES = 1 << 20


@dataclass
class BDXData:
    author: str
    decompressed_path: Path
    temporary_directory: Path
    closed: bool = False

    def operations(self) -> Iterator[dict[str, Any]]:
        if self.closed:
            raise RuntimeError("BDXData 已关闭")
        with self.decompressed_path.open("rb") as stream:
            _read_header(stream)
            count = 0
            while True:
                opcode = _u8(stream)
                if opcode == 88:
                    return
                count += 1
                yield _read_operation(stream, opcode)

    def close(self) -> str | None:
        if self.closed:
            return None
        self.closed = True
        try:
            shutil.rmtree(self.temporary_directory)
        except OSError as error:
            return str(error)
        return None

    def __enter__(self) -> "BDXData":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def read_file(path: str) -> BDXData:
    temporary_directory = Path(tempfile.mkdtemp(prefix="tooldelta-bdx-"))
    output = temporary_directory / "content.bdxraw"
    try:
        with Path(path).open("rb") as source:
            if source.read(3) != b"BD@":
                raise ValueError("BDX 外层文件头不是 BD@")
            decoder = brotli.Decompressor()
            total = 0
            with output.open("wb") as target:
                while chunk := source.read(1 << 20):
                    try:
                        decompressed = decoder.process(chunk)
                    except brotli.error as error:
                        raise ValueError(f"BDX Brotli 数据损坏: {error}") from error
                    total += len(decompressed)
                    if total > MAX_DECOMPRESSED_BYTES:
                        raise ValueError(
                            f"BDX 解压数据超过限制: {total} > {MAX_DECOMPRESSED_BYTES}"
                        )
                    target.write(decompressed)
            if not decoder.is_finished():
                raise ValueError("BDX Brotli 数据被截断")
        with output.open("rb") as stream:
            author = _read_header(stream)
        return BDXData(author, output, temporary_directory)
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def _read_header(stream: BinaryIO) -> str:
    if _exact(stream, 4) != b"BDX\x00":
        raise ValueError("BDX 内层文件头不是 BDX\\0")
    return _string(stream)


def _read_operation(stream: BinaryIO, opcode: int) -> dict[str, Any]:
    if opcode == 1:
        return {"id": opcode, "value": _string(stream)}
    if opcode == 5:
        return {"id": opcode, "block": _uint16(stream), "states": _uint16(stream)}
    if opcode == 6:
        return {"id": opcode, "value": _uint16(stream)}
    if opcode in (20, 22, 24):
        return {"id": opcode, "value": _int16(stream)}
    if opcode == 7:
        return {"id": opcode, "block": _uint16(stream), "data": _uint16(stream)}
    if opcode in (8, 9, 14, 15, 16, 17, 18, 19, 41):
        if opcode == 41:
            raise ValueError("当前版本不支持含 NBT 负载的 BDX opcode 41")
        return {"id": opcode}
    if opcode == 12:
        return {"id": opcode, "value": _uint32(stream)}
    if opcode in (21, 23, 25):
        return {"id": opcode, "value": _int32(stream)}
    if opcode == 13:
        return {"id": opcode, "block": _uint16(stream), "states_text": _string(stream)}
    if opcode in (28, 29, 30):
        return {"id": opcode, "value": _int8(stream)}
    if opcode == 26:
        return {"id": opcode, **_command_data(stream)}
    if opcode == 27:
        return {
            "id": opcode,
            "block": _uint16(stream),
            "data": _uint16(stream),
            **_command_data(stream),
        }
    if opcode == 31:
        return {"id": opcode, "pool": _u8(stream)}
    if opcode in (32,):
        return {"id": opcode, "runtime_id": _uint16(stream)}
    if opcode in (33,):
        return {"id": opcode, "runtime_id": _uint32(stream)}
    if opcode == 34:
        return {"id": opcode, "runtime_id": _uint16(stream), **_command_data(stream)}
    if opcode == 35:
        return {"id": opcode, "runtime_id": _uint32(stream), **_command_data(stream)}
    if opcode == 36:
        return {"id": opcode, "data": _uint16(stream), **_command_data(stream)}
    if opcode in (37, 38):
        runtime_id = _uint16(stream) if opcode == 37 else _uint32(stream)
        slots = _chest_slots(stream)
        return {"id": opcode, "runtime_id": runtime_id, "slots": slots}
    if opcode == 39:
        size = _uint32(stream)
        _exact(stream, size)
        return {"id": opcode, "size": size}
    if opcode == 40:
        block, data = _uint16(stream), _uint16(stream)
        return {
            "id": opcode,
            "block": block,
            "data": data,
            "slots": _chest_slots(stream),
        }
    raise ValueError(f"未知 BDX opcode: {opcode}")


def _command_data(stream: BinaryIO) -> dict[str, Any]:
    return {
        "mode": _uint32(stream),
        "command": _string(stream),
        "custom_name": _string(stream),
        "last_output": _string(stream),
        "tick_delay": _uint32(stream),
        "execute_on_first_tick": bool(_u8(stream)),
        "track_output": bool(_u8(stream)),
        "conditional": bool(_u8(stream)),
        "needs_redstone": bool(_u8(stream)),
    }


def _chest_slots(stream: BinaryIO) -> int:
    count = _u8(stream)
    for _ in range(count):
        _string(stream)
        _exact(stream, 4)  # count byte, data uint16, slot byte
    return count


def _string(stream: BinaryIO) -> str:
    data = bytearray()
    while len(data) <= MAX_STRING_BYTES:
        value = _exact(stream, 1)[0]
        if value == 0:
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(f"BDX 字符串不是有效 UTF-8: {error}") from error
        data.append(value)
    raise ValueError(f"BDX 字符串超过限制: {MAX_STRING_BYTES} 字节")


def _exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("BDX 操作数据意外结束")
    return data


def _unpack(stream: BinaryIO, fmt: str) -> int:
    return int(struct.unpack(fmt, _exact(stream, struct.calcsize(fmt)))[0])


def _u8(stream: BinaryIO) -> int:
    return _exact(stream, 1)[0]


def _int8(stream: BinaryIO) -> int:
    return _unpack(stream, ">b")


def _uint16(stream: BinaryIO) -> int:
    return _unpack(stream, ">H")


def _int16(stream: BinaryIO) -> int:
    return _unpack(stream, ">h")


def _uint32(stream: BinaryIO) -> int:
    return _unpack(stream, ">I")


def _int32(stream: BinaryIO) -> int:
    return _unpack(stream, ">i")
