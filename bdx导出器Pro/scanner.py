from concurrent.futures import ThreadPoolExecutor
from tooldelta import fmts
from . import lib, bdx_utils

if 0:
    from . import BDXExporter

"""


export set 159 64 0
export setend 0 138 143
export bd.bdx



export set 74 -60 -117
export setend 426 115 72
export bd.bdx

"""


def get_and_load_structure(
    sys: "BDXExporter",
    x: int,
    y: int,
    z: int,
    sizex: int,
    sizey: int,
    sizez: int,
    relative_x: int,
    absolute_y: int,
    relative_z: int,
    progress_now: int,
    progress_max: int,
    tp: bool = True
):
    if tp:
        sys.game_ctrl.sendwscmd(f"tp {x} 0 {z}")
    progress_bar = bdx_utils.progress_bar(progress_now, progress_max)
    progress_text = (
        f"{progress_bar} 区块 [{x}, {y}, {z}] ~ [{x + sizex}, {y + sizey}, {z + sizez}]"
    )
    fmts.print_inf(
        f"正在获取 {progress_text}         ",
        end="\r",
    )
    get_structure_retries = 0
    while get_structure_retries < 10:
        try:
            r = sys.intr._request_structure_and_get((x, y, z), (sizex, sizey, sizez))
            break
        except ValueError as err:
            if tp:
                sys.game_ctrl.sendwocmd(f"tp @a[tag=robot] {x} 0 {z}")
            get_structure_retries += 1
            if get_structure_retries > 10:
                fmts.print_err("获取结构失败, 最大重试次数已超过")
                raise
            else:
                fmts.print_war(f"{err}: 重试第 {get_structure_retries} 次")
    fmts.print_inf(
        f"正在解析 {progress_text}         ",
        end="\r",
    )
    lib.LoadStructure(r, relative_x, absolute_y, relative_z)
    fmts.print_inf(
        f"解析完成 {progress_text}         ",
        end="\r",
    )


def export_to_structures(
    sys: "BDXExporter",
    startx: int,
    starty: int,
    startz: int,
    endx: int,
    endy: int,
    endz: int,
):
    startx, endx = min(startx, endx), max(startx, endx)
    starty, endy = min(starty, endy), max(starty, endy)
    startz, endz = min(startz, endz), max(startz, endz)
    dy = endy - starty + 1
    chunks_count = bdx_utils.get_chunks_num(startx, startz, endx, endz)
    steps = 0
    for x, z, rel_x, rel_z in bdx_utils.yield_chunks(startx, startz, endx, endz):
        sizex, sizez = min(16, endx - x + 1), min(16, endz - z + 1)
        get_and_load_structure(
            sys,
            x,
            starty,
            z,
            sizex,
            dy,
            sizez,
            rel_x,
            starty,
            rel_z,
            steps,
            chunks_count,
        )
        steps += 1
