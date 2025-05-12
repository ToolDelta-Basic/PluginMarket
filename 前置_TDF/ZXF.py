# ZhiXueFlet
# 作者: wangzm5773.
# s=51497882; print(json.dumps(exam.getExamStudentScoreDetailList()[str(s)], ensure_ascii = False, indent = 4))
# print(zhixue.ZhiXueDict[zhixue.account2ID[input()]].userName)
# zhixue.ZhiXueTGTlist["zxt2720329"].scan_QR(input("deviceID: "), input("codeID: "))
# "C:\Program Files\Python313\python.exe" C:\Users\xX7912Xx\Desktop\ZhiXueFlet\develop\FletExample\colors_browser\main.py
# def f(): lambda: k; k=1; print([locals() for k in [0]])
# zhixue.ZhiXueTGTlist[ZhiXueAdmin.userAccount].scan_QR(input("deviceID: "), input("codeID: "))
# print(zhixue.ZhiXueMobileTemp("zxt2332213").getMarkingExamList())
from __future__ import annotations
print(f"ZhiXueFlet 以 {__name__} 运行.")
from typing import Union, Any, Callable, Final, Literal, Optional, _LiteralGenericAlias, overload, TypeVar, Type, cast, get_args, get_origin, get_type_hints, runtime_checkable, TYPE_CHECKING, Protocol, final, no_type_check, no_type_check_decorator, TypeAlias # type: ignore
from types import GenericAlias
from decimal import Decimal
import traceback, sys, logging, time, dataclasses, re, os, datetime, threading, copy, json, base64, random, ctypes, string
import flet, rich, rich.console, rich.traceback
from flet_core.page import PageDisconnectedException
from stoppableThread import StoppableThread, stoppableThreadList, StoppableThreadStopping
from social import User, Conn, sysusr, sysgrp, tmpusr, tmpgrp, expusr, expgrp, friend_req_list, conn_dict, SocialException, SocialError, SocialIllegalOp
import zhixue
try:
    from zhixue import ZhiXue, ZhiXueNoPwdStudent, ZhiXueError, ZhiXueException, ZhiXueExamAdvance, ZhiXueProcessStopped, ZhiXueExamReportUpdateTimeTooRecentError, ZhiXueExamClassNumTooManyError, ZhiXueNoPermissionError, ZhiXueExamStudentNotFoundError, Exam as ZhiXueExam, ExamDict as ZhiXueExamDict, lockList as ZhiXueLockList, console, featureWhitelist, TIME_START, TIME_WAIT_FOR_REPORT_TO_BE_GENERATED, TIME_ONE_HOUR
    zhixue.initPyPI()
    from zhixue import ZhiXueAdmin, ExamCreateLock, ZhiXueCreateLock, ExamGetLock
except Exception:
    print(traceback.format_exc(), end = "")
    input("按回车键退出...")
    sys.exit(1)
logging.basicConfig(level = logging.INFO)
LEGAL_ASCII_CHARACTER = string.printable.strip(string.whitespace)
WINDOW_WIDTH_PIXEL_MIN = 320
WINDOW_WIDTH_PIXEL_MAX = 2000
WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN = 650
WINDOW_HEIGHT_PIXEL_MIN = 320
DISPLAY_WIDTH_PIXEL_MIN = 800
DISPLAY_WIDTH_PIXEL_MAX = 12000000000000000
SCORE_ADVANCE_DISABLED = False
GENERATE_REPORT_DISABLED = False
FREQUENCY_DATA: Final = {
    "login": {"INTERVAL": 300, "MAX_ACTION_NUM": 3},
    "restart": {"INTERVAL": 120, "MAX_ACTION_NUM": 1},
    "refreshExamList": {"INTERVAL": 5, "MAX_ACTION_NUM": 1},
    "refreshSocialList": {"INTERVAL": 1, "MAX_ACTION_NUM": 1},
    "refreshChatDetail": {"INTERVAL": 0.5, "MAX_ACTION_NUM": 1},
    "refreshExamDetail": {"INTERVAL": 120000, "MAX_ACTION_NUM": 2},
    "refreshExamDetailCache": {"INTERVAL": 5, "MAX_ACTION_NUM": 1},
    "examDetailSubjectContainerClick": {"INTERVAL": 1, "MAX_ACTION_NUM": 1},
    "examDetailSwitchScoreRank": {"INTERVAL": 0.5, "MAX_ACTION_NUM": 1},
    "switchDayNight": {"INTERVAL": 0.5, "MAX_ACTION_NUM": 1},
    "switchColor": {"INTERVAL": 0.5, "MAX_ACTION_NUM": 1},
}
EXAM_LIST_ADVANCE = {
    "7a6664b2-0142-40f0-95c9-d9e035de51d7": {
        "reportType": "exam",
        "finished": False,
        "published": False,
        "exam_is_gotten_by_teacher": True,
        "examCreateTime": time.time(),
        "examName": "第二次模考",
        "preload": True
    },
}
EXAM_LIST_JSON = {
    "./data/zero_simulation.json": {
        "reportType": "exam",
        "finished": True,
        "published": True,
        "exam_is_gotten_by_teacher": False,
        "examCreateTime": 1742199433,
        "examName": "03.14 百校联考",
        "preload": False
    }
}
if not os.path.isdir("./log/"): os.makedirs("./log/")

xiezhen = ZhiXue("53946824", "Alzm0514pyb")



def checkObjectConformGeneric(obj: Any, generic: Union[GenericAlias, _LiteralGenericAlias]) -> bool:
    if isinstance(generic, _LiteralGenericAlias):
        return obj in generic.__args__
    if not isinstance(generic, GenericAlias):
        raise TypeError(f"检查对象是否符合泛型异常: {type(generic)} 不是泛型.")
    objTypeGeneric = generic.__origin__
    if not isinstance(obj, objTypeGeneric):
        return False
    if objTypeGeneric is list:
        itemTypeGeneric = generic.__args__[0]
        itemFunc = checkObjectConformGeneric if isinstance(itemTypeGeneric, (GenericAlias, _LiteralGenericAlias)) else isinstance
        if not all(itemFunc(item, itemTypeGeneric) for item in obj):
            return False
    elif objTypeGeneric is dict:
        keyTypeGeneric, valueTypeGeneric = generic.__args__
        keyFunc = checkObjectConformGeneric if isinstance(keyTypeGeneric, (GenericAlias, _LiteralGenericAlias)) else isinstance
        valueFunc = checkObjectConformGeneric if isinstance(valueTypeGeneric, (GenericAlias, _LiteralGenericAlias)) else isinstance
        if not all((keyFunc(key, keyTypeGeneric) and valueFunc(value, valueTypeGeneric)) for key, value in obj.items()):
            return False
    elif objTypeGeneric is tuple:
        if len(obj) != len(generic.__args__):
            return False
        for item, itemTypeGeneric in zip(obj, generic.__args__):
            itemFunc = checkObjectConformGeneric if isinstance(itemTypeGeneric, (GenericAlias, _LiteralGenericAlias)) else isinstance
            if not itemFunc(item, itemTypeGeneric):
                return False
    else:
        raise ValueError("检查对象是否符合泛型异常: 不支持的泛型.")
    return True


def PKCS7(data, block_size = 16):
    if type(data) not in {bytes, bytearray}:
        raise TypeError("PKCS7 填充异常: 数据类型应为 bytes 或 bytearray")
    pl = block_size - (len(data) % block_size)
    return data + bytearray([pl for _ in range(pl)])


def crash():
    globals().clear()
    import builtins
    del builtins.ArithmeticError, builtins.AssertionError, builtins.AttributeError, builtins.BaseException, builtins.BlockingIOError, builtins.BrokenPipeError, builtins.BufferError, builtins.BytesWarning, builtins.ChildProcessError, builtins.ConnectionAbortedError, builtins.ConnectionError, builtins.ConnectionRefusedError, builtins.ConnectionResetError, builtins.DeprecationWarning, builtins.EOFError, builtins.Ellipsis, builtins.EncodingWarning, builtins.EnvironmentError, builtins.Exception, builtins.FileExistsError, builtins.FileNotFoundError, builtins.FloatingPointError, builtins.FutureWarning, builtins.GeneratorExit, builtins.IOError, builtins.ImportError, builtins.ImportWarning, builtins.IndentationError, builtins.IndexError, builtins.InterruptedError, builtins.IsADirectoryError, builtins.KeyError, builtins.KeyboardInterrupt, builtins.LookupError, builtins.MemoryError, builtins.ModuleNotFoundError, builtins.NameError, builtins.NotADirectoryError, builtins.NotImplemented, builtins.NotImplementedError, builtins.OSError, builtins.OverflowError, builtins.PendingDeprecationWarning, builtins.PermissionError, builtins.ProcessLookupError, builtins.RecursionError, builtins.ReferenceError, builtins.ResourceWarning, builtins.RuntimeError, builtins.RuntimeWarning, builtins.StopAsyncIteration, builtins.StopIteration, builtins.SyntaxError, builtins.SyntaxWarning, builtins.SystemError, builtins.SystemExit, builtins.TabError, builtins.TimeoutError, builtins.TypeError, builtins.UnboundLocalError, builtins.UnicodeDecodeError, builtins.UnicodeEncodeError, builtins.UnicodeError, builtins.UnicodeTranslateError, builtins.UnicodeWarning, builtins.UserWarning, builtins.ValueError, builtins.Warning, builtins.WindowsError, builtins.ZeroDivisionError, builtins.__build_class__, builtins.__doc__, builtins.__import__, builtins.__loader__, builtins.__name__, builtins.__package__, builtins.__spec__, builtins.abs, builtins.aiter, builtins.all, builtins.anext, builtins.any, builtins.ascii, builtins.bin, builtins.bool, builtins.breakpoint, builtins.bytearray, builtins.bytes, builtins.callable, builtins.chr, builtins.classmethod, builtins.compile, builtins.complex, builtins.copyright, builtins.credits, builtins.delattr, builtins.dict, builtins.dir, builtins.divmod, builtins.enumerate, builtins.eval, builtins.exec, builtins.exit, builtins.filter, builtins.float, builtins.format, builtins.frozenset, builtins.getattr, builtins.globals, builtins.hasattr, builtins.hash, builtins.help, builtins.hex, builtins.id, builtins.input, builtins.int, builtins.isinstance, builtins.issubclass, builtins.iter, builtins.len, builtins.license, builtins.list, builtins.locals, builtins.map, builtins.max, builtins.memoryview, builtins.min, builtins.next, builtins.object, builtins.oct, builtins.open, builtins.ord, builtins.pow, builtins.print, builtins.property, builtins.quit, builtins.range, builtins.repr, builtins.reversed, builtins.round, builtins.set, builtins.setattr, builtins.slice, builtins.sorted, builtins.staticmethod, builtins.str, builtins.sum, builtins.super, builtins.tuple, builtins.type, builtins.vars, builtins.zip
    # del builtins.BaseExceptionGroup, builtins.ExceptionGroup
    del builtins


def deleteObject(obj):
    refObjID = id(obj)
    refObjSize = sys.getsizeof(obj)
    refObj = ctypes.c_longlong.from_address(refObjID)
    refNum = refObj.value
    # for i in list(range(refObjID +1, refObjID +refObjSize +1))[::-1]:
    #     j = ctypes.c_longlong.from_address(i)
    #     j.value = 0
    refObj.value = 0
    # temp = obj
    # del temp
    refNumAC = refObj.value
    return refNum, refNumAC


def unlockZhixueLock():
    for i in zhixue.lockList:
        try:
            i._release_save() # type: ignore
        except RuntimeError:
            pass
    # try:
    #     zhixue.lockList[0]._release_save() # type: ignore
    # except RuntimeError:
    #     pass
    # try:
    #     zhixue.lockList[3]._release_save() # type: ignore
    # except RuntimeError:
    #     pass
    # try:
    #     zhixue.lockList[0]._release_save() # type: ignore
    # except RuntimeError:
    #     pass
    # try:
    #     zhixue.lockList[3]._release_save() # type: ignore
    # except RuntimeError:
    #     pass


