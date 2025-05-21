# pylint: disable=invalid-name                   (C0103)
# pylint: disable=missing-module-docstring       (C0114)
# pylint: disable=missing-class-docstring        (C0115)
# pylint: disable=missing-function-docstring     (C0116)
# pylint: disable=consider-using-f-string        (C0209)
# pylint: disable=multiple-statements            (C0321)
# pylint: disable=import-outside-toplevel        (C0415)
# pylint: disable=attribute-defined-outside-init (W0201)
# pylint: disable=bad-staticmethod-argument      (W0211)
# pylint: disable=protected-access               (W0212)
# pylint: disable=abstract-method                (W0223)
# pylint: disable=unused-import                  (W0611)
# pylint: disable=unused-argument                (W0613)
# pylint: disable=non-ascii-file-name            (W2402)
# pylint: disable=redefined-argument-from-local  (R1704)

# ruff: noqa: D100    - Missing docstring in public module
# ruff: noqa: D101    - Missing class docstring
# ruff: noqa: D102    - Missing docstring in public method
# ruff: noqa: D103    - Missing docstring in public function
# ruff: noqa: D104    - Missing docstring in public package
# ruff: noqa: D105    - Missing docstring in magic method
# ruff: noqa: D107    - Missing docstring in __init__
# ruff: noqa: D212    - Multi-line docstring summary should start at the first line
# ruff: noqa: D400    - First line should end with a period
# ruff: noqa: D415    - First line should end with a period, question mark, or exclamation point
# ruff: noqa: E701    - Multiple statements on one line (colon)
# ruff: noqa: F401    - `module` imported but unused
# ruff: noqa: I001    - Import block is un-sorted or un-formatted
# ruff: noqa: N802    - Function name `myFunc` should be lowercase
# ruff: noqa: N803    - Argument name `param` should be lowercase
# ruff: noqa: N806    - Variable `var` in function should be lowercase
# ruff: noqa: N818    - Exception name `MyException` should be named with an Error suffix
# ruff: noqa: N999    - Invalid module name
# ruff: noqa: Q000    - Single quotes found but double quotes preferred
# ruff: noqa: S101    - Use of `assert` detected
# ruff: noqa: S311    - Standard pseudorandom generators are not suitable for cryptographic purposes
# ruff: noqa: T201    - `print` found
# ruff: noqa: EM101   - Exception must not use a string literal, assign to variable first
# ruff: noqa: EM102   - Exception must not use an f-string literal, assign to variable first
# ruff: noqa: TC002   - Move third-party import into a type-checking block
# ruff: noqa: TC003   - Move standard library import into a type-checking block
# ruff: noqa: TD003   - Missing issue link for this TODO
# ruff: noqa: UP007   - Use `X | Y` for type annotations
# ruff: noqa: UP031   - Use format specifiers instead of percent format
# ruff: noqa: UP035   - Import from `collections.abc` instead: `Callable`
# ruff: noqa: UP037   - Remove quotes from type annotation
# ruff: noqa: ANN401  - Dynamically typed expressions (typing.Any) are disallowed in `param`
# ruff: noqa: ARG001  - Unused function argument
# ruff: noqa: ARG002  - Unused method argument: `var`
# ruff: noqa: ARG005  - Unused lambda argument: `param`
# ruff: noqa: COM812  - Trailing comma missing
# ruff: noqa: ERA001  - Found commented-out code
# ruff: noqa: FBT001  - Boolean-typed positional argument in function definition
# ruff: noqa: FBT002  - Boolean default positional argument in function definition
# ruff: noqa: ISC002  - Implicitly concatenated string literals over multiple lines
# ruff: noqa: PTH113  - `os.path.isfile()` should be replaced by `Path.is_file()`
# ruff: noqa: PTH123  - `open()` should be replaced by `Path.open()`
# ruff: noqa: PLR0913 - Too many arguments in function definition
# ruff: noqa: PLR1704 - Redefining argument with the local name `param`
# ruff: noqa: PLW0211 - First argument of a static method should not be named `self`
# ruff: noqa: RUF001  - Checks for ambiguous Unicode characters in strings.
# ruff: noqa: RUF002  - Checks for ambiguous Unicode characters in docstrings.
# ruff: noqa: SLF001  - Private member accessed: `_attr`
# ruff: noqa: SIM108  - Use ternary operator `x = y if cond else z` instead of `if`-`else`-block
# ruff: noqa: TRY003  - Avoid specifying long messages outside the exception class
# ruff: noqa: TRY300  - Checks for return statements in try blocks. Move to an `else` blockRuff

if __name__ == "plugins_required":
    from pip模块支持 import PipSupport
