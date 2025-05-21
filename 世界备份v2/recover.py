import json
import os
import subprocess
import requests
from tooldelta import Plugin
from tooldelta.utils import fmts, tempjson
from .recover_tool_name import get_tool_name
from .define import WorldBackupBase


class WorldBackupRecover:
    world_backup_base: WorldBackupBase

    def __init__(self, world_backup_base: WorldBackupBase) -> None:
        self.world_backup_base = world_backup_base

    def base(self) -> WorldBackupBase:
        return self.world_backup_base

    def plugin(self) -> Plugin:
        return self.base().plugin

    def download_and_run(self, cmd_config: dict) -> bool:
        tool_name = get_tool_name()
        if tool_name is None:
            fmts.print_err("世界备份第二世代: 恢复数据库为 MC 存档失败，因为操作系统不受支持")
            return False

        resp = requests.get(  # noqa: S113
            "https://api.github.com/repos/TriM-Organization/bedrock-chunk-diff/releases/latest"
        )
        if not resp.ok:
            fmts.print_err("世界备份第二世代: 从 GitHub 获取恢复工具失败")
            return False
        releases = json.loads(resp.content)

        tool_path = self.plugin().format_data_path(tool_name)
        for i in releases["assets"]:
            if i["name"] == tool_name:
                fmts.print_inf("世界备份第二世代: 开始下载存档恢复工具，请坐和放宽")

                file_binary = requests.get(  # noqa: S113
                    "https://github.tooldelta.top/" + i["browser_download_url"]
                )
                if not file_binary.ok:
                    fmts.print_err("世界备份第二世代: 恢复工具下载失败")
                    return False

                with open(tool_path, "wb") as file:
                    file.write(file_binary.content)
                os.chmod(tool_path, 0o755)  # noqa: PTH101, S103

                fmts.print_suc("世界备份第二世代: 恢复工具下载成功")
                break

        args: list[str] = [tool_path]
        for key, value in cmd_config.items():
            args.append(f"-{key}={value}")
        process = subprocess.Popen(args)  # noqa: S603
        process.wait()

        os.remove(tool_path)  # noqa: PTH107
        return True

    def recover(self) -> tuple[str, bool, str, str]:
        should_do_recover = False
        config_path = self.plugin().format_data_path("cmd_config.json")

        try:
            cmd_config = tempjson.load_and_read(config_path)
            if len(cmd_config) == 0:
                return "", False, "", ""
            should_do_recover = True
        except Exception:  # noqa: BLE001, S110
            pass

        if not should_do_recover:
            return "", False, "", ""

        if self.download_and_run(cmd_config):
            tempjson.load_and_write(config_path, {})
            tempjson.flush(config_path)
            return (
                cmd_config["output"],
                cmd_config["use-range"],
                f"({cmd_config['range-start-x']},{cmd_config['range-start-z']})",
                f"({cmd_config['range-end-x']},{cmd_config['range-end-z']})",
            )

        return "", False, "", ""
