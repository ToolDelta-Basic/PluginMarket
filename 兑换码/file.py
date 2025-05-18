def read(name=None):
    try:
        if not name:
            return
        else:
            with open(name,'r',encoding='utf-8') as f:
                data = f.read()
            return data
    except FileNotFoundError:
        print("文件不存在")
        return


def write(name=None, data=None):
    try:
        if not name:
            return
        else:
            with open(name, "r+",encoding='utf-8') as f:
                f.write(data)
            return
    except FileNotFoundError:
        print("文件不存在")
        return