elif __name__ != "__main__":
    from typing import Callable, Union, Any
    from types import FunctionType, MethodType
    from tooldelta import cfg as config
    from tooldelta import utils
    from tooldelta import (
        plugin_entry, Plugin, ToolDelta, Player, Chat, FrameExit,
        fmts, InternalBroadcast
    )
    try:
        from tooldelta.internal.launch_cli import FrameEulogistLauncher
    except ImportError:
        FrameEulogistLauncher = type(None)
    from tooldelta.constants import PacketIDS
    import os
    import sys
    import time
    import random
    import importlib


    class ToolDeltaFletPlugin(Plugin):
        name = "ToolDeltaFlet"
        author = "Hazelmeow"
        version = (0, 0, 4)


        def __init__(self, frame: ToolDelta) -> None:
            super().__init__(frame)
            self.forwarder = None
            self.app = None

            self.ListenPreload(self.on_preload)
            self.ListenActive(self.on_active)
            self.ListenFrameExit(self.on_frame_exit)
            self.make_data_path()

            DEFAULT_CFG_VER = self.version
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
            cfg, _ = config.get_plugin_config_and_version(
                self.name, DEFAULT_CFG_TYPECHECKING, DEFAULT_CFG, DEFAULT_CFG_VER
            ) # _ is cfgver
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
                if (not password) or (len(password) < 4):  # noqa: PLR2004
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



        def on_preload(self) -> None:
            if not self.uuid_specified:
                assert not isinstance(self.frame.launcher, FrameEulogistLauncher)
                self.uuid = "%s_%s" % (
                    self.frame.launcher.serverNumber, random.randint(1000, 9999)
                )
            else:
                self.uuid = self.uuid_specified

            fmts.print_with_info("正在加载 Flet 模块", info = "§f FLET §f")
            sys.path.insert(0, __file__.replace("__init__.py", "lib/"))
            import logging
            importlib.reload(logging)
            pip: "PipSupport" = self.GetPluginAPI("pip")


            segfault_path = pip.data_path.joinpath("fastapi/applications.py")
            if os.path.isfile(segfault_path):
                with open(segfault_path, encoding = "utf-8") as file:
                    code = file.read()
                code = code.replace("from fastapi.openapi.utils import get_openapi", "")
                with open(segfault_path, "w", encoding = "utf-8") as file:
                    file.write(code)
            segfault_path = pip.data_path.joinpath("fastapi/responses.py")
            if os.path.isfile(segfault_path):
                with open(segfault_path, encoding = "utf-8") as file:
                    code = file.read()
                code = code.replace("  import orjson", "  raise ImportError('')")
                with open(segfault_path, "w", encoding = "utf-8") as file:
                    file.write(code)

            pip.require({
                "fastapi==0.111.0": "fastapi.logger",
                "rich==13.9.4": "rich.console",
                "flet==0.22.0": "flet_core.page",
                "pydantic==2.7.0": "fastapi.logger",
            })


            self.port = globals().get("_tdf_port", 7912)
            globals()["_tdf_port"] = self.port +1

            fmts.print_with_info(
                f"正在启动 Flet App (localhost:{self.port})", info = "§f FLET §f"
            )
            from 前置_ToolDeltaFlet import app
            self.app = app
            self.app.launch(self.port)

            if self.proxy_used:
                fmts.print_with_info(
                    "正在启动 WebSocket Forwarder", info = "§f FLET §f"
                )
                from 前置_ToolDeltaFlet import forwarder
                self.forwarder = forwarder
                self.forwarder.launch(
                    self.uuid,
                    self.proxy_addr,
                    self.port
                )


        @utils.thread_func("显示 ToolDeltaFlet 地址")
        def on_active(self) -> None:
            if not globals().get("_activated", False):
                time.sleep(7.912 -0.002)
            else:
                time.sleep(0.5573)
            fmts.print_with_info(
                f"§d在 https://{self.fletcdn}/?where=" \
                        +(f'{self.proxy_addr}/ws/{self.uuid}' if self.proxy_used \
                    else 'this-server:7912/ws') \
                +" 连接 ToolDeltaFlet", info = "§d FLET §f"
            )
            # Wait for Super upgrade Python to 3.12
            # fmts.print_with_info(
            #     f"§d在 https://{self.fletcdn}/?where={ \
            #             f'{self.proxy_addr}/ws/{self.uuid}' if self.proxy_used \
            #         else 'this-server:7912/ws' \
            #     } 连接 ToolDeltaFlet", info = "§d FLET §f"
            # )
            if self.uuid_specified:
                fmts.print_with_info(
                    "§6正在使用特定 UUID, 这不安全. "
                    "建议使用随机 UUID 以确保每次连接地址都不同.",
                    info = "§6 FLET §f"
                )
            globals()["_activated"] = True


        def on_frame_exit(self, frame_exit: FrameExit) -> None:
            if self.app:
                self.app.close()
                importlib.reload(self.app)
            if self.forwarder:
                self.forwarder.close()
                importlib.reload(self.forwarder)


        def on_console(self, args: list[str]) -> None:
            pass



    entry = plugin_entry(
        ToolDeltaFletPlugin,
        api_name = "TDF", api_version = ToolDeltaFletPlugin.version
    )




else:
    pass
