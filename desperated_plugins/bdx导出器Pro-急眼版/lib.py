import os
import ctypes
import msgpack
from tooldelta import fmts

lib_file = os.path.join(os.path.dirname(__file__), "libbdxexporter.so")

try:
    LIB = ctypes.cdll.LoadLibrary(lib_file)
except Exception as e:
    fmts.print_err(f"BDX 导出库加载失败: {e}")
    raise e


class LockGetterAndReleaser:
    def __enter__(self):
        return AcquireLock()

    def __exit__(self, exc_type, exc_val, exc_tb):
        ReleaseLock()


def pyString(s: bytes):
    return s.decode()


def cgoString(s: str):
    return s.encode()


def assert_return(msg: bytes):
    if msg:
        raise RuntimeError(pyString(msg))


def AcquireLock() -> bool:
    return LIB.AcquireLock()


def ReleaseLock():
    LIB.ReleaseLock()


def LoadStructure(structure, relative_x: int, absolute_y: int, relative_z: int):
    bts: bytes = msgpack.packb(structure)  # type: ignore
    bts_len = len(bts)

    # bts_disp = "[" + ",".join(map(str, bts[:50])) + "]"

    # print(f"bts len={len(bts)}, first={bts_disp}")
    assert_return(LIB.LoadStructure(bts, bts_len, relative_x, absolute_y, relative_z))


def StructuresToBDX():
    assert_return(LIB.StructuresToBDX())


def DumpBDX(filepath: str):
    assert_return(LIB.DumpBDX(cgoString(filepath)))


LIB.AcquireLock.argtypes = ()
LIB.ReleaseLock.argtypes = ()
LIB.LoadStructure.argtypes = (
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_int32,
    ctypes.c_int32,
    ctypes.c_int32,
)
LIB.LoadStructure.restype = ctypes.c_char_p
LIB.StructuresToBDX.argtypes = ()
LIB.StructuresToBDX.restype = ctypes.c_char_p
LIB.DumpBDX.argtypes = (ctypes.c_char_p,)
LIB.DumpBDX.restype = ctypes.c_char_p
