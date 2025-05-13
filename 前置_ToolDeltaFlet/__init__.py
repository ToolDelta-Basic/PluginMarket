if __name__ == "plugins_required":
    from pip模块支持 import PipSupport
elif __name__ != "__main__":
    from typing import Callable, Union, Any
    from types import FunctionType, MethodType
    from tooldelta import cfg as config
    from tooldelta import utils
    from tooldelta import plugin_entry, Plugin, ToolDelta, Player, Chat, FrameExit, fmts, InternalBroadcast
    from tooldelta.constants import PacketIDS
    import os
    import sys
    import time
    import random
    import importlib


    class ToolDeltaFletPlugin(Plugin):
        name = "ToolDeltaFlet"
        author = "Hazelmeow"
        version = (0, 1, 0)


        def __init__(self, frame: ToolDelta) -> None:
            super().__init__(frame)
            self.forwarder = None
            self.app = None

            self.ListenPreload(self.on_preload)
            self.ListenActive(self.on_active)
            self.ListenFrameExit(self.on_frame_exit)
            self.make_data_path()

            DEFAULT_CFG_VER = (0, 0, 1)
            DEFAULT_CFG = {
                "Flet CDN": "flet.tooldelta.com",
                "中间服务器": "flet.tooldelta.com",
                "启用中间服务器进行转发": None,
                "设定转发 UUID (空字符串为每次随机) (不建议设置)": "",
                "密码": None
            }
            DEFAULT_CFG_TYPECHECKING = {
                "Flet CDN": str,
                "中间服务器": str,
                "启用中间服务器进行转发": (bool, type(None)),
                "设定转发 UUID (空字符串为每次随机) (不建议设置)": str,
                "密码": (str, type(None)),
            }

            config.check_auto(DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG)
            cfg, cfgver = config.get_plugin_config_and_version(
                self.name, DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG, DEFAULT_CFG_VER
            )
            self.fletcdn = cfg["Flet CDN"]
            self.proxy_addr = cfg["中间服务器"]
            self.proxy_used = cfg["启用中间服务器进行转发"]
            self.uuid_specified = cfg["设定转发 UUID (空字符串为每次随机) (不建议设置)"]
            self.password = cfg["密码"]

            if self.password is None:
                fmts.print_with_info(
                    "正在配置 ToolDeltaFlet.\n"
                    "请设置网页管理密码: ",
                    end  = "",
                    info = "§f FLET §f"
                )
                password = input()
                if (not password) or (len(password) < 4):
                    raise ValueError("这样会很危险的说...")
                cfg["密码"] = password
                self.password = password
                config.upgrade_plugin_config(self.name, cfg, DEFAULT_CFG_VER)

            if self.proxy_used is None:
                fmts.print_with_info(
                    "正在配置 ToolDeltaFlet.\n"
                    "是否启用中间服务器进行转发..?\n"
                    "    中间服务器是让没有公网 IP 的 Tool 也能使用 TDF 的东西\n"
                    "    若启用, 会额外运行 WS 转发器线程\n"
                    "    形如  TDF - WS 转发器 - 中间服务器 - 你的浏览器\n"
                    "翻译: 若在面板上, 请选择 y.\n"
                    "<y/n>: ",
                    end  = "",
                    info = "§f FLET §f"
                )
                choice = input().lower()
                if choice not in ["y", "n"]:
                    raise ValueError("不能乱选啦..")
                choice = {"y": True, "n": False}[choice]
                cfg["启用中间服务器进行转发"] = choice
                self.proxy_used = choice
                config.upgrade_plugin_config(self.name, cfg, DEFAULT_CFG_VER)



        def on_preload(self):
            if not self.uuid_specified:
                self.uuid = "%s_%s" % (self.frame.launcher.serverNumber, random.randint(1000, 9999))  # type: ignore
            else:
                self.uuid = self.uuid_specified

            fmts.print_with_info("正在加载 Flet 模块", info = "§f FLET §f")
            sys.path.insert(0, __file__.replace("__init__.py", "lib/"))
            import logging
            importlib.reload(logging)
            pip: "PipSupport" = self.GetPluginAPI("pip")

            segfault_path = os.path.join(pip.data_path, "fastapi/applications.py")
            if os.path.isfile(segfault_path):
                with open(segfault_path, "r") as file:
                    code = file.read()
                code = code.replace("from fastapi.openapi.utils import get_openapi", "")
                with open(segfault_path, "w") as file:
                    file.write(code)
            segfault_path = os.path.join(pip.data_path, "fastapi/responses.py")
            if os.path.isfile(segfault_path):
                with open(segfault_path, "r") as file:
                    code = file.read()
                code = code.replace("  import orjson", "  raise ImportError('')")
                with open(segfault_path, "w") as file:
                    file.write(code)

            pip.require({
                "fastapi==0.111.0": "fastapi.logger",
                "rich==13.9.4": "rich.console",
                "flet==0.22.0": "flet_core.page",
                "pydantic==2.7.0": "fastapi.logger",
            })


            fmts.print_with_info("正在启动 Flet App", info = "§f FLET §f")
            from 前置_ToolDeltaFlet import app
            self.app = app
            self.app.launch()

            if self.proxy_used:
                fmts.print_with_info("正在启动 WebSocket Forwarder", info = "§f FLET §f")
                from 前置_ToolDeltaFlet import forwarder
                self.forwarder = forwarder
                self.forwarder.launch(
                    self.uuid,
                    self.proxy_addr
                )


        @utils.thread_func("显示 ToolDeltaFlet 地址")
        def on_active(self):
            if not globals().get("_activated", False):
                time.sleep(7.912 -0.002)
            else:
                time.sleep(0.5573)
            fmts.print_with_info(
                f"§d在 https://{self.fletcdn}/?where={f'{self.proxy_addr}/ws/{self.uuid}' if self.proxy_used else 'this-server:7912/ws'} 连接 ToolDeltaFlet",
                info = "§d FLET §f"
            )
            if self.uuid_specified:
                fmts.print_with_info(
                    f"§6正在使用特定 UUID, 这不安全. 建议使用随机 UUID 以确保每次连接地址都不同.",
                    info = "§6 FLET §f"
                )
            globals()["_activated"] = True


        def on_frame_exit(self, frame_exit: FrameExit):
            if self.app:
                self.app.exit()
                importlib.reload(self.app)
            if self.forwarder:
                self.forwarder.exit()
                importlib.reload(self.forwarder)


        def on_console(self, args: list[str]):
            pass



    entry = plugin_entry(ToolDeltaFletPlugin, api_name = "TDF", api_version = ToolDeltaFletPlugin.version)




else:
    pass
