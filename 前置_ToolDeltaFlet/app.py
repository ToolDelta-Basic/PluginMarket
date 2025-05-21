from __future__ import annotations
from typing import (
    Union, Any, Callable, Final, Literal, Optional, TypeVar, final,
    ParamSpec, Self, Concatenate, NoReturn
)
from asyncio.exceptions import CancelledError
from types import GenericAlias
from decimal import Decimal
import re
import os
import time
import string
import signal
import logging
import datetime
import traceback
import threading

from flet_core.page import PageDisconnectedException
from flet_core.event import Event
import flet
import flet.fastapi.flet_app
import flet.fastapi.flet_app_manager
import rich
import rich.console
import rich.traceback
import fastapi
import fastapi.logger

from tooldelta.utils.tooldelta_thread import ThreadExit, ToolDeltaThread
from tooldelta import fmts, utils


ONE_PERCENT = Decimal("0.01")
PAGE_CHAR_WIDTH_SHOW_RICH_EXC = 79.12
LEGAL_ASCII_CHARACTER = string.printable.strip(string.whitespace)
WINDOW_WIDTH_PIXEL_MIN = 320
WINDOW_WIDTH_PIXEL_MAX = 2000
WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN = 650
WINDOW_WIDTH_PIXEL_SHOW_EXTENTIONS_MIN = 770
WINDOW_HEIGHT_PIXEL_MIN = 320
app_list: list[ToolDeltaFletApp] = []
theme_color_list = [
    [flet.colors.RED_500, flet.colors.RED_900],
    [flet.colors.ORANGE_500, flet.colors.ORANGE_900],
    [flet.colors.GREEN_100, flet.colors.GREEN_900],
    [flet.colors.BLUE_100, flet.colors.BLUE_900],
    [flet.colors.INDIGO_100, flet.colors.INDIGO_900],
    [flet.colors.DEEP_PURPLE_100, flet.colors.DEEP_PURPLE_900],
    [flet.colors.PURPLE_100, flet.colors.PURPLE],
]
freq_config = {
    "switch_theme": {"interval": 0.25, "count": 1},
    "login": {"interval": 300, "count": 3}
}
console = rich.console.Console()
exception_lock = threading.RLock()


