from tooldelta import fmts


def progress_bar(
    current: float,
    total: float,
    length: float = 20,
    color1: str = "§f",
    color2: str = "§b",
) -> str:
    """执行进度条

    Args:
        current (float | int): 当前进度值
        total (float | int): 总进度值
        length (int): 进度条长度.
        color1 (str): 进度条颜色 1.
        color2 (str): 进度条颜色 2.

    Returns:
        str: 格式化后的进度条字符串
    """
    pc = round(min(1, current / total) * length)
    return fmts.colormode_replace(
        color1 + " " * pc + color2 + " " * (20 - pc) + f"§r {current}/{total}", 7
    )
