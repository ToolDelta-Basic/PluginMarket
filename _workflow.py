import os
import json

def generate_json(directory):
    data = {}

    # 确保目标目录存在
    target_directory = directory
    if not os.path.exists(target_directory) or not os.path.isdir(target_directory):
        print("目录不存在或不是一个目录")
        return data

    # 获取目录下所有文件
    for root, _, files in os.walk(target_directory):
        relative_path = os.path.relpath(root, target_directory)
        if relative_path == ".":
            relative_path = ""
        data[relative_path] = []

        # 添加文件
        for file in files:
            data[relative_path].append(file)

    return data

def get_latest_versions(directory):
    v_dict = {"classic_plugin": {}, "injected_plugin": {}}
    for p1 in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, p1, "datas.json")):
            with open(
                os.path.join(p1, "datas.json"),
                "r",
                encoding="utf-8",
            ) as f:
                dat = json.load(f)
                v_dict[dat["plugin-type"] + "_plugin"][p1] = dat["version"]
    return json.dumps(v_dict, indent=2, ensure_ascii=False)

def flush_basic_datas():
    with open("market_tree.json", "r", encoding="utf-8") as f:
        market_d = json.load(f)
    for path in os.listdir():
        datpath = os.path.join(path, "datas.json")
        if os.path.isfile(datpath):
            with open(datpath, "r", encoding="utf-8") as f:
                dat = json.load(f)
                market_d["MarketPlugins"][path] = {
                    "author": dat["author"],
                    "version": dat["version"],
                    "plugin-type": dat["plugin-type"]
                }

    with open("market_tree.json", "w", encoding="utf-8") as f:
        json.dump(market_d, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    directory = "."  # 你的仓库目录

    json_data = generate_json(directory)

    # 将生成的 JSON 数据写入文件
    with open("directory.json", "w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)

    with open("latest_versions.json", "w", encoding="utf-8") as f:
        f.write(get_latest_versions(directory))

    flush_basic_datas()