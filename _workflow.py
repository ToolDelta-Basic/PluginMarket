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
    v_dict = {"dotcs_plugin": {}, "classic_plugin": {}, "injected_plugin": {}}
    with open(
        os.path.join(directory, "market_tree.json"),
        "r",
        encoding="utf-8",
    ) as f:
        for k, v in json.load(f)["MarketPlugins"].items():
            v_dict[v["plugin-type"] + "_plugin"][k] = v["version"]
    return json.dumps(v_dict, indent=2, ensure_ascii=False)

def update_plugin_data():
    with open(
        os.path.join(directory, "market_tree.json"), "r", encoding="utf-8"
    ) as f0:
        mk_dats = json.load(f0)
    for fdir in os.listdir():
        if os.path.isdir(fdir) and os.path.isfile(os.path.join(fdir, "data.json")):
            with open(os.path.join(fdir, "data.json"), "r", encoding="utf-8") as f:
                datas = json.load(f)
                mk_dats[fdir] = {
                    "author": datas["author"],
                    "version": datas["version"],
                    "description": datas["description"],
                    "plugin-type": datas["plugin-type"],
                    "pre-plugins": datas["pre-plugins"],
                    "limit_launcher": datas.get("limit_launcher")
                }
    with open(
        os.path.join(directory, "market_tree.json"), "w", encoding="utf-8"
    ) as f0:
        json.dump(mk_dats, f0)


if __name__ == "__main__":
    directory = "."  # 你的仓库目录
    json_data = generate_json(directory)

    # 将生成的 JSON 数据写入文件
    with open("directory.json", "w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)

    with open("latest_versions.json", "w", encoding="utf-8") as f:
        f.write(get_latest_versions(directory))
