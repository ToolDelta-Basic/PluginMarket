import tarfile
import zipfile
from datetime import datetime

now = datetime.now


def extract_executable_file(src: str, dst: str):
    if src.endswith(".zip"):
        file = zipfile.ZipFile(src)
        flist = file.filelist
        for i in flist:
            if "cqhttp" in i.filename:
                extract_file = i
                break
        else:
            raise ValueError("在压缩包中未找到go-cqhttp可执行文件")
        file.extract(extract_file, dst)
    elif src.endswith(".tar.gz"):
        file = tarfile.open(src, "r:gz")
        flist = file.getmembers()
        for i in flist:
            if "cqhttp" in i.name:
                extract_file = i
                break
        else:
            raise ValueError("在压缩包中未找到go-cqhttp可执行文件")
        file.extract(extract_file, dst)
    else:
        raise ValueError(f"不是合法tar或zip压缩包: {src}")


def output_remove_dtime(msg: str):
    # [2024-10-27 16:41:07] \x1b[0m\x1b[37m
    return msg.removeprefix(now().strftime("\x1b[0m\x1b[37m[%Y-%m-%d %H:%M:%S] "))