PT = ParamSpec("PT")
RT = TypeVar("RT")
SelfType = TypeVar("SelfType")
def on_exception(
    func_on_exc: Callable,
    exec_after_finish: Optional[list] = None,
    exec_after_exception: Optional[list] = None
) \
        -> Callable[
            [Callable[Concatenate[SelfType, PT], RT]],
             Callable[
                 Concatenate[SelfType, PT],
                 Union[tuple[None, BaseException], tuple[RT, None]]
             ]
           ]:
    """
    在函数出现异常时, 指定某函数进行处理.

    由于此装饰器不会重新 raise, 所以请使用 go 式写法.

    >>> @on_exception(...)
    ... def func1(...)
    ...    raise Exception
    ...
    ... @on_exception(...)
    ... def func2(...)
    ...     do_sth()
    ...     ret, exc = func1()
    ...     if exc:
    ...         return
    ...     do_sth()
    ...
    ... func2()

    Args:
        func_on_exc (Callable): _description_
        exec_after_finish (list, optional): _description_. Defaults to [].
        exec_after_exception (list, optional): _description_. Defaults to [].

    """
    if exec_after_finish is None:
        exec_after_finish = []
    if exec_after_exception is None:
        exec_after_exception = []
    def wrapper(func: Callable[Concatenate[SelfType, PT], RT]) \
            -> Callable[
                   Concatenate[SelfType, PT],
                   Union[tuple[None, BaseException], tuple[RT, None]]
               ]:

        def executor(self: SelfType, *args: Any, **kwargs: Any) \
            -> Union[tuple[None, BaseException], tuple[RT, None]] \
        :
            ret = None
            exception = None
            try:
                ret = func(self, *args, **kwargs)

            # Flet 断言失败.
            except AssertionError as exc:
                exception = exc
                exc_type = type(exc)
                exc_text = f"{exc_type.__name__}: {exc}"
                exc_text = f"Flet 框架断言失败.\n" \
                           f"若页面响应不正常, 可重启浏览器.\n{exc_text}"
                fmts.print_err(exc_text)
                func_on_exc(self, exc_text)
                for code in exec_after_exception:
                    exec(code)

            # ToolDelta 终止线程.
            except ThreadExit:
                fmts.print_war("线程被强制终止")
                raise

            # 正常异常.
            except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                exception = exc
                exc_type = type(exc)
                exc_text = f"{exc_type.__name__}: {exc}"
                exc_text_default = traceback.format_exc()
                fmts.print_err(exc_text_default)

                # 控制台输出美观的回溯.
                console_width = console.width -2
                exc_rich = rich.traceback.Traceback.from_exception(
                    exc_type, exc, exc.__traceback__, width = console_width,
                    show_locals = True, word_wrap = True
                )
                with exception_lock:
                    with console.capture() as capture:
                        console.print(exc_rich)
                    exc_text_rich = capture.get()
                    print(exc_text_rich)
                del exc_rich, console_width, capture, exc_text_rich

                # 网页显示美观的回溯.
                if isinstance(self, ToolDeltaFletApp):
                    page_char_width = int((self.page.width -180) //9)
                    if page_char_width > PAGE_CHAR_WIDTH_SHOW_RICH_EXC:
                        exc_rich = rich.traceback.Traceback.from_exception(
                            exc_type, exc, exc.__traceback__, width = page_char_width,
                            show_locals = True, word_wrap = True
                        )
                        with exception_lock, console.capture() as capture:
                            console.print(exc_rich, width = page_char_width)
                        exc_text_rich = re.sub(r"\x1b\[[0-9;]*m", "", capture.get())
                        del exc_rich, capture
                        exc_text = f"{exc_text}\n{exc_text_rich}"
                        func_on_exc(self, exc_text)

                    else:
                        exc_text = f"{exc_text}\n" \
                            f"[详细异常回溯被隐藏, 原因: 单行字符宽度过窄. " \
                            f"({page_char_width} <= {PAGE_CHAR_WIDTH_SHOW_RICH_EXC})]"
                        func_on_exc(self, exc_text)

            # 没有异常.
            else:
                for code in exec_after_finish:
                    exec(code)

            # 运行结束.
            finally:
                if isinstance(self, ToolDeltaFletApp):
                    self.update()

            return ret, exception  # type: ignore  # noqa: PGH003

        return executor

    return wrapper


class ToolDeltaFletException(Exception): pass
class ToolDeltaFletError(ToolDeltaFletException): pass


class ToolDeltaFletApp:
    from 前置_ToolDeltaFlet import entry as __api

    def __init__(self, page: flet.Page) -> None:
        self.__theme_color_index = 3
        self.connected = False
        self.freq_lock = threading._RLock()
        self.action_lock = threading._RLock()
        self.update_lock = threading._RLock()
        self.thread_list: list[ToolDeltaThread] = []
        self.freq = {action: [] for action in freq_config}
        self.api = None

        self.page = page
        assert self.page.controls is not None

        self.page.fonts = {
            "MCASCII": "./asset/font/minecraft-seven.ttf", # 19.84, 19.88 *3
            "FiraCodeRegular": "./asset/font/FiraCode-Regular.ttf",
            "FiraCodeMedium": "./asset/font/FiraCode-Medium.ttf",
            "Consola": "./asset/font/consola.ttf",
            "MCGNU": "./asset/font/Minecraft GNU.ttf", # 15.9075
            "MCAE": "./asset/font/Minecraft AE.ttf"
        }
        self.page.title = "ToolDeltaFlet (TDF) - 租赁服远程管理网页"
        self.page.theme = flet.Theme(
            font_family = "MCGNU", color_scheme_seed = flet.colors.BLUE_100
        )
        self.page.dark_theme = flet.Theme(
            font_family = "MCGNU", color_scheme_seed = flet.colors.BLUE_900
        )
        self.page.theme_mode = flet.ThemeMode.SYSTEM
        self.page.padding = 0
        self.page.vertical_alignment = flet.MainAxisAlignment.CENTER
        self.page.on_resize = self.on_resize
        self._orig_close = self.page._close  # Flet: 删除 session 时没有调用 on_close
        self.page._close = self.on_close
        self.page.on_connect = self.on_connect
        self.page.on_disconnect = self.on_disconnect

        self.__init_controls__()
        self.page.navigation_bar = self.navi_bar
        self.page.controls.append(self.format)
        self.page.overlay.append(self.delay_text)
        self.page.overlay.append(flet.IconButton(
            flet.icons.SUNNY, bottom = 0, left = 0,
            on_click = self.switch_theme_daynight
        ))
        self.page.overlay.append(flet.IconButton(
            flet.icons.FORMAT_PAINT, bottom = 0, left = 36,
            on_click = self.switch_theme_color
        ))

        theme_color_index = \
            self.page.client_storage.get("ToolDeltaFlet_theme_color_index")
        need_to_reset_it = (theme_color_index is None) \
                        or (not isinstance(theme_color_index, int)) \
                        or (theme_color_index < 0) \
                        or (theme_color_index >= len(theme_color_list))
        if need_to_reset_it:
            theme_color_index = 3
        assert isinstance(theme_color_index, int)
        self.theme_color_index = theme_color_index

        self.on_connect()
        self.on_resize()

        self.page.update()
        app_list.append(self)


    def __init_controls__(self) -> None:
        self.delay_text = flet.Text(
            right = 10, bottom = 10,
            value = "-- ms", size = 10, color = flet.colors.GREY_500
        )

        self.banner_text = flet.Text("",
            font_family = "FiraCodeMedium", color = flet.colors.ERROR, selectable = True
        )
        self.banner_column = flet.Column(
            spacing = 0,
            height = 22,
            scroll = flet.ScrollMode.AUTO,
            controls = [
                self.banner_text
            ],
        )
        self.banner = flet.Banner(
            bgcolor = flet.colors.ERROR_CONTAINER,
            leading = flet.Icon(
                flet.icons.WARNING_AMBER_ROUNDED, color = flet.colors.ERROR, size = 40
            ),
            content = self.banner_column,
            actions = [
                flet.TextButton("关闭", on_click = self.close_banner),
            ],
        )

        self.navi_rail = flet.NavigationRail(
            visible = False,
            selected_index = -1,
            label_type = flet.NavigationRailLabelType.ALL,
            height = 200, width = 76,
            min_width = 76,
            group_alignment = -0.9,
            on_change = lambda evt: self.change_navi(
                evt.control.destinations[evt.control.selected_index].label_content.value, evt
            ),
            destinations = [
                flet.NavigationRailDestination(
                    label_content = flet.Text("主页", font_family = "MCGNU"),
                    icon = flet.icons.HOUSE_OUTLINED,
                    selected_icon = flet.icons.HOUSE
                ),
                flet.NavigationRailDestination(
                    label_content = flet.Text("插件", font_family = "MCGNU"),
                    icon = flet.icons.COMMENT_OUTLINED,
                    selected_icon = flet.icons.COMMENT
                ),
                flet.NavigationRailDestination(
                    label_content = flet.Text("设置", font_family = "MCGNU"),
                    icon = flet.icons.ACCOUNT_CIRCLE_OUTLINED,
                    selected_icon = flet.icons.ACCOUNT_CIRCLE
                ),
            ]
        )

        self.navi_bar = flet.NavigationBar(
            visible = False,
            on_change = lambda evt: self.change_navi(
                evt.control.destinations[evt.control.selected_index].label, evt
            ),
            destinations = [
                flet.NavigationDestination(
                    label = "主页",
                    icon = flet.icons.HOUSE_OUTLINED,
                    selected_icon = flet.icons.HOUSE
                ),
                flet.NavigationDestination(
                    label = "插件",
                    icon = flet.icons.COMMENT_OUTLINED,
                    selected_icon = flet.icons.COMMENT
                ),
                flet.NavigationDestination(
                    label = "设置",
                    icon = flet.icons.ACCOUNT_CIRCLE_OUTLINED,
                    selected_icon = flet.icons.ACCOUNT_CIRCLE
                ),
            ],
        )

        self.login_password_textfeild = flet.TextField(
            width = 300, password = True,
            hint_text = "密码", label = "密码",
            focused_border_color = flet.colors.PRIMARY,
            on_submit = self.login
        )
        self.login_button = flet.ElevatedButton(
            width = 200,
            text = "登录",
            on_click = self.login,
            style = flet.ButtonStyle(
                shape = flet.RoundedRectangleBorder(radius = 2),
            )
        )

        self.page_size_illegal_text = flet.Text("",
            font_family = "MCGNU", size = 16, text_align = flet.TextAlign.CENTER
        )
        self.format_page_size_illegal = flet.Column(
            expand = 90,
            data = "窗口过",
            alignment = flet.MainAxisAlignment.CENTER,
            controls = [
                flet.Container(
                    alignment = flet.alignment.center,
                    content = self.page_size_illegal_text
                )
            ]
        )

        self.format_unlogin = flet.Column(
            expand = 90, spacing = 0,
            data = "未登录",
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text(
                            "ToolDeltaFlet 登录", font_family = "MCGNU", size = 32
                        )
                    ]
                ),
                flet.Row(height = 10),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.login_password_textfeild
                    ]
                ),
                flet.Row(height = 4),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text(
                            "2025-05-15 说明:\n" \
                            "    输完密码时按 ENTER 可以登录啦.\n" \
                            "    qwq",
                            font_family = "MCGNU", size = 12),
                    ]
                ),
                flet.Row(height = 4),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.login_button
                    ]
                ),
                # flet.Row(height = 4),
                # flet.Row(
                #     alignment = flet.MainAxisAlignment.CENTER,
                #     controls = [
                #         self.removeClientStorageButton
                #     ]
                # )
            ]
        )

        self.logout_button = flet.ElevatedButton(
            width = 200,
            text = "登出",
            on_click = self.logout,
            style = flet.ButtonStyle(
                shape = flet.RoundedRectangleBorder(radius = 2),
            )
        )
        self.format_setting = flet.Column(
            expand = 90,
            data = "设置",
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text("设置", font_family = "MCGNU", size = 32)
                    ]
                ),
                flet.Container(
                    alignment = flet.alignment.center,
                    content = \
                        flet.Text(
                            "\nTip 1:\n" \
                            "    在 ToolDeltaFlet 加载中或刷新页面时, " \
                                "点一下进度条上方的图片, 可以全屏网页w\n" \
                            "手机横屏使用非常方便的~, 不会再被地址栏占用空间.\n" \
                            "\nTip 2:\n    敬请期待更多功能qwq",
                            weight = flet.FontWeight.W_600
                        )
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.logout_button
                    ]
                )
            ]
        )


        self.main_title_text = flet.Text(
            "ToolDeltaFlet", font_family = "MCGNU", size = 32
        )
        self.main_occupier = flet.Text(" ", font_family = "MCGNU", size = 32)
        self.main_playerlist_column = flet.Column(spacing = 4)
        self.format_main = flet.Column(
            expand = 90, spacing = 0,
            data = "主页",
            alignment = flet.MainAxisAlignment.SPACE_BETWEEN,
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.main_title_text,
                    ]
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.main_playerlist_column
                    ]
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.main_occupier,
                    ]
                ),
            ]
        )

        self.format = flet.Row(
            vertical_alignment = flet.CrossAxisAlignment.START,
            alignment = flet.MainAxisAlignment.CENTER,
            expand = False,
            controls = [
                self.banner,
                self.navi_rail,
                flet.VerticalDivider(width = 1, opacity = 0.5),
                flet.Column(expand = 2),
                self.format_unlogin,
                flet.Column(expand = 2),
                flet.Column(width = 0)
            ]
        )


    def update(self) -> None:
        with self.update_lock:
            try:
                self.page.update()
            except PageDisconnectedException:
                self.on_disconnect()
                self.on_close()


    def on_connect(self, evt: Any = None) -> None:
        fmts.print_inf(f"{self.page.session_id} 连接网页.")
        self.connected = True
        self._thread_start()


    def on_disconnect(self, evt: Any = None) -> None:
        fmts.print_inf(f"{self.page.session_id} 断开网页.")
        self.connected = False
        self._thread_stop()


    def on_close(self) -> None:
        fmts.print_inf(f"{self.page.session_id} 会话结束.")
        if self in app_list:
            app_list.remove(self)
        self._orig_close()
        assert self.page.controls is not None
        self.connected = False
        self.page.controls.clear()
        self.page.overlay.clear()


    def show_exc_on_banner(self, text: str) -> None:
        text = text.removesuffix("\n")
        text = f"啊.. 这里有一些错误..\n怎会这样\n{text}"

        if self.banner.open and (self.banner_text.value == text):
            self.close_banner()
            time.sleep(0.1)

        height = 22 *len(text.splitlines())
        if self.page.width <= WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN:
            height += 22
        height = min(self.page.height, height)

        self.banner_text.value = text
        self.banner_column.height = height
        self.banner.open = True
        self.update()


    def check_freq(self, action: str) -> Decimal:
        with self.freq_lock:
            interval: int = freq_config[action]["interval"]
            max_action_count: int = freq_config[action]["count"]
            if len(self.freq[action]) < max_action_count:
                time_await = Decimal(0)
            else:
                interval_passed = time.time() -(self.freq[action][-max_action_count])
                time_await = Decimal(max(interval -interval_passed, 0))
                time_await.quantize(ONE_PERCENT)

            if time_await == 0:
                self.freq[action].append(time.time())
                self.freq[action] = self.freq[action][-max_action_count:]

        return time_await


    @on_exception(show_exc_on_banner)
    def switch_theme_daynight(self, evt: Any) -> None:
        with self.action_lock:
            action_too_frequently = self.check_freq("switch_theme")
            if action_too_frequently:
                return
            self.page.theme_mode = \
                     flet.ThemeMode.LIGHT \
                if (self.page.theme_mode == flet.ThemeMode.DARK) \
                else flet.ThemeMode.DARK
            self.close_banner()


    @on_exception(show_exc_on_banner)
    def switch_theme_color(self, evt: Any) -> None:
        with self.action_lock:
            action_too_frequently = self.check_freq("switch_theme")
            if action_too_frequently:
                return
            theme_color_index = self.theme_color_index
            if theme_color_index +1 >= len(theme_color_list):
                theme_color_index = 0
            else:
                theme_color_index += 1
            self.theme_color_index = theme_color_index
        self.update()
        self.page.client_storage.set(
            "ToolDeltaFlet_theme_color_index", theme_color_index
        )


    @property
    def theme_color_index(self) -> int:
        return self.__theme_color_index


    @theme_color_index.setter
    def theme_color_index(self, index: int) -> None:
        assert self.page.theme is not None
        assert self.page.dark_theme is not None
        self.__theme_color_index = index
        self.page.theme.color_scheme_seed = theme_color_list[index][0]
        self.page.dark_theme.color_scheme_seed = theme_color_list[index][1]


    def raise_exception(
        self, exc: BaseException, from_exc: Optional[BaseException] = None
    ) -> None:
        if from_exc:
            raise exc from from_exc
        raise exc


    def close_banner(self, evt: Any = None) -> None:
        self.banner_column.height = 0
        self.banner.open = False
        self.update()


    @on_exception(show_exc_on_banner)
    def on_resize(self, evt: Any = None) -> None:
        logged_in = self.api is not None

        if self.page.width < WINDOW_WIDTH_PIXEL_MIN:
            self.navi_rail.visible = False
            self.navi_bar.visible = False
            self.format.controls[2].visible = False
            self.format.controls[3].visible = False
            self.format.controls[5].visible = False
            self.change_navi("窗口过窄")
        elif self.page.width > WINDOW_WIDTH_PIXEL_MAX:
            self.navi_rail.visible = False
            self.navi_bar.visible = False
            self.format.controls[2].visible = False
            self.format.controls[3].visible = False
            self.format.controls[5].visible = False
            self.change_navi("窗口过宽")
        elif self.page.height < WINDOW_HEIGHT_PIXEL_MIN:
            self.navi_rail.visible = False
            self.navi_bar.visible = False
            self.format.controls[2].visible = False
            self.format.controls[3].visible = False
            self.format.controls[5].visible = False
            self.change_navi("窗口过矮")

        elif WINDOW_WIDTH_PIXEL_MIN <= self.page.width < WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN:
            self.navi_bar.visible = bool(logged_in)
            self.navi_rail.visible = False
            self.format.controls[2].visible = False
            self.format.controls[3].visible = bool(logged_in)
            self.format.controls[5].visible = bool(logged_in)
            if self.current_navi.startswith("窗口过"):
                self.change_navi()
        elif WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN <= self.page.width <= WINDOW_WIDTH_PIXEL_MAX:
            self.navi_bar.visible = False
            self.navi_rail.visible = bool(logged_in)
            self.format.controls[2].visible = bool(logged_in)
            self.format.controls[3].visible = bool(logged_in)
            self.format.controls[5].visible = bool(logged_in)
            if self.current_navi.startswith("窗口过"):
                self.change_navi()
        else:
            raise ToolDeltaFletException("处理窗口大小变化事件异常: 出现例外情况.")

        if WINDOW_WIDTH_PIXEL_MIN <= self.page.width < WINDOW_WIDTH_PIXEL_SHOW_EXTENTIONS_MIN:
            pass
        elif WINDOW_WIDTH_PIXEL_SHOW_EXTENTIONS_MIN <= self.page.width <= WINDOW_WIDTH_PIXEL_MAX:
            pass


        # self.pageWindowSizeIllegleFormat.height = self.page.height -4 -bottomHeight


    @property
    def current_navi(self) -> str:
        return self.format.controls[4].data


    @on_exception(show_exc_on_banner)
    def change_navi(self, navi_name: Optional[str] = None, evt: Any = None) -> None:
        assert self.navi_rail.destinations
        not_logged_in = self.api is None
        if not_logged_in:
            self.format.expand = False
        else:
            self.format.expand = True

        for navi_dst_index, navi_dst in enumerate(self.navi_rail.destinations):
            assert isinstance(navi_dst.label_content, flet.Text)

            if navi_name == navi_dst.label_content.value:
                self.navi_rail.selected_index = navi_dst_index
                self.navi_rail.selected_index = navi_dst_index
            if navi_name is None:
                if self.navi_rail.selected_index == -1:
                    navi_name = "未登录"
                if self.navi_rail.selected_index == navi_dst_index:
                    navi_name = navi_dst.label_content.value

        if navi_name == "窗口过窄":
            self.page_size_illegal_text.value = \
                f"窗口过窄, 请尝试增宽窗口至 {WINDOW_WIDTH_PIXEL_MIN}px 及以上.\n" \
                f"当前宽度: {self.page.width}px."
            self.format.controls[4] = self.format_page_size_illegal
            return
        if navi_name == "窗口过宽":
            self.page_size_illegal_text.value = \
                f"窗口过宽, 请尝试缩减窗口至 {WINDOW_WIDTH_PIXEL_MAX}px 及以下.\n" \
                f"当前宽度: {self.page.width}px."
            self.format.controls[4] = self.format_page_size_illegal
            return
        if navi_name == "窗口过矮":
            self.page_size_illegal_text.value = \
                f"窗口过矮, 请尝试增高窗口至 {WINDOW_HEIGHT_PIXEL_MIN}px 及以上.\n" \
                f"当前高度: {self.page.height}px."
            self.format.controls[4] = self.format_page_size_illegal
            return

        illegal_change = (not self.current_navi.startswith("窗口过")) \
                     and (not_logged_in and (navi_name != "未登录"))
        if illegal_change:
            raise ToolDeltaFletException("切换导航栏异常: 未登录.")

        if navi_name == "主页":
            self.format.controls[4] = self.format_main
        if navi_name == "插件":
            pass
        if navi_name == "设置":
            self.format.controls[4] = self.format_setting
        if navi_name == "未登录":
            self.format.controls[4] = self.format_unlogin


    @on_exception(
        show_exc_on_banner,
        exec_after_finish = ["self.login_button.disabled = False"]
    )
    def login(self, evt: Any = None) -> None:
        self.login_button.disabled = True
        self.login_button.text = "登录"
        self.login_password_textfeild.error_text = ""

        password = self.login_password_textfeild.value
        password = password or ""
        password_is_empty = not password
        password_is_too_short = len(password) < 4
        password_is_too_long = len(password) > 24
        can_not_login = password_is_empty \
                     or password_is_too_short \
                     or password_is_too_long
        fmts.print_inf(f"登录按钮被点击, 密码是 {password}")

        if can_not_login:
            if password_is_empty:
                self.login_password_textfeild.error_text = "请输入密码."
            elif password_is_too_short:
                self.login_password_textfeild.error_text = "密码过短."
            elif password_is_too_long:
                self.login_password_textfeild.error_text = "密码过长."
            return

        login_too_frequently = self.check_freq("login")
        if login_too_frequently:
            self.login_button.text = f"登录不能这么频繁哦, \n" \
                                     f"请 {login_too_frequently:.2f}s 后再试."
            return

        with self.action_lock:
            self.login_button.text = "登录中.."
            self.update()
            time.sleep(0.5)

            password_wrong = password != self.__api.password
            if password_wrong:
                self.login_password_textfeild.error_text = "密码错误."
                self.login_button.text = "密码错误."
                return

            self.login_button.text = "登录成功!"
            self.update()

            self.login_button.text = "登录"
            self.api = self.__api
            self.on_resize()
            self.change_navi("主页")


    @on_exception(show_exc_on_banner)
    def logout(self, evt: Any = None) -> None:
        with self.action_lock:
            self.api = None
            self.navi_rail.selected_index = -1
            self.change_navi("未登录")
            self.on_resize()


    def _thread_start(self) -> None:
        self.thread_list.append(
            utils.createThread(
                self._thread_show_delay, usage = "Flet App 显示延迟"
            )
        )
        self.thread_list.append(
            utils.createThread(
                self._thread_show_playerlist, usage = "Flet App 显示玩家列表"
            )
        )


    def _thread_stop(self) -> None:
        for thread in self.thread_list:
            thread.stop()


    @on_exception(show_exc_on_banner)
    def _thread_show_delay(self) -> None:
        while self.connected:
            time_start = time.perf_counter()
            try:
                time_delay_start = time.perf_counter()
                self.page.client_storage.contains_key(
                    f"ToolDeltaFlet_delay_{int(time_delay_start)}"
                )
                time_delay_ms = round((time.perf_counter() -time_delay_start) *1000)
                self.delay_text.value = f"网页延迟: {time_delay_ms} ms\n保留所有权利."
            except TimeoutError:
                self.delay_text.value = "网页延迟: 测量失败"
            if not self.connected:
                break
            self.update()
            time_spend = time.perf_counter() -time_start
            time.sleep((2 -time_spend) if (time_spend < 2) else 0)


    @on_exception(show_exc_on_banner)
    def _thread_show_playerlist(self) -> None:
        while self.connected:
            time_start = time.perf_counter()
            if self.api:
                self.main_playerlist_column.controls.clear()
                self.main_playerlist_column.controls.append(
                    flet.Row(
                        alignment = flet.MainAxisAlignment.START,
                        spacing = 0, width = 200,
                        controls = [
                            flet.Text(
                                "在线玩家:",
                                size = 16, text_align = flet.TextAlign.START
                            )
                        ]
                    )
                )
                for playername in self.api.game_ctrl.allplayers:
                    self.main_playerlist_column.controls.append(
                        flet.Row(
                            alignment = flet.MainAxisAlignment.CENTER,
                            spacing = 0, width = 200,
                            controls = [
                                flet.Text(
                                    playername,
                                    size = 16, text_align = flet.TextAlign.CENTER
                                )
                            ]
                        )
                    )
                self.update()
            time_spend = time.perf_counter() -time_start
            time.sleep((5 -time_spend) if (time_spend < 5) else 0)


    @on_exception(show_exc_on_banner)
    def _test_type_checking(self, text: str) -> int:
        return len(text)

    def _test_type_checking2(self) -> None:
        ret, exc = self._test_type_checking("123")
        if exc:
            raise exc
        typechecking = ret, exc
        print(typechecking)


