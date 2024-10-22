import tarfile
import zipfile


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
        file = tarfile.TarFile(src)
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
