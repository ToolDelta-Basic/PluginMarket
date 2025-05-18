import json


def save_data(data_path, data):
    bat_path = data_path + ".bat"
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        with open(bat_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)

        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    except:
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        with open(bat_path, "w", encoding="utf-8") as f:
            json.dump(data, f)


def load_data(data_path):
    bat_path = data_path + ".bat"
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    except:
        try:
            with open(bat_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        except:
            data = {}

    return data