def main(page: flet.Page) -> None:
    ToolDeltaFletApp(page)


@utils.thread_func("Flet App")
def launch(port: int) -> None:
    os.environ["FLET_SESSION_TIMEOUT"] = "60"
    os.environ["FLET_FORCE_WEB_SERVER"] = "yes"
    # os.environ["FLET_DISPLAY_URL_PREFIX"] = "网页已成功启动于"
    flet.fastapi.flet_app.DEFAULT_FLET_SESSION_TIMEOUT = 60
    flet.fastapi.flet_app_manager.app_manager.__evict_sessions_task = None
    signal.signal = lambda *_, **__: None
    fastapi.logger.logger.setLevel(100)
    logging.basicConfig(level = 50)
    try:
        flet.app(
            target = main, port = port, assets_dir = ".",
            view = flet.AppView.WEB_BROWSER, web_renderer = flet.WebRenderer.CANVAS_KIT,
            use_color_emoji = True
        )
    except (ThreadExit, CancelledError):
        close()
        return


def close() -> None:
    # Flet issue: reload 时, 没有重新启动删除过期 session 的线程
    app_manager = flet.fastapi.flet_app_manager.app_manager
    app_manager._FletAppManager__evict_sessions_task = None  # type: ignore  # noqa: PGH003
    for app in app_list.copy():
        app.on_close()
    assert not app_list
