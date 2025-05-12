from __future__ import annotations
from typing import Union, Any, Callable, Final, Literal, Optional, TypeVar, final
import fastapi.logger
from flet_core.page import PageDisconnectedException
from tooldelta.utils.tooldelta_thread import ThreadExit
from asyncio.exceptions import CancelledError
from tooldelta import fmts, utils
from types import GenericAlias
from decimal import Decimal
import os
import flet as flet
import time
import rich
import rich.console
import rich.traceback
import string
import signal
import fastapi
import logging


fastapi.logger.logger.setLevel(logging.NOTSET)


class TDF:
    from 前置_TDF import entry as api

    def __init__(self, page: flet.Page) -> None:
        self.page = page
        if self.page.controls is None:
            raise Exception("初始化 TDF 对象异常: page.controls 为空.")

        self.page.fonts = {
            "MCASCII": "./asset/font/minecraft-seven.ttf", # 19.84, 19.88 *3
            "FiraCodeRegular": "./asset/font/FiraCode-Regular.ttf",
            "FiraCodeMedium": "./asset/font/FiraCode-Medium.ttf",
            "Consola": "./asset/font/consola.ttf",
            "MCGNU": "./asset/font/Minecraft GNU.ttf", # 15.9075
            "MCAE": "./asset/font/Minecraft AE.ttf"
        }
        self.page.title = "ToolDeltaFlet (TDF) - 租赁服远程管理网页."
        self.page.theme = flet.Theme(font_family = "MCGNU", color_scheme_seed = flet.colors.BLUE_100)
        self.page.dark_theme = flet.Theme(font_family = "MCGNU", color_scheme_seed = flet.colors.BLUE_900)
        self.page.theme_mode = flet.ThemeMode.SYSTEM
        # self.page.scroll = flet.ScrollMode.AUTO
        self.page.padding = 0
        self.page.vertical_alignment = flet.MainAxisAlignment.CENTER
        self.__init_controls__()
        self._testing_webcontrol_feature()
        self.page.update()


    def __init_controls__(self):
        self.column = flet.Column(alignment = flet.MainAxisAlignment.CENTER, spacing = 4)
        self.page.add(
            flet.Row(
                [
                    flet.IconButton(flet.icons.REMOVE),
                    self.column,
                    flet.IconButton(flet.icons.ADD),
                ],
                alignment = flet.MainAxisAlignment.CENTER,
            )
        )


    @utils.thread_func("首次实现网页与租赁服相连")
    def _testing_webcontrol_feature(self):
        while True:
            self.column.controls.clear()
            self.column.controls.append(
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    width = 200, spacing = 0,
                    controls = [
                        flet.Text("首次实现网页与租赁服相连\n其他功能敬请期待 qwq", size = 16, text_align = flet.TextAlign.CENTER)
                    ]
                )
            )
            self.column.controls.append(
                flet.Row(
                    alignment = flet.MainAxisAlignment.START,
                    width = 200, spacing = 0,
                    controls = [
                        flet.Text("在线玩家:", size = 16, text_align = flet.TextAlign.START)
                    ]
                )
            )
            for playername in self.api.game_ctrl.allplayers:
                self.column.controls.append(
                    flet.Row(
                        alignment = flet.MainAxisAlignment.CENTER,
                        width = 200, spacing = 0,
                        controls = [
                            flet.Text(playername, size = 16, text_align = flet.TextAlign.CENTER)
                        ]
                    )
                )
            self.page.update()
            time.sleep(5)


def main(page):
    TDF(page)


@utils.thread_func("Flet App")
def launch_flet():
    os.environ["FLET_SESSION_TIMEOUT"] = "60"
    os.environ["FLET_DISPLAY_URL_PREFIX"] = "网页已成功启动于"
    signal.signal = lambda *_, **__: None
    try:
        flet.app(target = main, port = 7912, assets_dir = ".", view = flet.AppView.WEB_BROWSER, web_renderer = flet.WebRenderer.CANVAS_KIT, use_color_emoji = True)
    except (ThreadExit, CancelledError):
        return
