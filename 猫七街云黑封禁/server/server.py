from flask import Flask, jsonify, request
import os, json
from urllib.parse import unquote
from datetime import datetime

app = Flask(__name__)

HOST = "0.0.0.0"
PORT = 2000

def get_all_subfolders(start_path):
    subfolders = []
    for entry in os.listdir(start_path):
        full_path = os.path.join(start_path, entry)
        if os.path.isdir(full_path) and not entry.startswith('.'):
            subfolders.append(entry)
    return sorted(subfolders)

@app.route("/<path:main_end>/get_blacklist")
def get_blacklist(main_end):
    try:
        decoded_dir = unquote(main_end)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if any(c in decoded_dir for c in ["..", "\0", "/", "\\"]):
            return jsonify({"error": "非法路径参数"}), 400
        target_dir = os.path.normpath(os.path.join(base_dir, decoded_dir))
        base_real = os.path.realpath(base_dir)
        target_real = os.path.realpath(target_dir)
        if not target_real.startswith(base_real):
            return jsonify({"error": "路径越界访问"}), 403
        if not os.path.exists(target_real):
            return jsonify({"error": "指定路径不存在"}), 404
        if not os.path.isdir(target_real):
            return jsonify({"error": "指定路径不是目录"}), 400
        blacklist_file = os.path.join(target_real, "blacklist.json")
        with open(blacklist_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "黑名单文件不存在"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "黑名单文件格式错误"}), 500
    except Exception as e:
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500

@app.route("/get_list")
def get_list():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return jsonify({
        "subfolders": get_all_subfolders(current_dir),
        "status": "success"
    })

@app.route("/create_new/<server_number>", methods=["POST"])
def create_new_blacklist(server_number):
    try:
        if not server_number.isdigit():
            return jsonify({
                "status": "error",
                "message": "服务器号必须为纯数字"
            }), 400
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.normpath(os.path.join(base_dir, server_number))
        if not target_dir.startswith(base_dir):
            return jsonify({
                "status": "error",
                "message": "非法路径"
            }), 403
        data = request.get_json()
        if not data or "password" not in data or "blacklist" not in data:
            return jsonify({
                "status": "error",
                "message": "请求数据格式错误"
            }), 400
        password = data["password"]
        if len(password) < 16:
            return jsonify({
                "status": "error",
                "message": "密码长度必须至少16位"
            }), 400
        if os.path.exists(target_dir):
            return jsonify({
                "status": "error",
                "message": "该服务器号已存在"
            }), 409
        os.makedirs(target_dir, exist_ok=False)
        with open(os.path.join(target_dir, "blacklist.json"), "w", encoding="utf-8") as f:
            json.dump(data["blacklist"], f, indent=2, ensure_ascii=False)
        with open(os.path.join(target_dir, "密码.txt"), "w", encoding="utf-8") as f:
            f.write(f"管理员密码：{password}\n")
            f.write(f"创建时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        return jsonify({
            "status": "success",
            "message": f"云黑服务器 {server_number} 创建成功"
        })
    except FileExistsError:
        return jsonify({
            "status": "error",
            "message": "目录已存在"
        }), 409
    except OSError as e:
        return jsonify({
            "status": "error",
            "message": f"目录操作失败: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"服务器内部错误: {str(e)}"
        }), 500

@app.route("/remove/<server_number>", methods=["POST"])
def remove_blacklist_server(server_number):
    try:
        if not server_number.isdigit():
            return jsonify({
                "status": "error",
                "message": "服务器号必须为纯数字"
            }), 400
        data = request.get_json()
        if not data or "password" not in data:
            return jsonify({
                "status": "error",
                "message": "请求数据格式错误"
            }), 400
        password = data["password"]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.normpath(os.path.join(base_dir, server_number))
        if not target_dir.startswith(base_dir):
            return jsonify({
                "status": "error",
                "message": "非法路径"
            }), 403
        if not os.path.exists(target_dir):
            return jsonify({
                "status": "error",
                "message": "服务器号不存在"
            }), 404
        password_file = os.path.join(target_dir, "密码.txt")
        if not os.path.exists(password_file):
            return jsonify({
                "status": "error",
                "message": "密码文件不存在"
            }), 403
        with open(password_file, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            lines = content.split("\n")
            stored_password = None
            for line in lines:
                if "管理员密码：" in line:
                    stored_password = line.split("：")[1].strip()
                    break
            if stored_password is None:
                return jsonify({
                    "status": "error",
                    "message": "密码文件格式错误"
                }), 500
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"解析密码文件失败: {str(e)}"
            }), 500
        if password != stored_password:
            return jsonify({
                "status": "error",
                "message": "密码错误"
            }), 403
        import shutil
        try:
            shutil.rmtree(target_dir)
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"删除目录失败: {str(e)}"
            }), 500
        return jsonify({
            "status": "success",
            "message": f"黑名单服务器 {server_number} 删除成功"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"服务器内部错误: {str(e)}"
        }), 500

@app.route("/verify_password/<server_number>", methods=["POST"])
def verify_password(server_number):
    try:
        if not server_number.isdigit():
            return jsonify({
                "status": "error",
                "message": "服务器号必须为纯数字"
            }), 400
        data = request.get_json()
        if not data or "password" not in data:
            return jsonify({
                "status": "error",
                "message": "请求数据格式错误"
            }), 400
        password = data["password"]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.normpath(os.path.join(base_dir, server_number))
        if not target_dir.startswith(base_dir):
            return jsonify({
                "status": "error",
                "message": "非法路径"
            }), 403
        if not os.path.exists(target_dir):
            return jsonify({
                "status": "error",
                "message": "服务器号不存在"
            }), 404
        password_file = os.path.join(target_dir, "密码.txt")
        if not os.path.exists(password_file):
            return jsonify({
                "status": "error",
                "message": "密码文件不存在"
            }), 403
        with open(password_file, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            lines = content.split("\n")
            stored_password = None
            for line in lines:
                if "管理员密码：" in line:
                    stored_password = line.split("：")[1].strip()
                    break
            if stored_password is None:
                return jsonify({
                    "status": "error",
                    "message": "密码文件格式错误"
                }), 500
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"解析密码文件失败: {str(e)}"
            }), 500
        if password != stored_password:
            return jsonify({
                "status": "error",
                "message": "密码错误"
            }), 403
        return jsonify({
            "status": "success",
            "message": "密码验证成功"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"服务器内部错误: {str(e)}"
        }), 500

@app.route("/upload_blacklist/<server_number>", methods=["POST"])
def upload_blacklist(server_number):
    try:
        if not server_number.isdigit():
            return jsonify({
                "status": "error",
                "message": "服务器号必须为纯数字"
            }), 400
        data = request.get_json()
        if not data or "blacklist" not in data:
            return jsonify({
                "status": "error",
                "message": "请求数据格式错误"
            }), 400
        blacklist_data = data["blacklist"]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.normpath(os.path.join(base_dir, server_number))
        if not target_dir.startswith(base_dir):
            return jsonify({
                "status": "error",
                "message": "非法路径"
            }), 403
        if not os.path.exists(target_dir):
            return jsonify({
                "status": "error",
                "message": "服务器号不存在"
            }), 404
        with open(os.path.join(target_dir, "blacklist.json"), "w", encoding="utf-8") as f:
            json.dump(blacklist_data, f, indent=2, ensure_ascii=False)
        return jsonify({
            "status": "success",
            "message": "云黑列表上传成功"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"服务器内部错误: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)