def showExc(funcOnExc: Callable, execAfterFinish = [], execAfterException = []) -> Callable:
    def prerun(func: Callable) -> Callable:
        def run(self: ZhiXueFlet, *args, **kwargs) -> Union[Any, BaseException]:
            try:
                result = func(self, *args, **kwargs)
            except (ZhiXueFletError, ZhiXueProcessStopped, ZhiXueExamClassNumTooManyError, ZhiXueExamReportUpdateTimeTooRecentError) as exc:
                result = exc
                excType = type(exc)
                excInfo = f"{excType.__name__}: {exc}"
                print(excInfo)
                funcOnExc(self, "", f"{exc}")
                for code in execAfterException:
                    exec(code)
            except AssertionError as exc:
                result = exc
                excType = type(exc)
                excInfo = f"{excType.__name__}: {exc}"
                print(excInfo)
                funcOnExc(self, "Flet 框架遇到问题.\n若页面响应不正常, 可重启浏览器.", excInfo)
                for code in execAfterException:
                    exec(code)
            except StoppableThreadStopping:
                raise
            except BaseException as exc:
                result = exc
                excType = type(exc)
                excInfo = f"{excType.__name__}: {exc}"
                excInfoFull = traceback.format_exc()
                print(excInfoFull)

                excWidth = console.width -2
                excInfoRich = rich.traceback.Traceback.from_exception(excType, exc, exc.__traceback__, width = excWidth, show_locals = True)
                with console.capture() as capture:
                    console.print(excInfoRich)
                excInfoRich = capture.get()
                print(excInfoRich)
                with open(f"./log/Exception_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')[:-3]}.txt", "w", encoding = "utf-8") as file:
                    file.write(excInfoRich)
                del excInfoRich, capture

                excWidth = int((self.page.width -180) //9)
                if excWidth > float("INF"):
                    del excInfoFull
                    excInfoRich = rich.traceback.Traceback.from_exception(excType, exc, exc.__traceback__, width = excWidth, show_locals = True)
                    with console.capture() as capture:
                        console.print(excInfoRich, width = excWidth)
                    del excInfoRich
                    funcOnExc(self, re.sub(r"\x1b\[[0-9;]*m", "", capture.get()), excInfo)
                else:
                    funcOnExc(self, f"[详细异常回溯被隐藏, 原因: 单行字符宽度过窄. ({excWidth} <= inf)]", excInfo)
            for code in execAfterFinish:
                exec(code)
            self.update()
            return result
        return run
    return prerun


def _consoleThread() -> None:
    while True:
        try:
            exec(input())
        except BaseException as exc:
            print(traceback.format_exc(), end = "", flush = True)
            if isinstance(exc, (KeyboardInterrupt, EOFError, StoppableThreadStopping)):
                return


def deadLockDetectThread() -> None:
    while True:
        deadLocked = True
        for i in range(12):
            if showLoadingContainer:
                deadLocked = False
            lockedNum = 0
            for lock in ZhiXueLockList:
                if type(lock) == threading.Lock: lockedNum += lock.locked()
                else:
                    locked = not lock.acquire(timeout = 0.0001)
                    if not locked: lock.release()
                    lockedNum += locked
            if lockedNum == 0:
                deadLocked = False
            time.sleep(1)
        if deadLocked:
            print("强制解除死锁.")
            # unlockZhixueLock()
            # unlockZhixueLock()



class ZhiXueFletException(Exception): pass
class ZhiXueFletError(ZhiXueFletException): pass



class WithBoolen():
    def __init__(self: WithBoolen, value: bool) -> None:
        self._value = value
        self._lock = threading.Lock()
    def __bool__(self: WithBoolen) -> bool:
        return self._value
    def __repr__(self: WithBoolen) -> str:
        return f"{self._value} (withable)"
    def __eq__(self: WithBoolen, other: Any) -> bool:
        return self._value == other
    def __ne__(self, other: object) -> bool:
        return self._value != other
    def __enter__(self: WithBoolen) -> WithBoolen:
        with self._lock:
            self._valueEnter = self._value
            self._value = not self._value
            return self
    def __exit__(self: WithBoolen, exc_type, exc_value, exc_traceback) -> None:
        with self._lock:
            self._value = self._valueEnter
            del self._valueEnter



need_to_regenerate_white_list = False
if not os.path.isfile("./data/whiteList.json"):
    need_to_regenerate_white_list = True
else:
    with open("./data/whiteList.json", "r", encoding = "utf-8") as file:
        whiteList = json.load(file)
    if not checkObjectConformGeneric(whiteList, dict[
        Literal["userIDlist", "classIDlist", "schoolIDlist", "fakestudent"], list[str]
    ]): need_to_regenerate_white_list = True
if need_to_regenerate_white_list:
    whiteList = {
        "schoolIDlist": [],
        "classIDlist": [],
        "userIDlist": [],
        "fakestudent": []
    }
    with open("./data/whiteList.json", "w", encoding = "utf-8") as file:
        json.dump(whiteList, file, ensure_ascii = False, indent = 4)

if os.path.isfile("./data/frequency.json"):
    with open("./data/frequency.json", "r", encoding = "utf-8") as file:
        frequencyDict = json.load(file)
else:
    frequencyDict = {}
    with open("./data/frequency.json", "w", encoding = "utf-8") as file:
        json.dump(frequencyDict, file, ensure_ascii = False, indent = 4)
frequencySetLock = threading.Lock()
pageList: list[ZhiXueFlet] = []
showLoadingContainer = False
themeColorList = [
    [flet.colors.RED_500, flet.colors.RED_900],
    [flet.colors.ORANGE_500, flet.colors.ORANGE_900],
    [flet.colors.GREEN_100, flet.colors.GREEN_900],
    [flet.colors.BLUE_100, flet.colors.BLUE_900],
    [flet.colors.INDIGO_100, flet.colors.INDIGO_900],
    [flet.colors.DEEP_PURPLE_100, flet.colors.DEEP_PURPLE_900],
    [flet.colors.PURPLE_100, flet.colors.PURPLE],
]
class ZhiXueFlet():
    def __init__(self: ZhiXueFlet, page: flet.Page) -> None:
        self.zhixue = None
        self.socialusr = None
        self.connected = False
        self.actionLock = threading.Lock()
        self.updateLock = threading.Lock()
        self.zhixue_is_nopwd_student = None
        self.can_view_marking_teacher: bool = False

        self.page = page
        if self.page.controls is None:
            raise ZhiXueFletException("初始化 ZhiXueFlet 对象异常: page.controls 为空.")
        self.page.fonts = {
            "MCASCII": "./asset/font/minecraft-seven.ttf", # 19.84, 19.88 *3
            "FiraCodeRegular": "./asset/font/FiraCode-Regular.ttf",
            "FiraCodeMedium": "./asset/font/FiraCode-Medium.ttf",
            "Consola": "./asset/font/consola.ttf",
            "MCGNU": "./asset/font/Minecraft GNU.ttf", # 15.9075
            "MCAE": "./asset/font/Minecraft AE.ttf"
        }
        self.page.title = "ZhiXueFlet (ZXF) - 智学网成绩查询网页."
        self.page.theme = flet.Theme(font_family = "MCGNU", color_scheme_seed = flet.colors.BLUE_100)
        self.page.dark_theme = flet.Theme(font_family = "MCGNU", color_scheme_seed = flet.colors.BLUE_900)
        self.page.theme_mode = flet.ThemeMode.SYSTEM
        self.page.scroll = flet.ScrollMode.AUTO
        self.page.padding = 0
        self.__initControl__()
        self.onConnect()
        self.page.on_resize = self.onResize
        self.page.on_close = self.onClose
        self.page.on_connect = self.onConnect
        self.page.on_disconnect = self.onDisconnect
        self.page.pubsub.subscribe_topic("social_msg", self.onMsgRecv)
        self.page.controls.append(self.format)
        self.page.overlay.append(self.dialog)
        self.page.overlay.append(self.loadingContainer)
        self.page.overlay.append(self.delayText)
        self.page.overlay.append(flet.IconButton(
            flet.icons.SUNNY, bottom = 0, left = 0,
            on_click = self.switchDayNight
        ))
        self.page.overlay.append(flet.IconButton(
            flet.icons.FORMAT_PAINT, bottom = 0, left = 36,
            on_click = self.switchColor
        ))
        self.page.navigation_bar = self.naviBar

        self.themeColorIndex = 3
        try:
            theme_color_index_in_client_stroage = self.page.client_storage.contains_key(f"ZhiXueFlet_themeColorIndex")
            if theme_color_index_in_client_stroage:
                themeColorIndex = self.page.client_storage.get(f"ZhiXueFlet_themeColorIndex")
                if not isinstance(themeColorIndex, int):
                    themeColorIndex = 3
                self.themeColorIndex = themeColorIndex
        except TimeoutError as exc:
            print(exc)
        self.setColorByIndex(self.themeColorIndex)

        # self.zhixueAccountTextField.disabled = True
        # self.zhixuePasswordTextField.disabled = True

        self.onResize()
        self.changeRail("账号")
        pageList.append(self)


    @property
    def frequency(self: ZhiXueFlet) -> dict[str, list[float]]:
        if self.zhixue is None:
            userID = str(self.zhixueAccountTextField.value)
        else:
            userID = self.zhixue.userID
        if not userID:
            userID = "None"
            # raise ZhiXueFletException("获取用户操作频率异常: 用户未登录智学网.")
        if userID not in frequencyDict:
            frequencyDict[userID] = {key: copy.deepcopy([]) for key in FREQUENCY_DATA}
        return frequencyDict[userID]


    def onConnect(self: ZhiXueFlet, *args, **kwargs) -> None:
        self.connected = True
        print(f"[{time.strftime('%H:%M:%S', time.localtime())}] {self.page.session_id} {self.page.client_ip} 连接网页 WebSocket.")
        self.loopThread = StoppableThread(name = f"ZhiXueFlet_{self.page.session_id}", target = self._loopThread, data = {"": ""}, daemon = True)


    def onDisconnect(self: ZhiXueFlet, *args, **kwargs) -> None:
        self.connected = False
        print(f"[{time.strftime('%H:%M:%S', time.localtime())}] {self.page.session_id} {self.page.client_ip} 断开网页 WebSocket.")
        self.loopThread.stop()


    def onClose(self: ZhiXueFlet, *args, **kwargs) -> None:
        print(f"[{time.strftime('%H:%M:%S', time.localtime())}] {self.page.session_id} {self.page.client_ip} 会话关闭.")
        pageList.remove(self)
        if self.page.controls is None:
            raise ZhiXueFletException("处理会话关闭事件异常: page.controls 为空.")
        self.naviRail.destinations.clear()
        self.naviBar.destinations.clear()
        self.format.controls.clear()
        self.page.controls.clear()
        self.page.overlay.clear()
        self.page.navigation_bar = None
        self.update()
        self.clear()
        del self.page


    def update(self: ZhiXueFlet) -> None:
        with self.updateLock:
            try:
                self.page.update()
            except PageDisconnectedException:
                self.onDisconnect()
                self.onClose()


    def showOthersLoadingContainer(self: ZhiXueFlet) -> None:
        global showLoadingContainer
        showLoadingContainer = True
        for page in pageList:
            if page != self:
                if page.loadingContainer.visible == True:
                    continue
                page.loadingContainer.visible = True
                if page.connected:
                    page.update()


    def closeOthersLoadingContainer(self: ZhiXueFlet) -> None:
        global showLoadingContainer
        showLoadingContainer = False
        for page in pageList:
            if page.loadingContainer.visible == False:
                continue
            page.loadingContainer.visible = False
            if page.connected:
                page.update()


    def changeOthersLoadingContainer(self: ZhiXueFlet, text: str) -> None:
        global showLoadingContainer
        showLoadingContainer = True
        for page in pageList:
            if page != self:
                page.loadingContainer.visible = True
                page.loadingText.value = text
                if page.connected:
                    page.update()


    def _setFrequency(self: ZhiXueFlet, actionName: str) -> None:
        MAX_ACTION_NUM = FREQUENCY_DATA[actionName]["MAX_ACTION_NUM"]
        self.frequency[actionName]
        self.frequency[actionName].append(time.time())
        self.frequency[actionName] = self.frequency[actionName][-MAX_ACTION_NUM:]
        with open("./data/frequency.json", "w", encoding = "utf-8") as file:
            json.dump(frequencyDict, file, indent = 4, ensure_ascii = False)


    def checkFrequency(self: ZhiXueFlet, actionName: str) -> Union[int, float]:
        with frequencySetLock:
            INTERVAL: int = FREQUENCY_DATA[actionName]["INTERVAL"]
            MAX_ACTION_NUM: int = FREQUENCY_DATA[actionName]["MAX_ACTION_NUM"]
            if len(self.frequency[actionName]) < MAX_ACTION_NUM:
                self._setFrequency(actionName)
                timeNeedToWait = 0
            else:
                intervalCurrent = time.time() -(self.frequency[actionName][-MAX_ACTION_NUM])
                if intervalCurrent >= INTERVAL:
                    self._setFrequency(actionName)
                    timeNeedToWait = 0
                else:
                    timeNeedToWait = INTERVAL -intervalCurrent
        return timeNeedToWait


    def clear(self: ZhiXueFlet) -> None:
        del self.dialogCloseButton, self.dialogContainer, self.dialog, self.naviRail, self.naviBar, \
            self.examList, self.examDetailTitle, self.examDetailLoadingText, self.examDetailTotalScoreRow, self.examDetailSubjectScoreRow, \
            self.examDetailBackButton, self.examDetailSwitchScoreRankButton, self.examDetail, self.pageMainTitle, self.pageMainFormat, \
            self.zhixueAccountTextField, self.zhixuePasswordTextField, self.userInfoText, self.loginButton, self.QQchannelButton, self.logoutButton, \
            self.pageAccountUnloginFormat, self.pageAccountFormat, self.pageWindowSizeIllegleFormat, self.format,
            # self.banner, self.bannerColumn, self.bannerText
        del self.zhixue


    def __initControl__(self: ZhiXueFlet) -> None:
        self.bannerText = flet.Text("", font_family = "FiraCodeMedium", color = flet.colors.ERROR, selectable = True)
        self.bannerColumn = flet.Column(
            spacing = 0,
            height = 22,
            scroll = flet.ScrollMode.AUTO,
            controls = [
                self.bannerText
            ],
        )
        self.banner = flet.Banner(
            bgcolor = flet.colors.ERROR_CONTAINER,
            leading = flet.Icon(flet.icons.WARNING_AMBER_ROUNDED, color = flet.colors.ERROR, size = 40),
            content = self.bannerColumn,
            actions = [
                flet.TextButton("关闭", on_click = self.closeBanner),
            ],
        )

        self.delayText = flet.Text(
            right = 10, bottom = 10,
            value = "-- ms", size = 10, color = flet.colors.GREY_500
        )

        self.loadingText = flet.Text("加载中...", size = 16, expand = True, text_align = flet.TextAlign.CENTER)
        self.loadingContainer = flet.Container(
            expand = True, bgcolor = flet.colors.BACKGROUND,
            alignment = flet.alignment.center,
            padding = 0, margin = 0,
            content = self.loadingText
        )
        self.loadingContainer.visible = False

        self.dialogCloseButton = flet.IconButton(
            icon = flet.icons.CLOSE,
            on_click = self.closeDialog,
        )
        self.dialogContainer = flet.Container(
            bgcolor = flet.colors.BACKGROUND,
            alignment = flet.alignment.center,
            padding = 0, margin = 0,
        )
        self.dialog = flet.AlertDialog(
            open = False, modal = True,
            title_padding = 0, content_padding = 0, actions_padding = 0,
            on_dismiss = self.closeDialog,
            content = flet.Stack(
                controls = [
                    self.dialogContainer,
                    flet.Row(
                        alignment = flet.MainAxisAlignment.END,
                        controls = [
                            self.dialogCloseButton
                        ]
                    )
                ]
            )
        )

        self.naviRail = flet.NavigationRail(
            visible = False,
            selected_index = 1,
            label_type = flet.NavigationRailLabelType.ALL,
            height = 200, width = 76,
            min_width = 76,
            group_alignment = -0.9,
            on_change = lambda event: self.changeRail(event.control.destinations[event.control.selected_index].label_content.value, event),
            destinations = [
                flet.NavigationRailDestination(
                    label_content = flet.Text("主页", font_family = "MCGNU"),
                    icon = flet.icons.HOUSE_OUTLINED,
                    selected_icon = flet.icons.HOUSE
                ),
                flet.NavigationRailDestination(
                    label_content = flet.Text("好友", font_family = "MCGNU"),
                    icon = flet.icons.COMMENT_OUTLINED,
                    selected_icon = flet.icons.COMMENT
                ),
                flet.NavigationRailDestination(
                    label_content = flet.Text("账号", font_family = "MCGNU"),
                    icon = flet.icons.ACCOUNT_CIRCLE_OUTLINED,
                    selected_icon = flet.icons.ACCOUNT_CIRCLE
                ),
            ]
        )

        self.naviBar = flet.NavigationBar(
            visible = False,
            on_change = lambda event: self.changeRail(event.control.destinations[event.control.selected_index].label, event),
            destinations = [
                flet.NavigationDestination(
                    label = "主页",
                    icon = flet.icons.HOUSE_OUTLINED,
                    selected_icon = flet.icons.HOUSE
                ),
                flet.NavigationDestination(
                    label = "好友",
                    icon = flet.icons.COMMENT_OUTLINED,
                    selected_icon = flet.icons.COMMENT
                ),
                flet.NavigationDestination(
                    label = "账号",
                    icon = flet.icons.ACCOUNT_CIRCLE_OUTLINED,
                    selected_icon = flet.icons.ACCOUNT_CIRCLE
                ),
            ],
        )

        self.examList = flet.ListView(
            height = 100,
            divider_thickness = 0,
            data = "考试列表",
            controls = []
        )
        self.examDetailTitle = flet.Text("", offset = flet.Offset(0, 0.15), font_family = "MCGNU", size = 24, text_align = flet.TextAlign.CENTER, max_lines = 1, overflow = flet.TextOverflow.ELLIPSIS,)
        self.examDetailLoadingText = flet.Text("", font_family = "MCGNU", size = 32, text_align = flet.TextAlign.CENTER)
        self.examDetailTotalScoreRow = flet.ResponsiveRow(spacing = 6, run_spacing = 6)
        self.examDetailSubjectScoreRow = flet.ResponsiveRow(spacing = 6, run_spacing = 6)
        self.examDetailReportUpdateTimeText = flet.Text()
        self.examDetailBackButton = flet.IconButton(
            icon = flet.icons.ARROW_BACK,
            on_click = lambda event: self.changeSubPage("主页", "考试列表"),
        )
        self.examDetailSwitchScoreRankButton = flet.IconButton(
            right = 0,
            icon = flet.icons.SWITCH_LEFT,
            on_click = self.examDetailSwitchScoreRank,
        )
        self.examDetail = flet.Column(
            height = 100, spacing = 0,
            scroll = flet.ScrollMode.AUTO,
            data = "考试详情",
            controls = [
                flet.Stack(
                    controls = [
                        flet.Row(
                            alignment = flet.MainAxisAlignment.CENTER,
                            controls = [
                                self.examDetailTitle,
                            ]
                        ),
                        flet.Row(
                            alignment = flet.MainAxisAlignment.CENTER,
                            controls = [
                                self.examDetailLoadingText,
                            ]
                        ),
                        self.examDetailSwitchScoreRankButton,
                        self.examDetailBackButton
                    ]
                ),
                self.examDetailTotalScoreRow,
                flet.Row(height = 8),
                self.examDetailSubjectScoreRow,
                flet.Row(height = 8),
                self.examDetailReportUpdateTimeText,
            ]
        )
        self.pageMainTitle = flet.Text("ZhiXueFlet", font_family = "MCGNU", size = 32)

        self.pageMainFormat: flet.Column = flet.Column(
            expand = 90, spacing = 0,
            data = "主页",
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.pageMainTitle,
                    ]
                ),
                self.examList
            ]
        )

        self.zhixueAccountTextField = flet.TextField(width = 300, hint_text = "账号", label = "账号", on_submit = lambda _: self.zhixuePasswordTextField.focus(), focused_border_color = flet.colors.PRIMARY)
        self.zhixuePasswordTextField = flet.TextField(width = 300, hint_text = "密码", label = "密码", password = True, on_submit = self.ZhiXueLogin, focused_border_color = flet.colors.PRIMARY)
        self.userInfoText = flet.Text("", font_family = "MCGNU")
        self.loginButton = flet.ElevatedButton(
            width = 200,
            text = "登录",
            on_click = self.ZhiXueLogin,
            style = flet.ButtonStyle(
                shape = flet.RoundedRectangleBorder(radius = 2),
            ),
        )
        self.removeClientStorageButton = flet.ElevatedButton(
            width = 200,
            text = "清除缓存",
            on_click = self.removeClientStorage,
            style = flet.ButtonStyle(
                shape = flet.RoundedRectangleBorder(radius = 2),
            ),
        )
        self.QQchannelButton = flet.ElevatedButton(
            width = 200,
            text = "加入 QQ 频道",
            on_click = self.launchQQchannel,
            style = flet.ButtonStyle(
                shape = flet.RoundedRectangleBorder(radius = 2),
            ),
        )
        self.logoutButton = flet.ElevatedButton(
            width = 200,
            text = "登出",
            on_click = self.ZhiXueLogout,
            style = flet.ButtonStyle(
                shape = flet.RoundedRectangleBorder(radius = 2),
            ),
        )
        self.logoutRemoveCScheckbox = flet.Checkbox(
            width = 160,
            label = "退出时清除缓存",
            value = False,
        )
        self.pageAccountUnloginFormat = flet.Column(
            expand = 90, spacing = 0,
            data = "账号",
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text("智学网登录", font_family = "MCGNU", size = 32)
                    ]
                ),
                flet.Row(height = 10),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.zhixueAccountTextField
                    ]
                ),
                flet.Row(height = 10),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.zhixuePasswordTextField
                    ]
                ),
                flet.Row(height = 4),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        # flet.Text("点击登录按钮就表示你详细阅读过并同意频道中的总公告\n2024-05-25 说明:\n    智学网关闭旧登录方式,\n    现在需要用 ZXF FakeStudent 勉强进去..\n    让 5573 手动放一些信息在网页,\n    大概一次能让整个 ZXF (对所有学生) 持续可用半小时", font_family = "MCGNU", size = 12),
                        # flet.Text("2024-12-14 说明:\n    由于学校以及某些相关原因, ZXF 停止服务.\n    (抱歉捏..)", font_family = "MCGNU", size = 12),
                        flet.Text("2025-02-21 说明:\n    输完密码时按 ENTER 可以登录啦.\n    哼哼..", font_family = "MCGNU", size = 12),
                    ]
                ),
                flet.Row(height = 4),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.loginButton
                    ]
                ),
                flet.Row(height = 4),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.removeClientStorageButton
                    ]
                )
            ]
        )
        self.pageAccountFormat = flet.Column(
            expand = 90,
            data = "账号",
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text("账号信息", font_family = "MCGNU", size = 32)
                    ]
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.START,
                    controls = [
                        self.userInfoText
                    ]
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.START,
                    controls = [
                        flet.Text("\nTip 1:\n    在加载 ZXF /刷新页面时, 点一下进度条上方的图片, 可以全屏网页w\n    手机横屏使用非常方便的~, 不会再被地址栏占用空间.\n\nTip 2:\n    附中校园网可在 http://124.222.154.164/ 访问网页.\n    (教室黑板, 老师电脑等等)\n    而在校外应该用 https://www.zhixueflet.site/", weight = flet.FontWeight.W_600)
                    ]
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.logoutButton
                    ]
                ),
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        self.logoutRemoveCScheckbox
                    ]
                ),
            ]
        )

        self.windowSizeIllegleText = flet.Text("", font_family = "MCGNU", size = 16, expand = True, text_align = flet.TextAlign.CENTER)
        self.pageWindowSizeIllegleFormat = flet.Column(
            expand = 90,
            data = "窗口过",
            alignment = flet.MainAxisAlignment.CENTER,
            controls = [
                flet.Container(
                    alignment = flet.alignment.center,
                    expand = True,
                    content = self.windowSizeIllegleText
                )
            ]
        )
        self.chatListTitle = flet.Stack(
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [flet.Text(f"", offset = flet.Offset(0, 0.1), font_family = "MCGNU", size = 24, text_align = flet.TextAlign.CENTER)]
                )
            ]
        )
        self.chatList = flet.Column(
            expand = 18, scroll = flet.ScrollMode.AUTO,
            height = 200, spacing = 0
        )
        self.chatDetailTextField = flet.TextField(
            expand = True, border = flet.InputBorder.UNDERLINE, offset = flet.Offset(0.01, -0.05),
            multiline = True, min_lines = 1, max_lines = 5, max_length = 2048,
            filled = False, hint_text = "消息..", label = ""
        )
        self.chatDetailSendMsgButton = flet.IconButton(
            icon = flet.icons.SEND, offset = flet.Offset(0.2, 0),
            tooltip = "发送",
            on_click = self.sendMsg,
        )
        self.chatDetailCloseButton = flet.IconButton(
            icon = flet.icons.CLOSE,
            on_click = self.closeChatDetail,
        )
        self.chatDetail = flet.Column(
            expand = 82, scroll = flet.ScrollMode.AUTO,
            height = 200, spacing = 0,
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    vertical_alignment = flet.CrossAxisAlignment.START,
                    spacing = 0, data = 55730000,
                    controls = [
                        self.chatDetailCloseButton,
                        self.chatDetailTextField,
                        self.chatDetailSendMsgButton,
                    ]
                )
            ]
        )
        self.chatList.controls.append(self.chatListTitle)
        self.pageFriendFormat = flet.Row(
            expand = 120, spacing = 8,
            vertical_alignment = flet.CrossAxisAlignment.START,
            data = "聊天列表",
            controls = [
                self.chatList,
                self.chatDetail
            ]
        )

        self.format = flet.Row(
            vertical_alignment = flet.CrossAxisAlignment.START,
            alignment = flet.MainAxisAlignment.CENTER,
            controls = [
                self.banner,
                self.naviRail,
                flet.Column(expand = 0),
                self.pageAccountUnloginFormat,
                flet.Column(expand = 0),
                flet.Column(width = 0)
            ]
        )


    def closeBanner(self: ZhiXueFlet, *args) -> None:
        # self.bannerText.value = ""
        self.bannerColumn.height = 0
        self.banner.open = False
        self.update()


    def closeDialog(self: ZhiXueFlet, *args) -> None:
        self.dialogCloseButton.disabled = False
        self.dialog.open = False
        self.onResize()
        self.update()


    def showExcOnBanner(self: ZhiXueFlet, excInfoRich: str, excInfo: str) -> None:
        text = excInfo +"\n" + excInfoRich
        if text.endswith("\n"):
            text = text[:-1]
        text = f"啊.. 这里有一些错误..\n怎会这 (抱歉.jpg)\n{text}"
        if self.banner.open and (text == self.bannerText.value):
            self.closeBanner()
            time.sleep(0.1)
        height = 22 *(0 +len(text.splitlines()))
        if self.page.width <= WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN:
            height += 22
        if height > self.page.height:
            height = self.page.height
        self.bannerText.value = text
        self.bannerColumn.height = height
        self.banner.open = True
        self.update()


    @showExc(funcOnExc = showExcOnBanner)
    def raiseException(self: ZhiXueFlet, excType: type[BaseException] = ZhiXueFletException, excInfo: str = "一个普通的异常."):
        # exec("from __future__ import braces")
        raise excType(excInfo)


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.removeClientStorageButton.disabled = False"])
    def removeClientStorage(self: ZhiXueFlet, *_, **__) -> None:
        with self.actionLock:
            self.removeClientStorageButton.disabled = True
            self.removeClientStorageButton.text = "清除中..."
            self.zhixueAccountTextField.value = ""
            self.zhixuePasswordTextField.value = ""
            self.page.update()
            for key in self.page.client_storage.get_keys("ZhiXueFlet_"):
                self.page.client_storage.remove(key)
            self.removeClientStorageButton.text = "清除成功!"
            self.page.update()
            time.sleep(1)
            self.removeClientStorageButton.disabled = False
            self.removeClientStorageButton.text = "清除缓存"


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.QQchannelButton.disabled = False"])
    def launchQQchannel(self: ZhiXueFlet, _) -> None:
        self.QQchannelButton.disabled = True
        self.page.set_clipboard("https://pd.qq.com/s/ew3vshh9h")
        self.page.launch_url("https://pd.qq.com/s/ew3vshh9h")


    @showExc(funcOnExc = showExcOnBanner)
    def getCurrentSubPage(self: ZhiXueFlet, pageName: Union[None, str] = None) -> str:
        if pageName == "主页":
            return self.pageMainFormat.controls[1].data
        if pageName == "社交":
            return self.pageFriendFormat.data
        raise ZhiXueFletException(f"获取页面的当前子页面异常: 未找到 {pageName} 页面.")


    @showExc(funcOnExc = showExcOnBanner)
    def getCurrentRail(self: ZhiXueFlet) -> str:
        return self.format.controls[3].data


    @showExc(funcOnExc = showExcOnBanner)
    def changeRail(self: ZhiXueFlet, railName: Optional[str] = None, event: Optional[Any] = None) -> None:
        if self.naviRail.destinations is None:
            raise ZhiXueFletException("切换页面异常: 导航栏为空.")
        for railDestinationIndex, railDestination in enumerate(self.naviRail.destinations):
            if not isinstance(railDestination.label_content, flet.Text):
                raise ZhiXueFletException("切换页面异常: 导航栏标签不是 Flet.Text 类型.")
            if railName == railDestination.label_content.value:
                self.naviRail.selected_index = railDestinationIndex
                self.naviBar.selected_index = railDestinationIndex
            if railName is None:
                # return
                if self.naviRail.selected_index == railDestinationIndex:
                    railName = railDestination.label_content.value
        assert railName is not None
        if railName == "主页":
            self.format.controls[3] = self.pageMainFormat
            if self.getCurrentSubPage("主页") == "考试列表" and event:
                self.refreshExamList()
        if railName == "好友":
            if self.socialusr is not None:
                # if self.socialusr.get_nickname() != "51497882":
                #     raise SocialError
                self.format.controls[3] = self.pageFriendFormat
                self.refreshChatList(event)
        if railName == "账号":
            if self.zhixue is not None:
                self.format.controls[3] = self.pageAccountFormat
            else:
                self.format.controls[3] = self.pageAccountUnloginFormat
                try:
                    there_is_userID_and_password_in_client_stroage = all(self.page.client_storage.contains_key(f"ZhiXueFlet_{key}") for key in ["zhixueAccount", "zhixuePassword"])
                    if there_is_userID_and_password_in_client_stroage:
                        self.zhixueAccountTextField.value = self.page.client_storage.get("ZhiXueFlet_zhixueAccount")
                        self.zhixuePasswordTextField.value = self.page.client_storage.get("ZhiXueFlet_zhixuePassword")
                except TimeoutError as exc:
                    print(exc)
        if railName == "窗口过窄":
            self.windowSizeIllegleText.value = f"窗口过窄, 请尝试增宽窗口至 {WINDOW_WIDTH_PIXEL_MIN}px 及以上.\n当前宽度: {self.page.width}px."
            self.format.controls[3] = self.pageWindowSizeIllegleFormat
        if railName == "窗口过宽":
            self.windowSizeIllegleText.value = f"窗口过宽, 请尝试缩减窗口至 {WINDOW_WIDTH_PIXEL_MAX}px 及以下.\n当前宽度: {self.page.width}px."
            self.format.controls[3] = self.pageWindowSizeIllegleFormat
        if railName == "窗口过矮":
            self.windowSizeIllegleText.value = f"窗口过矮, 请尝试增高窗口至 {WINDOW_HEIGHT_PIXEL_MIN}px 及以上.\n当前高度: {self.page.height}px."
            self.format.controls[3] = self.pageWindowSizeIllegleFormat


    @showExc(funcOnExc = showExcOnBanner)
    def changeSubPage(self: ZhiXueFlet, pageName: Union[None, str] = None, subPageName: Union[None, str] = None) -> None:
        if pageName == "主页":
            if subPageName == "考试列表":
                if self.getCurrentSubPage(pageName) == "考试详情":
                    self.examDetailTotalScoreRow.controls.clear()
                    self.examDetailSubjectScoreRow.controls.clear()
                    self.update()
                self.pageMainFormat.controls[1] = self.examList
                self.pageMainTitle.value = "成绩查询"
                self.pageMainTitle.visible = True
            if subPageName == "考试详情":
                self.pageMainFormat.controls[1] = self.examDetail
                self.pageMainTitle.value = "考试详情"
                self.pageMainTitle.visible = False
        if pageName == "账号":
            pass
        self.changeRail(pageName)


    @showExc(funcOnExc = showExcOnBanner)
    def onResize(self: ZhiXueFlet, event = None) -> None:
        if self.page.width < WINDOW_WIDTH_PIXEL_MIN:
            self.naviRail.visible = False
            self.naviBar.visible = False
            bottomHeight = 0
            self.format.controls[2].visible = False
            self.format.controls[4].visible = False
            self.changeRail("窗口过窄")
        elif self.page.width > WINDOW_WIDTH_PIXEL_MAX:
            self.naviRail.visible = False
            self.naviBar.visible = False
            bottomHeight = 0
            self.format.controls[2].visible = False
            self.format.controls[4].visible = False
            self.changeRail("窗口过宽")
        elif self.page.height < WINDOW_HEIGHT_PIXEL_MIN:
            self.naviRail.visible = False
            self.naviBar.visible = False
            bottomHeight = 0
            self.format.controls[2].visible = False
            self.format.controls[4].visible = False
            self.changeRail("窗口过矮")
        elif WINDOW_WIDTH_PIXEL_MIN <= self.page.width < WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN:
            self.naviBar.visible = True if (self.zhixue is not None) else False
            self.naviRail.visible = False if (self.zhixue is not None) else False
            self.format.controls[2].visible = False if (self.zhixue is not None) else False
            self.format.controls[4].visible = False if (self.zhixue is not None) else False
            bottomHeight = 80
            self.examDetailTitle.width = self.page.width -150
            if self.getCurrentRail().startswith("窗口过"):
                self.changeRail()
        elif WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN <= self.page.width <= WINDOW_WIDTH_PIXEL_MAX:
            self.naviBar.visible = False if (self.zhixue is not None) else False
            self.naviRail.visible = True if (self.zhixue is not None) else False
            self.format.controls[2].visible = True if (self.zhixue is not None) else False
            self.format.controls[4].visible = True if (self.zhixue is not None) else False
            bottomHeight = 0
            self.examDetailTitle.width = (self.page.width -100) *0.9 -150
            if self.getCurrentRail().startswith("窗口过"):
                self.changeRail()
        else:
            raise ZhiXueFletException("处理窗口大小变化事件异常: 出现例外情况.")
        if WINDOW_WIDTH_PIXEL_MIN <= self.page.width < WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN +120:
            self.chatDetailCloseButton.visible = True
            if self.getCurrentSubPage("社交") == "聊天列表":
                self.chatList.visible = True
                self.chatDetail.visible = False
            else:
                self.chatList.visible = False
                self.chatDetail.visible = True
        elif WINDOW_WIDTH_PIXEL_SHOW_NAVIBAR_MIN +120 <= self.page.width <= WINDOW_WIDTH_PIXEL_MAX:
            self.chatDetail.visible = True
            self.chatList.visible = True
            self.chatDetailCloseButton.visible = False
            if self.page.width <= 1000:
                self.chatList.expand = 22
                self.chatDetail.expand = 78
            elif self.page.width <= 1200:
                self.chatList.expand = 20
                self.chatDetail.expand = 80
            elif self.page.width <= 1400:
                self.chatList.expand = 18
                self.chatDetail.expand = 82
            else:
                self.chatList.expand = 16
                self.chatDetail.expand = 84
        if self.zhixue is None:
            bottomHeight = 0
        self.dialogContainer.width = self.page.width //2
        self.dialogContainer.height = self.page.height //2
        self.dialogContainer.width = max(560, min(self.dialogContainer.width, 800))
        self.dialogContainer.height = max(400, min(self.dialogContainer.height, 600))
        self.examList.height = self.page.height -50 -bottomHeight
        self.examDetail.height = self.page.height -4 -bottomHeight
        self.chatDetail.height = self.page.height -8 -bottomHeight
        self.chatList.height = self.page.height -8 -bottomHeight
        self.pageWindowSizeIllegleFormat.height = self.page.height -4 -bottomHeight


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.loginButton.disabled = False"])
    def ZhiXueLogin(self: ZhiXueFlet, _) -> None:
        self.loginButton.disabled = True
        account, password = self.zhixueAccountTextField.value, self.zhixuePasswordTextField.value
        account = account or ""
        password = password or ""
        print("登录按钮被点击:", account)
        if account == password == "重启":
            restart_too_frequently = self.checkFrequency("restart")
            if restart_too_frequently:
                self.loginButton.text = f"重启过于频繁, \n请 {restart_too_frequently:.2f}s 后再试."
                return
            self.loginButton.text = "检测网页是否卡死..."
            self.update()
            time.sleep(0.5773)
            frequencySetLock.acquire()
            if all(lock.acquire(timeout = 5.773) for lock in ZhiXueLockList):
                self.zhixueAccountTextField.error_text = "网页未卡死, 不要随便用啊啊啊.."
                self.zhixuePasswordTextField.error_text = "网页未卡死, 不要随便用啊啊啊.."
                self.loginButton.text = "登录"
                self.update()
                frequencySetLock.release()
                [lock.release() for lock in ZhiXueLockList]
                time.sleep(0.5773)
            else:
                self.zhixueAccountTextField.error_text = "网页真的有卡死.. 重启ing"
                self.zhixuePasswordTextField.error_text = "网页真的有卡死.. 重启ing"
                self.loginButton.text = "网页真的有卡死.. 重启ing"
                self.update()
                time.sleep(1.5773)
                os._exit(1)
            return
        account_is_empty = not account
        account_is_too_short = (len(account) < 6)
        account_is_too_long = (len(account) > 24)
        account_is_userAccount = (account.isdigit() is False) or (len(account) != 19)
        account_contain_illegal_character = any((char not in LEGAL_ASCII_CHARACTER) for char in account)
        password_is_empty = not password
        password_is_too_short = (len(password) < 6)
        password_is_too_long = (len(password) > 24)
        password_is_same_as_userAccount = account_is_userAccount and (account == password)
        password_is_default = account_is_userAccount and (password == "111111")
        login_is_nopwd_student = f"{account}_{password}" in featureWhitelist.get("noPwdStudent", {}).keys()
        can_not_login = (account_is_empty or account_is_too_short or password_is_empty or password_is_too_short or account_is_too_long or password_is_too_long or password_is_same_as_userAccount or password_is_default or account_contain_illegal_character) and ((not login_is_nopwd_student))
        self.zhixueAccountTextField.error_text = ""
        self.zhixuePasswordTextField.error_text = ""
        self.loginButton.text = "登录"
        if can_not_login:
            if account_is_empty:
                self.zhixueAccountTextField.error_text = "请输入账号."
            elif account_is_too_short:
                self.zhixueAccountTextField.error_text = "账号过短."
            elif account_is_too_long:
                self.zhixueAccountTextField.error_text = "账号过长."
            elif account_contain_illegal_character:
                self.zhixueAccountTextField.error_text = "账号包含非法字符."
            if password_is_empty:
                self.zhixuePasswordTextField.error_text = "请输入密码."
            elif password_is_too_short:
                self.zhixuePasswordTextField.error_text = "密码过短."
            elif password_is_too_long:
                self.zhixuePasswordTextField.error_text = "密码过长."
            elif password_is_same_as_userAccount:
                self.zhixuePasswordTextField.error_text = "密码不能和账号相同, \n请先在智学网修改密码."
            elif password_is_default:
                self.zhixuePasswordTextField.error_text = "密码不能是初始密码, \n请先在智学网修改密码."
            return

        lockedNum = 0
        for lock in ZhiXueLockList:
            if type(lock) == threading.Lock: lockedNum += lock.locked()
            else:
                locked = not lock.acquire(timeout = 0.0001)
                if not locked: lock.release()
                lockedNum += locked
        if lockedNum:
            self.zhixueAccountTextField.error_text = "为防死锁, 此时不能登录.\n请等数秒再尝试."
            self.zhixuePasswordTextField.error_text = "在账号和密码都输入 重启 二字,\n再点登录, 可强制重启网页."
            return

        login_too_frequently = self.checkFrequency("login")
        if login_too_frequently:
            self.loginButton.text = f"登录不能这么频繁哦, \n请 {login_too_frequently:.2f}s 后再试."
            return

        with self.actionLock:
            self.loginButton.text = "登录中.."
            self.update()
            try:
                if login_is_nopwd_student:
                    print("使用 NoPwdStudent", account)
                    userID, userAccount, usesrName, studentCode, studentClassID, userSchoolID, stageName, enrollYear = featureWhitelist["noPwdStudent"][f"{account}_{password}"].split("_")
                    zhixue = ZhiXueNoPwdStudent(userID, userAccount, usesrName, studentCode, studentClassID, userSchoolID, stageName, int(enrollYear))
                else:
                    if account_is_userAccount:
                        userAccount = account
                        # userID = ZhiXue.getUserIDbyAccountPassword(userAccount, password)
                    else:
                        raise NotImplementedError
                    del account
                    if (userAccount[:2] not in ["43", "51"]) and (userAccount not in ["53801193"]):
                        raise NotImplementedError("异常发生.")
                    zhixue = ZhiXue(userAccount, password)
                self.zhixue_is_nopwd_student = login_is_nopwd_student
            except (ZhiXueError, ZhiXueException) as exc:
                excInfo = str(exc)
                self.loginButton.text = excInfo
                if "用户不存在" in excInfo:
                    self.zhixueAccountTextField.error_text = excInfo
                if "您提供的凭证有误" in excInfo:
                    self.zhixuePasswordTextField.error_text = excInfo
                if "账号或密码错误" in excInfo:
                    self.zhixueAccountTextField.error_text = excInfo
                    self.zhixuePasswordTextField.error_text = excInfo
                return

            if "student" not in zhixue.userRoleList:
                self.zhixueAccountTextField.error_text = "请使用学生账号登录."
                self.loginButton.text = "请使用学生账号登录."
                return

            # if account_is_fake_student:
            #     account_in_white_list = any(account_white.startswith("_".join(account.split("_", 7)[:-1])) for account_white in whiteList["fakestudent"])
            # else:
            account_in_white_list = ("everyone" in whiteList["userIDlist"]) \
                                or (zhixue.userID in whiteList["userIDlist"]) \
                                or (zhixue.userAccount in whiteList["userIDlist"]) or (zhixue.studentCode in whiteList["userIDlist"]) \
                                or (zhixue.studentClassID in whiteList["classIDlist"]) or (zhixue.userSchoolID in whiteList["schoolIDlist"]) \
                                or (login_is_nopwd_student) \
                                or (userAccount == "4351497882")

            if not account_in_white_list:
                if zhixue.userSchoolID == "2300000001000049726":
                    self.zhixueAccountTextField.error_text = "账号不在白名单中, 请在 G2218 班联系作者."
                    self.zhixuePasswordTextField.error_text = "QwQ"
                    # self.loginButton.text = "加载白名单配置文件异常: 格式错误."
                    # raise ZhiXueFletException("加载白名单配置文件异常: 格式错误.")
                else:
                    self.zhixueAccountTextField.error_text = "账号不在白名单中, 请在频道联系作者.\n一个悲伤的消息:\n    不可抗事件发生,\n    ZhiXueFlet 于 2024-04-11 终止服务..."
                    self.zhixuePasswordTextField.error_text = "大家, 再见啦. \n真的非常感谢你们一直以来的支持与陪伴,\n这是一段很好很独特的经历.\n \n                            5573\n                            2023-03 ~ 2024-04"
                    self.loginButton.text = "账号不在白名单中,\n请在频道联系作者."
                return
            self.can_view_marking_teacher = zhixue.studentCode in featureWhitelist.get("markingTeacher", [])
            self.can_view_marking_teacher = self.can_view_marking_teacher or (zhixue.userSchoolID == "1500000100044990927")
            self.loginButton.text = "登录成功!"
            try:
                self.page.client_storage.set("ZhiXueFlet_zhixueAccount", (userAccount if (not login_is_nopwd_student) else account))
                self.page.client_storage.set("ZhiXueFlet_zhixuePassword", password)
            except TimeoutError as exc:
                print(exc)
            self.loginButton.text = "登录"
            self.userInfoText.value = \
                f"姓名: {zhixue.userName}\n" \
                f"学校: {zhixue.userSchoolName}\n" \
                f"班级: {zhixue.studentClassName}\n\n" \
                f"附加功能可用情况:\n" \
                f"    看阅卷老师: {'可用' if self.can_view_marking_teacher else '不在白名单'}"
            self.zhixue = zhixue
            self.socialusr = User(zhixue.userID).save_data("realname", zhixue.userName).save_data("nickname", zhixue.studentCode)
            if self.socialusr.ID not in sysgrp.member:
                sysgrp.add_member(self.socialusr.ID)
            self.onResize()
            self.changeSubPage("主页", "考试列表")
        self.refreshExamList()


    @showExc(funcOnExc = showExcOnBanner)
    def ZhiXueLogout(self: ZhiXueFlet, event = None) -> None:
        with self.actionLock:
            self.zhixue = None
            self.socialusr = None
            self.chatDetail.data = None
            self.chatList.controls.clear()
            self.chatList.controls.append(self.chatListTitle)
            self.chatDetail.controls = [self.chatDetail.controls.pop(0)]
            self.pageFriendFormat.data = "聊天列表"
            self.zhixue_is_nopwd_student = None
            self.can_view_marking_teacher = False
            self.examList.controls.clear()
            self.changeSubPage("账号", "未登录")
            self.onResize()
        if self.logoutRemoveCScheckbox.value:
            self.removeClientStorage()


    @showExc(funcOnExc = showExcOnBanner)
    def refreshChatList(self: ZhiXueFlet, event = None) -> None:
        if self.socialusr is None:
            raise ZhiXueFletException("刷新聊天列表异常: 用户未登录社交账号.")
        if event:
            if (action_too_frequently := self.checkFrequency("refreshSocialList")):
                return
                raise ZhiXueFletError(f"切换页面太快..")
        with self.actionLock:
            self.chatListTitle.controls[0].controls[0].value = self.socialusr.get_nickname()
            borded_ID = -1
            for control in self.chatList.controls:
                if not isinstance(control, flet.Container):
                    continue
                if control.border is not None:
                    if control.border.top is not None:
                        if control.border.top.color:
                            if control.border.top.color == flet.colors.PRIMARY_CONTAINER:
                                borded_ID = control.data
                                break
            self.chatList.controls.clear()
            self.chatList.controls.append(self.chatListTitle)
            self.chatList.controls.append(
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text("获取社交列表...", size = 16)
                    ]
                )
            )
            if event:
                self.update()
            self.chatList.controls.pop()
            for connID, data in self.socialusr.get_social().items():
                conn = Conn(connID)
                dispname = data["name"]
                latest_msg = self.socialusr.load_msg(connID, conn.msgnum -1, conn.msgnum -1)[-1]
                if (conn.type == "group") and (latest_msg[2] != "system"):
                    latest_msg = "%s: %s" % (User(latest_msg[2]).get_realname(), latest_msg[3])
                else:
                    latest_msg = latest_msg[3]
                self.chatList.controls.append(
                    flet.Container(
                        padding = 0, data = connID, border = flet.Border(*((flet.BorderSide(2, flet.colors.PRIMARY_CONTAINER +",0"), ) *4)) if (connID != borded_ID) else flet.Border(*((flet.BorderSide(2, flet.colors.PRIMARY_CONTAINER), ) *4)),
                        on_click = self.refreshChatDetail,
                        ink = True,
                        content = flet.Column(
                            controls = [
                                flet.ListTile(
                                    leading = {
                                        "group": flet.Icon(flet.icons.GROUP),
                                        "friend": flet.Icon(flet.icons.PERSON)
                                    }[conn.type],
                                    title = flet.Text(dispname, overflow = flet.TextOverflow.ELLIPSIS),
                                    subtitle = flet.Text(latest_msg, opacity = 0.6, max_lines = 1, overflow = flet.TextOverflow.ELLIPSIS),
                                    # on_click = lambda _: _,
                                )
                            ]
                        )
                    )
                )
            self.update()


    @showExc(funcOnExc = showExcOnBanner)
    def refreshChatDetail(self: ZhiXueFlet, event: flet.ControlEvent) -> None:
        if self.socialusr is None:
            raise ZhiXueFletException("构建聊天详情页面异常: 用户未登录社交账号.")
        action_too_frequently = self.checkFrequency("refreshChatDetail")
        if action_too_frequently:
            return
            raise ZhiXueFletError(f"查看过于频繁啦, 再等等 {action_too_frequently:.2f}s 哦.")
        with self.actionLock:
            connID: int = event.control.data
            conn = Conn(connID)
            for control in self.chatList.controls:
                if not isinstance(control, flet.Container):
                    continue
                if control == event.control:
                    control.border = flet.Border(*((flet.BorderSide(2, flet.colors.PRIMARY_CONTAINER), ) *4))
                else:
                    control.border = flet.Border(*((flet.BorderSide(2, flet.colors.PRIMARY_CONTAINER +",0"), ) *4))
            self.chatDetail.data = connID
            self.chatDetail.controls = [self.chatDetail.controls.pop(0)]
            self.update()
            self.loadMsg(conn.msgnum -200, conn.msgnum -1)
            self.pageFriendFormat.data = "聊天详情"
            self.onResize()


    @showExc(funcOnExc = showExcOnBanner)
    def sendMsg(self: ZhiXueFlet, event) -> None:
        assert self.socialusr is not None
        msg = str(self.chatDetailTextField.value)
        if not msg:
            self.chatDetailTextField.error_text = "无法发送空消息."
            return
        else:
            self.chatDetailTextField.error_text = ""
        connID = self.chatDetail.data
        conn = Conn(connID)
        self.socialusr.record_msg(connID, msg)
        self.page.pubsub.send_others_on_topic("social_msg", (self.socialusr.ID, connID, conn.msgnum -1))
        self.chatDetailTextField.value = ""
        self.loadMsg(conn.msgnum -1, conn.msgnum -1)
        self.refreshChatList()


    def onMsgRecv(self: ZhiXueFlet, topic, msg):
        if self.socialusr is None:
            return
        sender, connID, msgIndex = msg
        if connID == self.chatDetail.data:
            self.loadMsg(msgIndex, msgIndex)
            self.refreshChatList()
        else:
            connIDlist = self.socialusr.get_social().keys()
            if connID in connIDlist:
                self.refreshChatList()


    @showExc(funcOnExc = showExcOnBanner)
    def loadMsg(self: ZhiXueFlet, msg_start, msg_end) -> None:
        assert self.socialusr is not None
        connID = self.chatDetail.data
        msg_list = self.socialusr.load_msg(connID, msg_start, msg_end)
        msg_dict = {}
        for control in self.chatDetail.controls:
            if control.data == 55730000:
                continue
            msg_dict[control.data] = control
        del control
        now_time = time.time()
        for msg in msg_list[::-1]:
            msg_index, msg_time, msg_sender, msg = msg
            msg_time = int(msg_time /1000)
            if now_time -msg_time <= 86400:
                time_format = "%H:%M"
            elif now_time -msg_time <= 86400 *365:
                time_format = "%m-%d"
            else:
                time_format = "%Y-%m"
            msg_time = time.strftime(time_format, time.localtime(msg_time))
            if msg_index in msg_dict:
                self.chatDetail.controls.remove(msg_dict[msg_index])
            if msg_sender == "system":
                self.chatDetail.controls.append(
                    flet.Row(
                        spacing = 0, alignment = flet.MainAxisAlignment.CENTER,
                        data = msg_index,
                        controls = [
                            flet.Text(f"{msg_time}  {msg}", italic = True, color = flet.colors.ON_SURFACE, opacity = 0.6, size = 12, text_align = flet.TextAlign.CENTER)
                        ]
                    )
                )
            else:
                user_name = User(msg_sender).get_realname()
                # self.chatDetail.controls.append(
                #     flet.Container(
                #         padding = 0,
                #         data = msg_index,
                #         content = flet.Column(
                #             controls = [
                #                 flet.ListTile(
                #                     title = flet.Text(f"{msg_time}  {user_name}: {msg}", size = 16, text_align = flet.TextAlign.CENTER, no_wrap = False, max_lines = 1024),
                #                     # subtitle = flet.Text(latest_msg, opacity = 0.6, max_lines = 1, overflow = flet.TextOverflow.ELLIPSIS),
                #                 )
                #             ]
                #         )
                #     )
                # )
                self.chatDetail.controls.append(
                    flet.Container(
                        padding = 4,
                        data = msg_index,
                        content = flet.Text(f"{msg_time}  {user_name}: {msg}", size = 16, text_align = flet.TextAlign.START, no_wrap = False, max_lines = 1024)
                    )
                )
        self.chatDetail.controls.sort(key = lambda control: control.data, reverse = True)


    @showExc(funcOnExc = showExcOnBanner)
    def closeChatDetail(self: ZhiXueFlet, event) -> None:
        self.pageFriendFormat.data = "聊天列表"
        self.chatDetail.data = None
        self.chatDetail.controls = [self.chatDetail.controls.pop(0)]
        for control in self.chatList.controls:
            if not isinstance(control, flet.Container):
                continue
            control.border = flet.Border(*((flet.BorderSide(2, flet.colors.PRIMARY_CONTAINER +",0"), ) *4))
        self.onResize()


    @showExc(funcOnExc = showExcOnBanner)
    def refreshExamList(self: ZhiXueFlet, event = None) -> None:
        if self.zhixue is None:
            raise ZhiXueFletException("刷新考试列表异常: 用户未登录智学网.")
        if (action_too_frequently := self.checkFrequency("refreshExamList")):
            return
            raise ZhiXueFletError(f"切换页面太快..")
        with self.actionLock:
            self.examList.controls.clear()
            self.examList.controls.append(
                flet.Row(
                    alignment = flet.MainAxisAlignment.CENTER,
                    controls = [
                        flet.Text("获取考试列表...", size = 16)
                    ]
                )
            )
            self.update()
            examListStudent = {}
            examListSchool = {}
            examList = {}
            try:
                if (self.zhixue.userSchoolID == "1500000100044990927") and (self.zhixue_is_nopwd_student):
                    examListStudent: dict = copy.deepcopy(xiezhen.getExamList(maxNum = 5))
                    examListStudent_tmp = copy.deepcopy(examListStudent)
                    examListStudent.update(copy.deepcopy(xiezhen.getExamList(maxNum = 1024)))
                    examListStudent.update(examListStudent_tmp)
                else:
                    examListStudent: dict = copy.deepcopy(self.zhixue.getExamList(maxNum = 5))
                    examListStudent_tmp = copy.deepcopy(examListStudent)
                    examListStudent.update(copy.deepcopy(self.zhixue.getExamList(maxNum = 1024)))
                    examListStudent.update(examListStudent_tmp)
                [exam.update({"exam_is_gotten_by_teacher": False, "preload": False}) for exam in examListStudent.values()]
                examList = examListStudent
            except ZhiXueError as exc:
                print(exc)
            try:
                examListSchool: dict = copy.deepcopy(ZhiXue.getExamListByEnrollmentYear(self.zhixue.userSchoolID, self.zhixue.studentEnrollmentStageName, self.zhixue.studentEnrollmentYear, maxNum = 5))
                examListSchool_tmp = copy.deepcopy(examListSchool)
                examListSchool.update(copy.deepcopy(ZhiXue.getExamListByEnrollmentYear(self.zhixue.userSchoolID, self.zhixue.studentEnrollmentStageName, self.zhixue.studentEnrollmentYear, maxNum = 1024)))
                examListSchool.update(examListSchool_tmp)
                [exam.update({"exam_is_gotten_by_teacher": True, "preload": False}) for exam in examListSchool.values()]
                examListSchool.update(examListStudent)
                examList = examListSchool
            except ZhiXueError as exc:
                print(exc)
        # if self.zhixue.userID == "1500000100077346483":
        if self.zhixue.userSchoolID == "2300000001000049726" and self.zhixue.studentEnrollmentYear == 2022:
            examListOriginal = examList
            examList = copy.deepcopy(EXAM_LIST_ADVANCE)
            examList.update(copy.deepcopy(EXAM_LIST_JSON))
            examList.update(examListOriginal)
        if not examList:
            raise ZhiXueFletException("获取考试列表异常: 获取结果为空.")
        examList = {examID: examList[examID] for examID in sorted(examList, key = lambda x: examList[x]["examCreateTime"], reverse = True)}
        self.examList.controls.clear()
        for examID, exam in examList.items():
            examName = (
                "[五岳] " if examID.startswith("./")
              else (
                "[前瞻] " if exam["preload"]
              else (
                "[考试] " if (exam["reportType"] == "exam")
              else
                "[作业] "
            ))) +exam["examName"]
            examTime = time.strftime("%Y-%m-%d", time.localtime(exam["examCreateTime"]))
            examStatusText = []
            finished = exam["finished"]
            published = exam["published"]
            taken_by_student = (not exam["exam_is_gotten_by_teacher"]) or (self.zhixue_is_nopwd_student)
            if not finished: examStatusText.append("在阅卷")
            if not published: examStatusText.append("未发布")
            if not taken_by_student: examStatusText.append("没参加")
            examStatusText = ", ".join(examStatusText)
            self.examList.controls.append(
                flet.TextButton(
                    tooltip = f"考试时间: {examTime}",
                    on_click = lambda event: self.refreshExamDetail(*event.control.data),
                    data = (examID, exam),
                    style = flet.ButtonStyle(
                        shape = flet.RoundedRectangleBorder(radius = 2),
                    ),
                    content = flet.Row(
                        controls = [
                            flet.Text(
                                value = f"{examName}",
                                font_family = "MCAE",
                                size = 16,
                                expand = True,
                                color = flet.colors.ON_SURFACE if (published and taken_by_student) else flet.colors.GREY_500,
                                max_lines = 1,
                                overflow = flet.TextOverflow.ELLIPSIS,
                            ),
                            flet.Text(
                                value = f"{examStatusText}",
                                font_family = "MCGNU",
                                color = flet.colors.ON_SURFACE if (published and taken_by_student) else flet.colors.GREY_500,
                            ),
                        ],
                    )
                )
            )


    def progressFunc(self, action: str, current: int, total: int) -> None:
        if not self.connected:
            raise ZhiXueProcessStopped("处理数据终止: 用户断开连接.")
        _showText = action
        if action == "Exam.getExamClassList":
            _showText = f"获取参考班级列表...\n[{current}/{total}]"
        if action == "Exam.getExamStudentScoreList":
            _showText = f"获取学生分数...\n[{current}/{total}]"
        if action == "Exam.getExamSubjectStudentRankList":
            _showText = f"处理学生分数...\n[{current}/{total}]"
        if action == "Exam.getExamSubjectMarkingProgress":
            _showText = f"获取阅卷进度...\n"
        if _showText != action:
            self.examDetailLoadingText.value = _showText
            self.update()
            if (current not in [1, total]) and (current %5 != 0):
                return
            self.changeOthersLoadingContainer("某位同学正在点进考试\n所以.. 网页现在无法做其他操作\n怕大家无聊, 显示一下他的加载进度好啦\n" +"-" *32 +"\n" +_showText)


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.examDetailBackButton.disabled = False", "self.examDetailSwitchScoreRankButton.disabled = False", "self.closeOthersLoadingContainer()"])
    def refreshExamDetail(self: ZhiXueFlet, examID: str, examInfo: dict = {}) -> None:
        self.examDetailSwitchScoreRankButton.disabled = True
        if self.zhixue is None:
            raise ZhiXueFletException("构建考试详情页面异常: 用户未登录智学网.")
        if (examID in ZhiXueExamDict) or (examID in EXAM_LIST_JSON) or (examID in os.listdir("./data/zhixue/exam/")):
            action_too_frequently = self.checkFrequency("refreshExamDetailCache")
        else:
            action_too_frequently = self.checkFrequency("refreshExamDetail")
        if action_too_frequently:
            raise ZhiXueFletError(f"查看过于频繁啦, 再等等 {action_too_frequently:.2f}s 哦.")
        self.examDetailBackButton.disabled = True
        self.examDetailLoadingText.visible = True
        self.examDetailTitle.visible = False
        self.examDetailReportUpdateTimeText.visible = False
        self.examDetailTotalScoreRow.controls.clear()
        self.examDetailSubjectScoreRow.controls.clear()
        self.examDetailLoadingText.value = "初始化..."

        self.changeSubPage("主页", "考试详情")
        self.update()
        exam_is_in_advance = examInfo.get("preload", False)
        studentInfoDict = {
            "studentName": self.zhixue.userName,
            "studentCode": self.zhixue.studentCode,
            "studentSchoolID": self.zhixue.userSchoolID,
            "studentClassID": self.zhixue.studentClassID,
            "studentClassName": self.zhixue.studentClassName
        }

        if examID.startswith("./"):
            exam = JsonExam(examID)
        else:
            exam = ZhiXueExam(examID)
        examData = exam.getExamInfo()
        examName = examData["examName"]
        examReportUpdateTime = exam.getReportUpdateTime()
        exam_is_in_advance = exam_is_in_advance and (examReportUpdateTime == (TIME_START -((TIME_START +TIME_ONE_HOUR *4) %86400) -TIME_WAIT_FOR_REPORT_TO_BE_GENERATED))
        exam.in_advance = exam_is_in_advance # type: ignore

        self.examDetailReportUpdateTimeText.value = f"成绩更新时间: {datetime.datetime.fromtimestamp(examReportUpdateTime).strftime('%Y-%m-%d %H:%M:%S') if (exam_is_in_advance is False) else '这是前瞻的考试, 还没有成绩报告.'}"
        self.examDetailReportUpdateTimeText.visible = True
        self.update()

        try:
            is_forcely_get = False
            if exam_is_in_advance:
                raise ZhiXueError("这是前瞻的考试, 还没有成绩报告.")
            # if exam_is_in_advance:
            #     is_forcely_get = True
            # else:
            #     is_forcely_get = False
            if not is_forcely_get:
                studentData = exam.getExamStudentScore(self.zhixue.userID, is_forcely_get = False, progressFunc = self.progressFunc, studentInfoDict = studentInfoDict)
            else:
                studentData = exam.getExamStudentScore(self.zhixue.studentCode, is_forcely_get = True, progressFunc = self.progressFunc, studentInfoDict = studentInfoDict)
        # except (ZhiXueExamClassNumTooManyError, ZhiXueNoPermissionError, ZhiXueExamStudentNotFoundError, ZhiXueExamAdvance) as exc:
        except (ZhiXueError) as exc:
            excType = type(exc)
            excInfo = f"{excType.__name__}: {exc}"
            exceptionColumn = flet.Column(
                spacing = 0,
                controls = [
                    flet.Column(
                        spacing = 0,
                        expand = True,
                        controls = [
                            flet.Text("这里有一些错误...", size = 24, text_align = flet.TextAlign.CENTER),
                            flet.Text(excInfo, size = 16),
                        ]
                    ),
                    flet.Column(
                        spacing = 0,
                        alignment = flet.MainAxisAlignment.END,
                        controls = [
                            flet.Row(
                                spacing = 0,
                                alignment = flet.MainAxisAlignment.END,
                                controls = [
                                    flet.TextButton(
                                        text = "啊.. 只能返回考试列表了.. (伤心.jpg)",
                                        on_click = lambda event: [
                                            self.closeDialog(),
                                            self.changeSubPage("主页", "考试列表")
                                        ],
                                        style = flet.ButtonStyle(
                                            shape = flet.RoundedRectangleBorder(radius = 2),
                                        ),
                                    ),
                                ]
                            ),
                            flet.Row(
                                spacing = 0,
                                alignment = flet.MainAxisAlignment.END,
                                controls = [
                                    flet.TextButton(
                                        text = "这样嘛.. 那.. 我看看实时成绩..?\n        也许能成功 (期待ing)",
                                        on_click = lambda event: [
                                            self.closeDialog(),
                                        ],
                                        style = flet.ButtonStyle(
                                            shape = flet.RoundedRectangleBorder(radius = 2),
                                        ),
                                    ),
                                ]
                            ),
                            flet.Row(
                                spacing = 0,
                                alignment = flet.MainAxisAlignment.END,
                                controls = [
                                    flet.TextButton(
                                        text = "能不能先尝试获取查询权限呢 qwq" if (
                                                    exam.getDataFromCache("tried_to_get_permission") is None
                                                ) else "获取查询权限尝试失败...",
                                        # disabled = False if (
                                        #             isinstance(exc, ZhiXueNoPermissionError) \
                                        #         and (exam.getDataFromCache("tried_to_get_permission") is None)
                                        #         and (any(subject["subject_is_finished"] for (subjectID, subject) in exam.getExamSubjectList().items()))
                                        #         ) else True,
                                        # on_click = lambda event: [
                                        #     self.raiseException(ZhiXueFletError, "点击过于频繁.") if self.checkFrequency("examDetailSubjectContainerClick") else None,
                                        #     self.closeDialog(),
                                        #     exam.setData("tried_to_get_permission", True),
                                        #     exam._setReportPermission(),
                                        #     self.refreshExamDetail(examID)
                                        # ],
                                        disabled = True,
                                        style = flet.ButtonStyle(
                                            shape = flet.RoundedRectangleBorder(radius = 2),
                                        ),
                                    ),
                                ]
                            ),
                        ]
                    ),
                ]
            )
            self.dialogContainer.content = flet.Container(
                padding = 0, margin = 10,
                content = exceptionColumn
            )
            self.dialogCloseButton.disabled = True
            self.dialog.open = True
            self.update()
            studentData = {}
            studentData["subjectList"] = exam.getExamSubjectList(add_assign_score_if_exam_is_assign = True)
            studentData["studentInfo"] = studentInfoDict

        self.examDetailLoadingText.value = "构建页面..."
        self.update()
        self.closeOthersLoadingContainer()
        self.examDetailLoadingText.visible = False
        self.examDetailTitle.visible = True
        self.examDetailTitle.value = f"{examName}"
        exam_is_assign = studentData["subjectList"]["score"]["subject_is_assign"]
        studentInfo = studentData["studentInfo"]
        for subjectID, subject in studentData["subjectList"].items():
            if not isinstance(subject, dict):
                raise ZhiXueFletError(f"构建考试详情页面异常: 学科 {subjectID} 数据不是字典.")
            subjectName = subject["subjectName"]
            subjectStandardScore = subject["subjectStandardScore"]
            subjectMarkingProgress: float = round(subject["subjectMarkingProgress"] *100, 2)
            if isinstance(subjectMarkingProgress, float) and subjectMarkingProgress.is_integer():
                subjectMarkingProgress = int(subjectMarkingProgress)
            studentScore: Optional[Union[int, float]] = subject.get("studentScore", None)
            studentScoreAssign: Optional[Union[int, float]] = subject.get("studentScoreAssign", None)
            studentScoreRankClass = subject.get("studentScoreRankClass", None)
            studentScoreRankSchool = subject.get("studentScoreRankSchool", None)
            studentScoreRankAll = subject.get("studentScoreRankAll", None)
            studentNumClass = subject.get("studentNumClass", 1)
            studentNumSchool = subject.get("studentNumSchool", 1)
            studentNumAll = subject.get("studentNumAll", 1)
            classNumAll = subject.get("classNumAll", 1)
            schoolNum = subject.get("schoolNum", 1)
            subject_is_not_total_score = not subjectID.startswith("score")
            subject_is_total_score = not subject_is_not_total_score
            subject_is_finished = subject["subject_is_finished"]
            subject_is_assign = subject["subject_is_assign"]
            subject_marking_is_completed = subjectMarkingProgress == 100
            if exam_is_in_advance:
                if len(studentData["subjectList"]) > 6:
                    subject_marking_is_completed = False
                    subject_is_finished = False
            subject_report_can_be_published = (not subject_is_finished) and subject_is_not_total_score and subject_marking_is_completed and (not GENERATE_REPORT_DISABLED)
            have_student_score = studentScore is not None
            have_student_assign_score = studentScoreAssign is not None
            for subjectContainerType in ["score", "rank", "marking", "scoreAdvance"]:
                if not subject_is_finished:
                    if subjectContainerType in ["score", "rank"]:
                        continue
                # if (subject_marking_is_completed and (subject["subjectMarkingStatus"] != "m3marking")):
                if (
                    subject_marking_is_completed
                  and (
                    subject["subjectMarkingStatus"] not in ["m3marking", "m2startScan"]
                  )
                ) or ((
                    subjectMarkingProgress == 0
                  )
                  and (
                    time.time() -examReportUpdateTime >= 3600 *1
                  )
                  and (
                    len(studentData["subjectList"]) > 6
                  )
                ) or (
                    time.time() -examReportUpdateTime >= 86400 *3
                ):
                    if subjectContainerType in ["marking", "scoreAdvance"]:
                        continue
                textColor = flet.colors.ON_SURFACE
                scoreLeftColor = flet.colors.ON_SURFACE
                scoreRightColor = flet.colors.GREY_500
                if subjectContainerType == "marking":
                    backgroundColor = flet.colors.PRIMARY_CONTAINER
                    backgroundPercent = int(round(subjectMarkingProgress))
                elif subjectContainerType == "scoreAdvance":
                    backgroundColor = flet.colors.PRIMARY_CONTAINER
                    backgroundPercent = int(round(subjectMarkingProgress))
                elif subjectContainerType == "score":
                    backgroundColor = flet.colors.PRIMARY_CONTAINER
                    backgroundPercent = (int(round(studentScore /subjectStandardScore *100)) if (subjectStandardScore > 0) else 100) if have_student_score else 0
                elif subjectContainerType == "rank":
                    backgroundColor = flet.colors.PRIMARY_CONTAINER
                    backgroundPercent = (100 -int(round((studentScoreRankAll -1) /studentNumAll *100))) if ((studentNumAll != 0) and (studentScoreRankAll is not None)) else 0
                else:
                    raise ZhiXueFletException(f"构建考试详情页面异常: 未知的学科容器类型 {subjectContainerType}.")
                if backgroundPercent > 100:
                    backgroundPercent = 100
                if backgroundPercent < 0:
                    backgroundPercent = 0
                subjectTextButton = flet.TextButton(
                    visible = True if (subjectContainerType not in ["rank", "scoreAdvance"]) else False,
                    height = 75,
                    data = (subjectContainerType, exam, subjectID, subject, studentInfo), on_click = self.examDetailSubjectContainerClick,
                    col = {"xs": 4, "sm": 3, "md": 3, "lg": 2.4, "xl": 2, "xxl": 1.5} if subject_is_not_total_score else ({"xs": 12, "sm": 6, "md": 6, "lg": 6, "xl": 6, "xxl": 6} if exam_is_assign else {"xs": 12, "sm": 12, "md": 12, "lg": 12, "xl": 12, "xxl": 12}),
                    style = flet.ButtonStyle(
                        padding = 0,
                        # side = flet.BorderSide(2, backgroundColor),
                        shape = flet.RoundedRectangleBorder(radius = 0),
                    ),
                    content = flet.Container(
                        padding = 0,
                        content = flet.Stack(
                            controls = [
                                flet.Container(
                                    padding = 0,
                                    border = flet.Border(*((flet.BorderSide(2, backgroundColor), ) *4)),
                                    opacity = 0.6,
                                    content = flet.Row(
                                        spacing = 0, run_spacing = 0,
                                        controls = [
                                            flet.Container(
                                                bgcolor = backgroundColor,
                                                expand = backgroundPercent,
                                            ),
                                            flet.Container(
                                                expand = 100 -backgroundPercent,
                                            )
                                        ]
                                    ),
                                ),
                                flet.Column(
                                    spacing = 2, run_spacing = 0,
                                    alignment = flet.MainAxisAlignment.START,
                                    controls = [
                                        flet.Row(
                                            spacing = 0, run_spacing = 0,
                                            alignment = flet.MainAxisAlignment.SPACE_BETWEEN,
                                            controls = [
                                                flet.Text(subjectName, size = 16, color = textColor),
                                                flet.Text("" if subject_is_finished
                                                    else ("阅卷中" if (not subject_marking_is_completed)
                                                    else  "阅卷完成"),
                                                          offset = flet.Offset(0, -0.5), size = 8, color = textColor),
                                            ]
                                        ),
                                        flet.Row(
                                            spacing = 0, run_spacing = 0,
                                            expand = 1, offset = flet.Offset(0, -0.1),
                                            alignment = flet.MainAxisAlignment.SPACE_EVENLY,
                                            controls =
                                            [   # 正在阅卷格式.
                                                flet.Column(
                                                    alignment = flet.MainAxisAlignment.CENTER,
                                                    controls = [
                                                        flet.Text(f"{subjectMarkingProgress}%" if (not subject_report_can_be_published)
                                                             else ("智学网正在生成报告" if (exam.getDataFromCache(f"{subjectID}_is_regenerating") is True)
                                                             else  "点击发布成绩"),
                                                                  size = 20 if (not subject_report_can_be_published)
                                                                    else 12,
                                                                  color = textColor, text_align = flet.TextAlign.CENTER)
                                                    ]
                                                ),
                                            ] if (subjectContainerType == "marking") else (
                                            [   # 分数格式.
                                                flet.Column(width = 2),
                                                flet.Column(
                                                    spacing = 0, run_spacing = 0,
                                                    alignment = flet.MainAxisAlignment.START,
                                                    controls = [
                                                        flet.Text(f"{studentScore}" if have_student_score else " -", size = 30, color = scoreLeftColor, font_family = "MCASCII", text_align = flet.TextAlign.RIGHT),
                                                    ] if (subject_is_total_score or (not subject_is_assign)) else [
                                                        flet.Stack(
                                                            controls = [
                                                                flet.Text(f"{studentScore}" if have_student_score else " -", size = 30, color = scoreLeftColor, font_family = "MCASCII", text_align = flet.TextAlign.RIGHT),
                                                                flet.Text(f"{studentScoreAssign}" if have_student_assign_score else " -", size = 10, color = scoreLeftColor, font_family = "MCASCII", text_align = flet.TextAlign.RIGHT),
                                                            ]
                                                        )
                                                    ]
                                                ),
                                                flet.Column(
                                                    offset = flet.Offset(0, 0.1),
                                                    alignment = flet.MainAxisAlignment.CENTER,
                                                    controls = [
                                                        flet.Text("/", size = 16, color = scoreRightColor, font_family = "MCASCII")
                                                    ]
                                                ),
                                                flet.Column(
                                                    alignment = flet.MainAxisAlignment.END,
                                                    controls = [
                                                        flet.Text(f"{subjectStandardScore}", size = 16, color = scoreRightColor, font_family = "MCASCII", text_align = flet.TextAlign.LEFT)
                                                    ]
                                                ),
                                                flet.Column(width = 2),
                                            ] if (subjectContainerType == "score") else (
                                            [   # 排名格式.
                                                flet.Column(
                                                    spacing = 0, run_spacing = 0,
                                                    alignment = flet.MainAxisAlignment.CENTER,
                                                    controls =
                                                    [
                                                        flet.Text(f"班: {studentScoreRankClass} / {studentNumClass}", offset = flet.Offset(0, 0), size = 14, color = textColor, text_align = flet.TextAlign.CENTER),
                                                        flet.Text(f"年: {studentScoreRankSchool} / {studentNumSchool}", offset = flet.Offset(0, -0.2), size = 14, color = textColor, text_align = flet.TextAlign.CENTER),
                                                        flet.Text(f"联: {studentScoreRankAll} / {studentNumAll}", offset = flet.Offset(0, -0.4), size = 14, color = textColor, text_align = flet.TextAlign.CENTER),
                                                    ] if ((schoolNum > 1) or (studentNumSchool == 0)) else (
                                                    [
                                                        flet.Text(f"班: {studentScoreRankClass} / {studentNumClass}", offset = flet.Offset(0, 0.2), size = 14, color = textColor, text_align = flet.TextAlign.CENTER),
                                                        flet.Text(f"年: {studentScoreRankSchool} / {studentNumSchool}", offset = flet.Offset(0, 0), size = 14, color = textColor, text_align = flet.TextAlign.CENTER),
                                                    ] if ((classNumAll > 1) or (studentNumClass == 0)) else (
                                                    [
                                                        flet.Text(f"班: {studentScoreRankClass} / {studentNumClass}", offset = flet.Offset(0, 0), size = 14, color = textColor, text_align = flet.TextAlign.CENTER),
                                                    ]
                                                    ))
                                                )
                                            ] if (subjectContainerType == "rank") else (
                                            [   # 提前查分格式.
                                                flet.Column(
                                                    alignment = flet.MainAxisAlignment.CENTER,
                                                    controls = [
                                                        flet.Text(f"实时成绩", size = 14, color = textColor, text_align = flet.TextAlign.CENTER)
                                                    ]
                                                ),
                                            ] if (subjectContainerType == "scoreAdvance") else (
                                            [   # 异常格式.
                                                self.raiseException(ZhiXueFletException, f"构建考试详情页面异常: 未知的学科容器类型 {subjectContainerType}.")
                                            ]
                                            ))))
                                        ),
                                    ],
                                )
                            ],
                        ),
                    )
                )
                if subjectID.startswith("score"):
                    self.examDetailTotalScoreRow.controls.append(subjectTextButton)
                else:
                    self.examDetailSubjectScoreRow.controls.append(subjectTextButton)
        # deleteObject(exam)


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.examDetailSwitchScoreRankButton.disabled = False"])
    def examDetailSwitchScoreRank(self: ZhiXueFlet, event) -> None:
        self.examDetailSwitchScoreRankButton.disabled = True
        action_too_frequently = self.checkFrequency("examDetailSwitchScoreRank")
        if action_too_frequently:
            raise ZhiXueFletError(f"操作过于频繁啦, 再等等 {action_too_frequently:.2f}s 哦.")
        for subjectContainer in (self.examDetailTotalScoreRow.controls +self.examDetailSubjectScoreRow.controls):
            subjectContainerType = subjectContainer.data[0]
            subjectID = subjectContainer.data[2]
            # if subjectContainerType == "marking":
            #     continue
            if (subjectContainerType in ["marking", "scoreAdvance"]) and subjectID.startswith("score"):
                continue
            subjectContainer.visible = not subjectContainer.visible
        self.examDetailSwitchScoreRankButton.icon = flet.icons.SWITCH_RIGHT if (self.examDetailSwitchScoreRankButton.icon == flet.icons.SWITCH_LEFT) else flet.icons.SWITCH_LEFT


    @showExc(funcOnExc = showExcOnBanner)
    def switchDayNight(self: ZhiXueFlet, event) -> None:
        with self.actionLock:
            action_too_frequently = self.checkFrequency("switchDayNight")
            if action_too_frequently:
                return
            self.page.theme_mode = flet.ThemeMode.LIGHT if (self.page.theme_mode == flet.ThemeMode.DARK) else flet.ThemeMode.DARK
            self.closeBanner()


    @showExc(funcOnExc = showExcOnBanner)
    def switchColor(self: ZhiXueFlet, event) -> None:
        with self.actionLock:
            action_too_frequently = self.checkFrequency("switchColor")
            if action_too_frequently:
                return
            themeColorIndex = self.themeColorIndex
            if themeColorIndex +1 >= len(themeColorList):
                themeColorIndex = 0
            else:
                themeColorIndex += 1
            self.themeColorIndex = themeColorIndex
            self.setColorByIndex(themeColorIndex)
            try:
                self.page.client_storage.set("ZhiXueFlet_themeColorIndex", themeColorIndex)
            except TimeoutError as exc:
                print(exc)


    @showExc(funcOnExc = showExcOnBanner)
    def setColorByIndex(self: ZhiXueFlet, index: int) -> None:
        self.page.theme.color_scheme_seed = themeColorList[index][0]
        self.page.dark_theme.color_scheme_seed = themeColorList[index][1]


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.dialogCloseButton.disabled = False", "self.closeOthersLoadingContainer()"])
    def examDetailSubjectContainerClick(self: ZhiXueFlet, event) -> None:
        self.dialogCloseButton.disabled = True
        if self.zhixue is None:
            raise ZhiXueFletException("构建学科排名详情对话框异常: 用户未登录智学网.")
        action_too_frequently = self.checkFrequency("examDetailSubjectContainerClick")
        if action_too_frequently:
            raise ZhiXueFletError(f"操作过于频繁啦, 再等等 {action_too_frequently:.2f}s 哦.")
        subjectContainerType: str; exam: ZhiXueExam; subjectID: str; subject: dict; studentInfo: dict
        subjectContainerType, exam, subjectID, subject, studentInfo = event.control.data

        subjectName = subject["subjectName"]
        subjectStandardScore = subject["subjectStandardScore"]
        subjectMarkingProgress: float = round(subject["subjectMarkingProgress"] *100, 2)
        if isinstance(subjectMarkingProgress, float) and subjectMarkingProgress.is_integer():
            subjectMarkingProgress = int(subjectMarkingProgress)
        exam_is_in_advance = exam.in_advance # type: ignore
        studentName = studentInfo["studentName"]
        studentSchoolID = studentInfo["studentSchoolID"]
        studentClassID = studentInfo["studentClassID"]
        studentScore = subject.get("studentScore", 0)
        studentScoreAssign = subject.get("studentScoreAssign", None)
        subject_is_not_total_score = not subjectID.startswith("score")
        subject_is_total_score = not subject_is_not_total_score
        subject_is_finished = subject["subject_is_finished"]
        subject_is_assign = subject["subject_is_assign"]
        subject_marking_is_completed = subjectMarkingProgress == 100
        if exam_is_in_advance:
            if len(exam.getExamSubjectList()) > 6:
                subject_is_finished = False
                subject_marking_is_completed = False
        subject_report_can_be_published = (not subject_is_finished) and subject_is_not_total_score and subject_marking_is_completed
        have_student_score = studentScore is not None
        have_student_assign_score = studentScoreAssign is not None
        can_load_answer_sheet = subject_is_finished and subject_is_not_total_score and (have_student_score or have_student_assign_score) and (not exam_is_in_advance) and (not isinstance(exam, _JsonExam))
        # if self.zhixue.studentCode == "51497882":
        #     can_load_answer_sheet = True
        can_load_subject_topic_marking_progress = subject_is_not_total_score and ((not subject_marking_is_completed) or (GENERATE_REPORT_DISABLED))
        if subjectContainerType == "score":
            if can_load_answer_sheet:
                self.dialog_show_score(exam, subjectID, studentSchoolID)
            return
        if subjectContainerType == "rank":
            self.dialog_show_rank(exam, subject, subjectID, studentInfo)
            return
        if subjectContainerType == "marking":
            if subject_report_can_be_published:
                self.dialog_show_publish(event, exam, subjectID)
                return
            if can_load_subject_topic_marking_progress:
                self.dialog_show_marking_progress(exam, subjectName, subjectID)
                return
            return
        if subjectContainerType == "scoreAdvance":
            if SCORE_ADVANCE_DISABLED:
                raise NotImplementedError
            if can_load_subject_topic_marking_progress:
                self.dialog_show_score_advance(exam, subjectName, subjectID, subject_is_finished, studentInfo)
            return

    def dialog_show_score(self, exam: ZhiXueExam, subjectID: str, studentSchoolID: str):
        loadingText = flet.Text("网页正在处理答题卡图片...", size = 24, text_align = flet.TextAlign.CENTER)
        self.dialogContainer.content = flet.Row(
            alignment = flet.MainAxisAlignment.CENTER,
            vertical_alignment = flet.CrossAxisAlignment.CENTER,
            controls = [
                loadingText
            ]
        )
        self.dialog.open = True
        self.update()
        assert self.zhixue is not None
        savePath = f"{zhixue.PATH_SAVE_ANSWER_SHEET}{exam.examID}/{subjectID}/{zhixue.MD5(exam.examID +subjectID +self.zhixue.userID)[11:3:-1]}/"
        if not os.path.isfile(savePath +"处理后答题卡.png"):
            result = exam.processSheetData(exam.getSheetData(self.zhixue.userID, subjectID, studentSchoolID), saveFormat = "png", use_cache = True, only_save_processed_sheet_image = True, can_view_marking_teacher = self.can_view_marking_teacher)
            savePath = result["savePath"]
        loadingText.value = "处理完成,\n跳转到答题卡图片链接...\n要允许网页跳转新链接哦."
        self.update()
        time.sleep(1)
        self.page.launch_url(savePath[1:] +"index.html")
        self.closeDialog()


    def dialog_show_rank(self, exam: ZhiXueExam, subject: dict, subjectID: str, studentInfo: dict):
        subjectName = subject["subjectName"]
        subject_is_finished = subject["subject_is_finished"]
        studentNumClass = subject.get("studentNumClass", 1)
        studentNumSchool = subject.get("studentNumSchool", 1)
        classNumSchool = subject.get("classNumSchool", 1)
        studentNumAll = subject.get("studentNumAll", 1)
        classNumAll = subject.get("classNumAll", 1)
        schoolNum = subject.get("schoolNum", 1)
        scoreAverageAll = subject.get("scoreAverageAll", None)
        scoreAverageSchool = subject.get("scoreAverageSchool", None)
        scoreAverageClass = subject.get("scoreAverageClass", None)
        scoreAverageSchoolRank = subject.get("scoreAverageSchoolRank", None)
        scoreAverageClassRankAll = subject.get("scoreAverageClassRankAll", None)
        scoreAverageClassRankSchool = subject.get("scoreAverageClassRankSchool", None)
        self.dialog.open = True
        rankDetailColumn = flet.Column(
            spacing = 0,
            controls = [
                flet.Row(
                    alignment = flet.MainAxisAlignment.START,
                    controls = [
                        flet.Text(f"{subjectName}", size = 24, text_align = flet.TextAlign.CENTER),
                    ]
                )
            ]
        )
        self.dialogContainer.content = flet.Container(
            padding = 0, margin = 10,
            content = rankDetailColumn
        )
        # if classNumSchool <= 0:
        #     raise ZhiXueFletError("显示学科排名详细数据异常: 学生学校参考班级数为零.")
        if schoolNum <= 0:
            raise ZhiXueFletError("显示学科排名详细数据异常: 参考学校数为零.")
        rankDetailColumn.controls.append(flet.Divider())
        rankDetailColumn.controls.append(
            flet.Text(f"班级平均分: {scoreAverageClass}")
        )
        if classNumSchool > 1:
            rankDetailColumn.controls.append(
                flet.Text(f"班均分在校排: {scoreAverageClassRankSchool} / {classNumSchool}")
            )
        if schoolNum > 1:
            rankDetailColumn.controls.append(
                flet.Text(f"班均分在总排: {scoreAverageClassRankAll} / {classNumAll}")
            )
        if (classNumSchool > 1) or (scoreAverageClass == 0):
            rankDetailColumn.controls.append(flet.Divider())
            rankDetailColumn.controls.append(
                flet.Text(f"校级平均分: {scoreAverageSchool}")
            )
            if schoolNum > 1:
                rankDetailColumn.controls.append(
                    flet.Text(f"校均分排: {scoreAverageSchoolRank} / {schoolNum}")
                )
        if (schoolNum > 1) or (scoreAverageSchool == 0):
            rankDetailColumn.controls.append(flet.Divider())
            rankDetailColumn.controls.append(
                flet.Text(f"联考平均分: {scoreAverageAll}")
            )
        rankDetailColumn.controls.append(
            flet.Row(
                alignment = flet.MainAxisAlignment.END,
                controls = [
                    flet.TextButton("查看小题分", disabled = True if isinstance(exam, _JsonExam) else False, on_click = lambda _: self.dialog_show_score_advance(exam, subjectName, subjectID, subject_is_finished, studentInfo)),
                ]
            )
        )


    def dialog_show_publish(self, event, exam: ZhiXueExam, subjectID: str):
        publishText: flet.Text = event.control.content.content.controls[1].controls[1].controls[0].controls[0]
        if publishText.value == "点击发布成绩":
            if GENERATE_REPORT_DISABLED:
                raise NotImplementedError
            publishText.value = "尝试发布..."
            self.update()
            if exam.getDataFromCache(f"{subjectID}_is_regenerating") is None:
                publishText.value = "执行第一步.."
                self.update()
                host = exam.getSubjectHost(subjectID)
                result = json.loads(exam.zhixue.getDataFromURL(f"https://www.zhixue.com/exam/progress/generateInMarkingTask?markingPaperId={subjectID}"))
                if result["result"] != "success":
                    publishText.value = "发布失败"
                    raise ZhiXueFletException(f"发布学科报告异常: {result['message']}")
                time.sleep(1)
                publishText.value = "执行第二步.."
                self.update()
                result = json.loads(zhixue.ZhiXueApplier.getDataFromURL(f"{host}/exam/marking/completemarking/?markingPaperId={subjectID}"))
                if result["result"] != "success":
                    if result["message"] != "该试卷己完成阅卷!":
                        publishText.value = "发布失败"
                        raise ZhiXueFletException(f"发布学科报告异常: {result['message']}")
                exam.setData(f"{subjectID}_is_regenerating", True)
                time.sleep(1)
                for i in range(1, 31):
                    publishText.value = f"[{i}/30] 等待..."
                    self.update()
                    time.sleep(1)
                publishText.value = "执行第三步.."
                self.update()
                host = exam.getExamHost()
                for checkItem in ["planUser", "progress", "archiveCheck"]:
                    result = json.loads(zhixue.ZhiXueApplier.getDataFromURL(f"{host}/exam/report/confirmCheck?markingPaperId={subjectID}&checkItem={checkItem}"))
                    if result["result"] != "success":
                        publishText.value = "发布失败"
                        raise ZhiXueFletException(f"发布学科报告异常: {result['message']}")

                result = json.loads(zhixue.ZhiXueApplier.getDataFromURL(f"{host}/exam/report/createReport?examId={exam.examID}"))
                if result["result"] != "success":
                    publishText.value = "发布失败"
                    raise ZhiXueFletException(f"发布学科报告异常: {result['message']}")
                publishText.value = "发布成功"
                exam.reloadExamRankForcely()
            else:
                publishText.value = "不能重复发布"


    def dialog_show_marking_progress(self, exam: ZhiXueExam, subjectName: str, subjectID: str):
        self.dialog.open = True
        self.dialogContainer.content = flet.Container(
            padding = 0, margin = 10,
            content = flet.Row(
                alignment = flet.MainAxisAlignment.CENTER,
                vertical_alignment = flet.CrossAxisAlignment.CENTER,
                controls = [
                    flet.Text("加载中...", size = 32, text_align = flet.TextAlign.CENTER)
                ]
            )
        )
        self.update()

        subjectTopicMarkingDetailColumn = flet.Column(
            spacing = 0,
            scroll = flet.ScrollMode.AUTO,
            controls = [
                flet.Text(f"{subjectName}", size = 24, text_align = flet.TextAlign.CENTER),
            ]
        )
        self.dialogContainer.content.alignment = flet.alignment.top_center
        self.dialogContainer.content.content = subjectTopicMarkingDetailColumn
        subjectTopicMarkingDetailColumn.controls.append(flet.Divider())
        subjectTopicMarkingProgressDataTable = flet.DataTable(
            width = 10000,
            column_spacing = 4,
            data_row_max_height = 32,
            columns = [
                flet.DataColumn(flet.Text("题号", text_align = flet.TextAlign.CENTER)),
                flet.DataColumn(flet.Text("份数", text_align = flet.TextAlign.CENTER)),
                flet.DataColumn(flet.Text("进度", text_align = flet.TextAlign.CENTER)),
            ],
        )
        lst = []
        for topic in exam.getExamSubjectTopicMarkingProgress(subjectID):
            subjectTopicMarkingProgress: float = round(topic["topicMarkingProgress"] *100, 2)
            if isinstance(subjectTopicMarkingProgress, float) and subjectTopicMarkingProgress.is_integer():
                subjectTopicMarkingProgress = int(subjectTopicMarkingProgress)
            if topic['topicName'] != "总计":
                lst.append(subjectTopicMarkingProgress)
            subjectTopicMarkingProgressDataTable.rows.append(
                flet.DataRow(
                    cells = [
                        flet.DataCell(flet.Text(f"{topic['topicName']}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                        flet.DataCell(flet.Text(f"{topic['topicMarkingCountFinished']} / {topic['topicMarkingCountAll']}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                        flet.DataCell(flet.Text(f"{subjectTopicMarkingProgress} %", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                    ]
                )
            )
        P_allTopicAreMarked = Decimal(100)
        for P in lst:
            P_allTopicAreMarked *= Decimal(P)
        print(lst)
        P_allTopicAreMarked /= (100 **len(lst))
        P_allTopicAreMarked_rounded = round(P_allTopicAreMarked, 2)
        if (P_allTopicAreMarked != 0) and (P_allTopicAreMarked_rounded == 0):
            P_allTopicAreMarked = f"{P_allTopicAreMarked:.2e})".replace("e", "×10^(")
        else:
            P_allTopicAreMarked = P_allTopicAreMarked_rounded
        subjectTopicMarkingProgressDataTable.rows.insert(0,
            flet.DataRow(
                cells = [
                    flet.DataCell(flet.Text(f"P(A)", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                    flet.DataCell(flet.Text(f"A = 所有题被阅到", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                    flet.DataCell(flet.Text(f"{P_allTopicAreMarked} %", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                ]
            )
        )
        subjectTopicMarkingDetailColumn.controls.append(subjectTopicMarkingProgressDataTable)


    @showExc(funcOnExc = showExcOnBanner, execAfterFinish = ["self.dialogCloseButton.disabled = False", "self.closeOthersLoadingContainer()"])
    def dialog_show_score_advance(self, exam: ZhiXueExam, subjectName: str, subjectID: str, subject_is_finished: bool, studentInfo: dict):
        if SCORE_ADVANCE_DISABLED:
            raise NotImplementedError
        # raise ZhiXueFletError("-------------------------\n智学网修复 实时成绩 的查询 bug,\n这个功能用不了了..............................................................................................................................\n..........................................................................................................................................\n..........................................................................................................................................\n..........................................................................................................................................")
        self.dialog.open = True
        self.dialogCloseButton.disabled = True
        loadingText = flet.Text("加载中...", size = 16, text_align = flet.TextAlign.CENTER)
        self.dialogContainer.content = flet.Container(
            padding = 0, margin = 10,
            content = flet.Row(
                alignment = flet.MainAxisAlignment.CENTER,
                vertical_alignment = flet.CrossAxisAlignment.CENTER,
                controls = [
                    loadingText
                ]
            )
        )
        self.update()
        # self.showOthersLoadingContainer()

        def _progressFunc(name, current, total):
            _showText = name
            if name == "Exam.getExamSubjectObjectiveDetail_init":
                _showText = "\n处理第一.1步\n"
            if name == "Exam.getExamSubjectObjectiveDetail_submitDownload":
                _showText = "\n处理第一.2步\n"
            if name == "Exam.getExamSubjectObjectiveDetail_waitforDownload":
                _showText = f"时间过去 {(current -1) *5}s\n" \
                            f"处理第一.3步\n"
            if name == "Exam.getExamSubjectObjectiveDetail_downloading":
                _showText = "\n处理第一.4步\n"
            if name == "Exam.getExamSubjectObjectiveDetail_unziping":
                _showText = "\n处理第一.5步\n"
            if name == "Exam.getExamSubjectObjectiveDetail_analyzing":
                loadingText.data = (current, total)
                _showText = f"\n处理第一.6步\n" \
                            f"[{current}/{total}]"

            if name == "Exam.prepareExamStudentAnswerRecord_init":
                _showText = f"\n处理第一.6步\n" \
                            f"[{loadingText.data[0]}/{loadingText.data[1]}][1/2][1/4][1/1]"
            if name == "Exam.prepareExamStudentAnswerRecord_wait_1":
                _showText = f"\n处理第一.6步\n" \
                            f"[{loadingText.data[0]}/{loadingText.data[1]}][1/2][2/4][{current}/{total}]"
            if name == "Exam.prepareExamStudentAnswerRecord_wait_2":
                _showText = f"时间过去 {(current -1) *5}s\n" \
                            f"处理第一.6步\n" \
                            f"[{loadingText.data[0]}/{loadingText.data[1]}][1/2][3/4][1/1]"
            if name == "Exam.prepareExamStudentAnswerRecord_wait_3":
                _showText = f"\n处理第一.6步\n" \
                            f"[{loadingText.data[0]}/{loadingText.data[1]}][1/2][4/4][{current}/{total}]"

            if name == "Exam.getExamSubjectTopicList_choice":
                _showText = f"\n处理第一.6步\n" \
                            f"[{loadingText.data[0]}/{loadingText.data[1]}][2/2][{round(current *100 /total)}%]"

            if name == "Exam.getExamSubjectMarkingDetail_init":
                _showText = "\n处理第二.1步\n"
            if name == "Exam.getExamSubjectMarkingDetail_submitDownload":
                _showText = "\n处理第二.2步\n"
            if name == "Exam.getExamSubjectMarkingDetail_waitforDownload":
                _showText = f"时间过去 {(current -1) *5}s\n" \
                            f"处理第二.3步\n"
            if name == "Exam.getExamSubjectMarkingDetail_downloading":
                _showText = "\n处理第二.4步\n"
            if name == "Exam.getExamSubjectMarkingDetail_unziping":
                _showText = "\n处理第二.5步\n"
            if name == "Exam.getExamSubjectMarkingDetail_analyzing":
                _showText = f"\n处理第二.6步\n" \
                            f"[{current}/{total}]"

            if name == "Exam.getExamStudentScoreDetailList_objective":
                _showText = f"\n最终汇总.\n" \
                            f"[1/2][{current}/{total}]\n"
            if name == "Exam.getExamStudentScoreDetailList_marking":
                _showText = f"\n最终汇总.\n" \
                            f"[2/2][{current}/{total}]\n"

            print(_showText)
            if _showText != name:
                loadingText.value = _showText
                self.update()
                self.changeOthersLoadingContainer("某位同学正在加载实时成绩\n所以.. 网页现在无法做其他操作\n怕大家无聊, 显示一下他的加载进度好啦\n" +"-" *32 +"\n" +_showText)
                # time.sleep(0.05)

        subjectTopicMarkingDetailColumn = flet.Column(
            spacing = 0,
            scroll = flet.ScrollMode.AUTO,
            controls = [
                flet.Text(f"{subjectName}", size = 24, text_align = flet.TextAlign.CENTER),
            ]
        )
        subjectTopicMarkingDetailColumn.controls.append(flet.Divider())

        subjectTopicMarkingProgressDataTable = flet.DataTable(
            width = 10000,
            column_spacing = 8, data_row_max_height = 32,
            columns = [
                flet.DataColumn(flet.Text("题号", text_align = flet.TextAlign.CENTER)),
                flet.DataColumn(flet.Text("得分", text_align = flet.TextAlign.CENTER)),
                flet.DataColumn(flet.Text("阅卷老师", text_align = flet.TextAlign.CENTER)),
            ],
        )
        try:
            try:
                if not subject_is_finished:
                    studentDataList = exam.getExamStudentScoreDetailList(_progressFunc)
                else:
                    studentDataList = exam.getExamStudentScoreDetailList(_progressFunc, is_forcely_get = True)
            except Exception as exc:
                loadingText.value = f"{type(exc).__name__}: {str(exc)}".replace(": ", "\n").replace(", ", "\n")
                self.update()
                raise
            # print(studentDataList)
            studentData = studentDataList[studentInfo["studentCode"]]
            # if subjectID not in studentData["subjectList"]:
            #     if subject_is_finished:
            #         studentDataList = exam.getExamStudentScoreDetailList(_progressFunc)
            #     else:
            #         studentDataList = exam.getExamStudentScoreDetailList(_progressFunc, is_forcely_get = True)
            #     studentData = studentDataList[studentInfo["studentCode"]]
            if subjectID not in studentData["subjectList"]:
                raise ZhiXueError("找不到数据.")
            self.closeOthersLoadingContainer()
            studentAverageScoreSubject = 0
            if len(exam.getExamSubjectList()) > 6:
                studentAverageScoreSubject = 4
            for topicIndexAll, topic in studentData["subjectList"][subjectID].items():
                topicName = topic["topicName"]
                studentScore = topic["score"]
                if topicName != "总计":
                    is_choice = topic["is_choice"]
                    studentAverageScoreList = [student["subjectList"].get(subjectID, {}).get(topicIndexAll, {"score": None})["score"] for student in studentDataList.values()]
                    studentAverageScoreList = [score for score in studentAverageScoreList if (score is not None)]
                    if studentAverageScoreList:
                        studentAverageScore = round(sum(studentAverageScoreList) /len(studentAverageScoreList), 2)
                        if studentAverageScoreSubject is not None:
                            studentAverageScoreSubject += studentAverageScore
                    else:
                        studentAverageScore = "-"
                        studentAverageScoreSubject = None
                    del studentAverageScoreList
                else:
                    studentAverageScore = "-"
                    is_choice = False
                if not is_choice:
                    if self.can_view_marking_teacher:
                        studentMarkingTeacherText = ", ".join(f"{teacher['name']}({teacher['score']})" for (teacherRole, teacher) in topic.get("markingTeacher", {}).items())
                    else:
                        studentMarkingTeacherText = "不在功能白名单"
                    subjectTopicMarkingProgressDataTable.rows.append(
                        flet.DataRow(
                            cells = [
                                flet.DataCell(flet.Text(f"{topicName}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                                flet.DataCell(flet.Text(f"{studentScore if (studentScore is not None) else '待批'}  /{studentAverageScore}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                                flet.DataCell(flet.Text(f"{studentMarkingTeacherText if (studentScore is not None) else '-'}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                            ]
                        )
                    )
                else:
                    standardScore = topic["standardScore"]
                    standardAnswer = topic["standardAnswer"]
                    studentAnswer = topic["studentAnswer"]
                    if topicName == "总计":
                        studentMarkingTeacherText = "-"
                    else:
                        studentMarkingTeacherText = f"{studentAnswer} /{standardAnswer}"
                        standardScore = topic["standardScore"]
                        if studentScore is None:
                            studentMarkingTeacherText += ""
                        elif studentScore == 0:
                            studentMarkingTeacherText += " 选错"
                        elif studentScore == standardScore:
                            studentMarkingTeacherText += " 选对"
                        else:
                            studentMarkingTeacherText += " 没选全"
                    subjectTopicMarkingProgressDataTable.rows.append(
                        flet.DataRow(
                            cells = [
                                flet.DataCell(flet.Text(f"{topicName}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                                flet.DataCell(flet.Text(f"{studentScore}  /{studentAverageScore}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                                flet.DataCell(flet.Text(f"{studentMarkingTeacherText}", text_align = flet.TextAlign.CENTER, offset = flet.Offset(0, -0.4))),
                            ]
                        )
                    )
            subjectScoreText = subjectTopicMarkingProgressDataTable.rows[0].cells[1].content
            if studentAverageScoreSubject is not None:
                subjectScoreText.value = subjectScoreText.value.replace("-", str(round(studentAverageScoreSubject, 2)))
            del studentDataList
        except KeyError as exc:
            # print(studentData)
            studentDataList = None
            del studentDataList
            raise
        self.dialogContainer.content.alignment = flet.alignment.top_center
        self.dialogContainer.content.content = subjectTopicMarkingDetailColumn
        subjectTopicMarkingDetailColumn.controls.append(subjectTopicMarkingProgressDataTable)
        self.update()


    @showExc(funcOnExc = showExcOnBanner)
    def _loopThread(self: ZhiXueFlet, stoppableThread: StoppableThread) -> None:
        while self.connected and stoppableThread.running:
            timeStart = time.perf_counter()
            if self.socialusr is not None: pass
                # if self.getCurrentRail().startswith("聊天"):
                #     self.refreshChatList()
            userOnlineNum = len([_ for _ in stoppableThreadList if _.name.startswith("ZhiXueFlet_")])
            try:
                timeDelayStart = time.perf_counter()
                self.page.client_storage.contains_key(f"ZhiXueFlet_delay_{timeDelayStart}")
                delay = time.perf_counter() -timeStart
                self.delayText.value = f"网页延迟: {round(delay *1000)} ms\n在线学生: {userOnlineNum}\nZXF 仅支持 IPv6\n保留所有权利."
            except TimeoutError as exc:
                self.delayText.value = f"网页延迟: > 5000 ms"
            if not (self.connected and stoppableThread.running):
                break
            self.update()
            self.onResize()
            timeSpend = time.perf_counter() -timeStart
            time.sleep((2 -round(timeSpend, 3)) if (timeSpend < 2) else 0)



JsonExamList = {}
JsonExamLock = threading.RLock()
def JsonExam(path):
    with JsonExamLock:
        if path in JsonExamList:
            return JsonExamList[path]
        else:
            return _JsonExam(path)

class _JsonExam:
    def __init__(self, path):
        with open(path, "r", encoding = "utf-8") as file:
            self.data = json.load(file)
            self.data["examInfo"]["examName"] = self.data["examInfo"]["name"]
            del self.data["examInfo"]["name"]
        JsonExamList[path] = self
    def getExamInfo(self):
        return self.data["examInfo"]
    def getReportUpdateTime(self):
        return 1742199433
    def getExamStudentScore(self, userID, is_forcely_get, progressFunc, studentInfoDict):
        studentName = studentInfoDict["studentName"]
        for studentID, student in self.data["studentList"].items():
            studentSchoolID = student["schoolID"]
            if studentSchoolID != "湖南师大附中":
                continue
            if studentName != student["name"]:
                continue
            studentClassID = student["classID"]
            break
        else:
            raise ZhiXueFletError(f"无法找到学生 {studentName}")
        studentSchoolName = self.data["schoolList"][studentSchoolID]["name"]
        studentClassName = self.data["classList"][studentClassID]["name"]
        result = {
            "studentInfo": {
                "studentName": studentName,
                "studentCode": studentID,
                "studentSchoolID": studentSchoolID,
                "studentSchoolName": studentSchoolName,
                "studentClassID": studentClassID,
                "studentClassName": studentClassName
            },
            "examInfo": {},
            "subjectList": {}
        }
        for subjectID, subject in self.data["subjectList"].items():
            if studentClassID in self.data["subjectRankList"][subjectID]["class"]:
                class_ = self.data["subjectRankList"][subjectID]["class"][studentClassID]
            else:
                class_ = {}
            if studentSchoolID in self.data["subjectRankList"][subjectID]["school"]:
                school = self.data["subjectRankList"][subjectID]["school"][studentSchoolID]
            else:
                school = {}
            union  = self.data["subjectRankList"][subjectID]["total"]
            subjectName = subject["name"]
            subject_is_assign = subject["is_assign"]
            if studentID in self.data["subjectRankList"][subjectID]["student"]:
                student = self.data["subjectRankList"][subjectID]["student"][studentID]
                result["subjectList"][subjectID] = {
                    "subjectName": subjectName,
                    "subjectStandardScore": subject["standardScore"],
                    "subjectMarkingStatus": zhixue.EXAM_SUBJECT_MARKING_STATUS_4,
                    "subjectMarkingProgress": 1,
                    "subject_is_finished": True,
                    "subject_is_assign": subject["is_assign"],
                    "studentScore": student["score"],
                    "studentScoreAssign": student.get("scoreAssign", 0),
                    "is_studentScore_removed": student["removed"],
                    'studentNumAll': union['studentNumValid'],
                    'studentNumSchool': school['studentNumValid'],
                    'studentNumClass': class_['studentNumValid'],
                    'studentScoreRankAll': student['rankAll'],
                    'studentScoreRankSchool': student['rankSchool'],
                    'studentScoreRankClass': student['rankClass'],
                    'schoolNum': len(self.data["subjectRankList"][subjectID]["school"]),
                    'classNumAll': union["classNum"],
                    'classNumSchool': school["classNum"],
                    'scoreAverageAll': union["scoreAverageValid"],
                    'scoreAverageSchool': school["scoreAverageValid"],
                    'scoreAverageClass': class_["scoreAverageValid"],
                    'scoreAverageSchoolRank': school["rankAll"],
                    'scoreAverageClassRankAll': class_["rankAll"],
                    'scoreAverageClassRankSchool': class_["rankSchool"]
                }
            else:
                result["subjectList"][subjectID] = {
                    "subjectName": subjectName,
                    "subjectStandardScore": subject["standardScore"],
                    "subjectMarkingStatus": zhixue.EXAM_SUBJECT_MARKING_STATUS_4,
                    "subjectMarkingProgress": 1,
                    "subject_is_finished": True,
                    "subject_is_assign": subject["is_assign"],
                    "studentScore": None,
                    "studentScoreAssign": None,
                    "is_studentScore_removed": True,
                    'studentNumAll': union['studentNumValid'],
                    'studentNumSchool': school.get('studentNumValid', None),
                    'studentNumClass': class_.get('studentNumValid', None),
                    'studentScoreRankAll': union['studentNumValid'] +1,
                    'studentScoreRankSchool': school.get('studentNumValid', -1) +1,
                    'studentScoreRankClass': class_.get('studentNumValid', -1) +1,
                    'schoolNum': len(self.data["subjectRankList"][subjectID]["school"]),
                    'classNumAll': union["classNum"],
                    'classNumSchool': school.get("classNum", 0),
                    'scoreAverageAll': union["scoreAverageValid"],
                    'scoreAverageSchool': school.get("scoreAverageValid", None),
                    'scoreAverageClass': class_.get("scoreAverageValid", None),
                    'scoreAverageSchoolRank': school.get("rankAll", None),
                    'scoreAverageClassRankAll': class_.get("rankAll", None),
                    'scoreAverageClassRankSchool': class_.get("rankSchool", None)
                }
            if (not subject_is_assign) or subjectID == "score":
                del result["subjectList"][subjectID]["studentScoreAssign"]
        return result
        # {'examInfo': {'examName': '22级高三九校联考3.14（赋分）', 'examType': '月考', 'gradeName': '高三年级', 'exam_is_finished': True, 'exam_is_assign': False, 'exam_is_single_subject': False, 'updateTime': 1742203471.0},
        #  'subjectList':
        #      {'score':
        #           }, '853c9437-0989-49fc-84e7-5d9ed16462b4': {'subjectName': '语文', 'subjectStandardScore': 150, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': 112.5, 'is_studentScore_removed': False, 'studentScoreRankAll': 318, 'studentNumAll': 1176, 'studentScoreRankSchool': 318, 'studentNumSchool': 1176, 'studentScoreRankClass': 8, 'studentNumClass': 48, 'schoolNum': 1, 'classNumAll': 29, 'classNumSchool': 29, 'scoreAverageAll': 107.08, 'scoreAverageSchool': 107.08, 'scoreAverageClass': 104.62, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 21, 'scoreAverageClassRankSchool': 21}, 'b3d92c5d-978c-4e9b-8e78-423d2407910d': {'subjectName': '数学', 'subjectStandardScore': 150, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': 0, 'is_studentScore_removed': True, 'studentScoreRankAll': 1170, 'studentNumAll': 1169, 'studentScoreRankSchool': 1170, 'studentNumSchool': 1169, 'studentScoreRankClass': 47, 'studentNumClass': 46, 'schoolNum': 1, 'classNumAll': 29, 'classNumSchool': 29, 'scoreAverageAll': 94.02, 'scoreAverageSchool': 94.02, 'scoreAverageClass': 93.35, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 16, 'scoreAverageClassRankSchool': 16}, 'f33fcef6-8ea8-46a5-96ea-e4973b73be6e': {'subjectName': '英语', 'subjectStandardScore': 150, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': 0, 'is_studentScore_removed': True, 'studentScoreRankAll': 1172, 'studentNumAll': 1171, 'studentScoreRankSchool': 1172, 'studentNumSchool': 1171, 'studentScoreRankClass': 48, 'studentNumClass': 47, 'schoolNum': 1, 'classNumAll': 29, 'classNumSchool': 29, 'scoreAverageAll': 123.16, 'scoreAverageSchool': 123.16, 'scoreAverageClass': 120.69, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 21, 'scoreAverageClassRankSchool': 21}, '2d854350-49e8-49f8-b879-f31e2d2a555b': {'subjectName': '物理', 'subjectStandardScore': 100, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': None, 'is_studentScore_removed': True, 'studentScoreRankAll': 975, 'studentNumAll': 974, 'studentScoreRankSchool': 975, 'studentNumSchool': 974, 'studentScoreRankClass': 48, 'studentNumClass': 47, 'schoolNum': 1, 'classNumAll': 24, 'classNumSchool': 24, 'scoreAverageAll': 56.93, 'scoreAverageSchool': 56.93, 'scoreAverageClass': 49.89, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 20, 'scoreAverageClassRankSchool': 20}, '750572e4-1d86-4553-9bd0-10bde4a7f0d0': {'subjectName': '化学', 'subjectStandardScore': 100, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': None, 'is_studentScore_removed': True, 'studentScoreRankAll': 966, 'studentNumAll': 965, 'studentScoreRankSchool': 966, 'studentNumSchool': 965, 'studentScoreRankClass': 48, 'studentNumClass': 47, 'schoolNum': 1, 'classNumAll': 24, 'classNumSchool': 24, 'scoreAverageAll': 82.08, 'scoreAverageSchool': 82.08, 'scoreAverageClass': 78.81, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 16, 'scoreAverageClassRankSchool': 16}, '05b11df4-f2bc-49ac-b3f3-cd9d6f189ce6': {'subjectName': '生物', 'subjectStandardScore': 100, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': None, 'is_studentScore_removed': True, 'studentScoreRankAll': 795, 'studentNumAll': 794, 'studentScoreRankSchool': 795, 'studentNumSchool': 794, 'studentScoreRankClass': 1, 'studentNumClass': 0, 'schoolNum': 1, 'classNumAll': 24, 'classNumSchool': 24, 'scoreAverageAll': 85.13, 'scoreAverageSchool': 85.13, 'scoreAverageClass': 0, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 25, 'scoreAverageClassRankSchool': 25}, '1fbbea5f-7fba-44c9-b5f3-dae2ab521f6c': {'subjectName': '政治', 'subjectStandardScore': 100, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': None, 'is_studentScore_removed': True, 'studentScoreRankAll': 240, 'studentNumAll': 239, 'studentScoreRankSchool': 240, 'studentNumSchool': 239, 'studentScoreRankClass': 1, 'studentNumClass': 0, 'schoolNum': 1, 'classNumAll': 8, 'classNumSchool': 8, 'scoreAverageAll': 82.05, 'scoreAverageSchool': 82.05, 'scoreAverageClass': 0, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 9, 'scoreAverageClassRankSchool': 9}, 'ed284919-5959-496f-83b2-715d767b5fc7': {'subjectName': '历史', 'subjectStandardScore': 100, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': None, 'is_studentScore_removed': True, 'studentScoreRankAll': 197, 'studentNumAll': 196, 'studentScoreRankSchool': 197, 'studentNumSchool': 196, 'studentScoreRankClass': 1, 'studentNumClass': 0, 'schoolNum': 1, 'classNumAll': 6, 'classNumSchool': 6, 'scoreAverageAll': 63.38, 'scoreAverageSchool': 63.38, 'scoreAverageClass': 0, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 7, 'scoreAverageClassRankSchool': 7}, '32e13883-6452-426e-b4b2-adb0ca13ec54': {'subjectName': '地理', 'subjectStandardScore': 100, 'subjectMarkingStatus': 'm1initStatus', 'subjectMarkingProgress': 0, 'subject_is_finished': True, 'subject_is_assign': False, 'studentScore': None, 'is_studentScore_removed': True, 'studentScoreRankAll': 347, 'studentNumAll': 346, 'studentScoreRankSchool': 347, 'studentNumSchool': 346, 'studentScoreRankClass': 48, 'studentNumClass': 47, 'schoolNum': 1, 'classNumAll': 16, 'classNumSchool': 16, 'scoreAverageAll': 81.37, 'scoreAverageSchool': 81.37, 'scoreAverageClass': 82.81, 'scoreAverageSchoolRank': 1, 'scoreAverageClassRankAll': 9, 'scoreAverageClassRankSchool': 9}}}



if __name__ == "__main__":
    StoppableThread(target = _consoleThread, name = "处理控制台输入代码", daemon = True)
    StoppableThread(target = deadLockDetectThread, name = "死锁检测", daemon = True)
    os.environ["FLET_SESSION_TIMEOUT"] = "60"
    os.environ["FLET_DISPLAY_URL_PREFIX"] = "网页已成功启动于"
    flet.app(target = ZhiXueFlet, port = 5773, assets_dir = ".", view = flet.AppView.WEB_BROWSER, web_renderer = flet.WebRenderer.CANVAS_KIT, use_color_emoji = True)
    print("等待所有操作停止.")
    frequencySetLock.acquire()
    for lock in (ZhiXueLockList):
        lock.acquire(timeout = 5.773)
    for stoppableThread in stoppableThreadList[::-1]:
        waitUntilStopped = not stoppableThread.name.startswith("ZhiXueFlet_")
        stoppableThread.stop(False)
    [time.sleep(0.1) for _ in range(50) if stoppableThreadList]
    input("按回车键退出...\n")
