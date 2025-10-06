import getpass
from tooldelta import fmts, utils
from .cfg_formatter import config, F_QQ_NUMBER, F_QQ_PASSWORD, F_WS_ADDRESS

if 0:
    from . import QQLinkerLauncher


def get_config(qq_number: int, qq_password: str, ws_address: str):
    return config.format(**{F_QQ_NUMBER: qq_number, F_QQ_PASSWORD: qq_password, F_WS_ADDRESS: ws_address})


def make_config(qq_number: int, qq_password: str):
    return {"QQ号": qq_number, "密码": qq_password}


class ConfigMgr:
    def __init__(self, sys: "QQLinkerLauncher"):
        self.sys = sys
        self.account_file_path = self.sys.data_path / "账户配置.json"
        self.yaml_config_path = self.sys.data_path / "config.yml"

    def get_account_data(self):
        file_path = self.account_file_path
        ask = False
        if not file_path.is_file():
            ask = True
        try:
            ft = utils.safe_json_load(open(file_path, encoding="utf-8"))
            utils.cfg.check_auto({"QQ号": int, "密码": str}, ft)
        except Exception as err:
            fmts.print_err(f"读取账户配置错误: {err}")
            ask = True
        if ask:
            while True:
                qqnumber = utils.try_int(input(fmts.fmt_info("请输入QQ号: ")))
                if qqnumber is None:
                    fmts.print_err("输入错误")
                else:
                    break
            fmts.print_inf("QQ密码 如果不输入, 每次启动都将会使用扫码登录")
            qqpasswd = getpass.getpass(fmts.fmt_info("请输入QQ密码(不会回显): "))
            cfg = make_config(qqnumber, qqpasswd)
            utils.safe_json_dump(cfg, file_path, indent=4)
        else:
            cfg = ft
        qqnumber = cfg["QQ号"]
        qqpasswd = cfg["密码"]
        return qqnumber, qqpasswd

    def flush_config_yaml(self, openat_port: int = 3005):
        qqnumber, qqpasswd = self.get_account_data()
        with self.yaml_config_path.open("w", encoding="utf-8") as f:
            f.write(get_config(qqnumber, qqpasswd, f"127.0.0.1:{openat_port}"))
