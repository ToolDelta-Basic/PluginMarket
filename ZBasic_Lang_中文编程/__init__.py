# ToolDelta-ZBasic 中文编程
# 本插件由 SuperScript (2528622340@qq.com) 制作
# 未经作者允许, 请勿在插件以外的地方使用
# 编译器和执行器仅供插件内部私用
# 若需单独提取插件内的编译器和执行器, 请联系作者

# 导入 ToolDelta 框架
import os

# 标准库
import random
import shutil
import time

# 需要的类型
from typing import Optional
from collections.abc import Callable

from basic_codes import CodeSyntaxError, CompiledCode, CustomCodeUnit
from basic_types import *
from compiler import COMPILER, EXECUTOR, compile, extend_codes
from executor import run, set_game_ctrl

# 表达式解析器, 编译器和执行器
# 命令和函数注册器
from syntax_compile import get_final_type, multi_parse, parse, register_func_syntax
from syntax_lib import ConstPtr
from tooldelta import Frame, Plugin, Print, Utils, constants, game_utils, plugins

@plugins.add_plugin_as_api("ZBasic")
class ToolDelta_ZBasic(Plugin):
    name = "ZBasic-中文Basic语言"
    author = "SuperScript"
    version = (0, 0, 5)

    def __init__(self, frame: Frame):
        super().__init__(frame)
        self.create_dirs()
        self.scripts = {
            "启动": {},
            "玩家进入": {},
            "玩家退出": {},
            "玩家发言": {},
            "玩家死亡": {}
        }
        self.threads: list[Utils.createThread] = []
        self.reload_cbs = []

    # ------------------------------- API ----------------------------

    CodeSyntaxError = CodeSyntaxError
    OptionalType = OptionalType
    CustomCodeUnit = CustomCodeUnit
    CompiledCode = CompiledCode
    ConstPtr = ConstPtr

    ANY = ANY
    STRING = STRING
    NUMBER = NUMBER
    NULL = NULL
    BOOLEAN = BOOLEAN
    LIST = LIST

    class Special:
        ZHCN_TYPE = zhcn_type
        get_zhcn_type = staticmethod(get_zhcn_type)

    def add_reload_cb(self, cb: Callable[[], None]):
        """
        添加一个重载脚本监听器

        Args:
            cb (Callable): 监听器
        """
        self.reload_cbs.append(cb)

    def get_type(self, syntax: Any) -> ANY_TYPE:
        """
        获取表达式的最终传出值类型

        Args:
            syntax (Any): 解析后的表达式

        Returns:
            ANY_TYPE: 类型
        """
        return get_final_type(syntax)

    def parse_syntax(self, syntax: str, local_vars_register: REGISTER):
        """
        解析单个表达式字符串为表达式类

        Args:
            syntax (str): 表达式字符串
            local_vars_register (REGISTER): 变量命名空间

        Returns:
            Any: 解析完成的表达式
        """
        return parse(syntax, local_vars_register)

    def parse_syntax_multi(self, syntax: str, local_vars_register: REGISTER) -> list:
        """
        解析以 ; 分隔的表达式字符串为表达式组

        Args:
            syntax (str): 表达式字符串
            local_vars_register (REGISTER): 变量命名空间

        Returns:
            Any: 解析完成的表达式列表
        """
        return multi_parse(syntax, local_vars_register)

    def compile(self, code_string: str, local_vars_register: Optional[REGISTER] = None) -> "CompiledCode":
        """
        编译代码

        Args:
            code (str): 待编译的代码
            local_vars_register (REGISTER | None): 初始全局变量类型表

        Returns:
            CompiledCode: 编译好的代码

        Raises:
            CodeSyntaxError: 编译中代码的错误
        """
        if local_vars_register is None:
            local_vars_register = {}
        return compile(code_string, local_vars_register)

    def run(self, cmp_code: CompiledCode, local_vars: VAR_MAP):
        """
        执行编译后的代码

        Args:
            cmp_code (CompiledCode): 编译代码
            local_vars (VAR_MAP): 初始全局变量

        Returns:
            Signal (int): 代码执行完毕的返回状态, 1=正常退出, 100=被迫退出
        """
        return run(cmp_code, local_vars)

    def register_cmd_syntax(
        self,
        cmd: str,
        compiler: COMPILER,
        executor: EXECUTOR
    ):
        """
        注册一条语句

        Args:
            cmd (str): 语句命令
            compiler (COMPILER): 编译器, 传入参数和本地命名空间表, 传出`CodeUnit`
            executor (EXECUTOR): 执行器, 传入`CodeUnit`和本地变量表
        """
        extend_codes.add_cmd(cmd, compiler, executor)

    def register_func_syntax(
        self,
        func_name: str,
        restype: ANY_TYPE | Callable[[tuple[ANY_TYPE, ...]], ANY_TYPE],
        input_type_checker: Callable[[list[ANY_TYPE]], str | None] | tuple[ANY_TYPE, ...],
        func: Callable[..., Any]
    ):
        """
        注册一个函数

        Args:
            func_name (str): 函数名
            restype (BasicType | OptionalType): 返回类型
            input_type_checker ((list[ANY_TYPE]) -> None | str): 参数类型检查器, 检查不通过则返回所需参数类型的提示, 如 "字符串, 数值"
                e.g. `lambda t: None if t[0]==STRING and t[1]==NUMBER else "字符串, 数值"`
            func ((...) ->): 代码被执行时传入参数, 将返回作为表达式的计算结果
        """
        register_func_syntax(func_name, restype, input_type_checker, func)

    # ------------------------------------------------------------------------------

    def create_dirs(self):
        fdir = os.path.join(constants.TOOLDELTA_PLUGIN_DATA_DIR, "ZBasic中文脚本语言")
        if not os.path.isdir(fdir):
            os.mkdir(fdir)
            c_dir = os.path.join(os.path.dirname(__file__), "示例代码")
            for dir in os.listdir(c_dir):
                try:
                    shutil.copytree(
                        os.path.join(c_dir, dir),
                        fdir
                    )
                except Exception:
                    pass
        os.makedirs(os.path.join(fdir, "脚本文件"), exist_ok=True)
        os.makedirs(os.path.join(fdir, "数据文件"), exist_ok=True)

    def load_scripts(self):
        join = os.path.join
        isfile = os.path.isfile
        scripts: dict[str, dict[str, CompiledCode]] = self.scripts
        try:
            for filedir in os.listdir(join("插件数据文件", "ZBasic中文脚本语言", "脚本文件")):
                src_dir = os.path.join("插件数据文件", "ZBasic中文脚本语言", "脚本文件", filedir)
                fn = join(src_dir, "启动.txt")
                if isfile(fn):
                    with open(fn, "r", encoding="utf-8") as f:
                        scripts["启动"][filedir] = self.compile(f.read(), {})
                fn = join(src_dir, "玩家进入.txt")
                if isfile(fn):
                    with open(fn, "r", encoding="utf-8") as f:
                        scripts["玩家进入"][filedir] = self.compile(f.read(), {"玩家名": STRING})
                fn = join(src_dir, "玩家退出.txt")
                if isfile(fn):
                    with open(fn, "r", encoding="utf-8") as f:
                        scripts["玩家退出"][filedir] = self.compile(f.read(), {"玩家名": STRING})
                fn = join(src_dir, "玩家发言.txt")
                if isfile(fn):
                    with open(fn, "r", encoding="utf-8") as f:
                        scripts["玩家发言"][filedir] = self.compile(f.read(), {"玩家名": STRING, "消息": STRING})
                fn = join(src_dir, "玩家死亡.txt")
                if isfile(fn):
                    with open(fn, "r", encoding="utf-8") as f:
                        scripts["玩家死亡"][filedir] = self.compile(f.read(), {"玩家名": STRING, "击杀者": STRING})
                Print.print_suc(f"[ZBasic] 已载入脚本 {filedir}.")
        except CodeSyntaxError as e:
            import traceback
            traceback.print_exc()
            Print.print_err(f"中文脚本 {'/'.join(fn.split(os.sep)[3:])} 编译出现问题:")
            Print.print_err(str(e))
            Print.print_inf("修复后在控制台输入 重载脚本 即可再次载入")
        self.scripts = scripts

    def init(self):
        self.on_init_counter = ZBasic_TasksCounter("启动")
        self.on_player_join_counter = ZBasic_TasksCounter("玩家进入")
        self.on_player_leave_counter = ZBasic_TasksCounter("玩家退出")
        self.on_player_message_counter = ZBasic_TasksCounter("玩家发言")
        self.on_player_death_counter = ZBasic_TasksCounter("玩家死亡")

    def init_basic_funcs(self):
        # 注入Builtins函数
        self.register_func_syntax("取整", NUMBER, (NUMBER,), lambda x:int(x))
        self.register_func_syntax("随机整数", NUMBER, (NUMBER, NUMBER), lambda x, y:random.randint(int(x), int(y)))
        self.register_func_syntax("为空变量", BOOLEAN, lambda x:None if (len(x) == 1 and isinstance(x[0], OptionalType)) else "可空变量[任意类型]", lambda x:x==None)
        self.register_func_syntax("转换为整数", OptionalType(NUMBER), (STRING,), lambda x:Utils.try_int(x))
        self.register_func_syntax("当前系统时间戳", NUMBER, (), lambda:time.time())
        self.register_func_syntax("以字符串开头", BOOLEAN, (STRING, STRING), lambda x,y:x.startswith(y))
        self.register_func_syntax("以字符串结尾", BOOLEAN, (STRING, STRING), lambda x,y:x.endswith(y))
        self.register_func_syntax("字符串长度", NUMBER, (STRING,), lambda x:len(x))
        self.register_func_syntax("列表长度", NUMBER, (LIST[ANY],), lambda x:len(x))
        self.register_func_syntax("切割字符串", LIST[STRING], (STRING, STRING), lambda x,y:x.split(y))
        self.register_func_syntax("获取列表项", lambda l:OptionalType(l[0].type.extra1), (LIST[ANY], NUMBER), lambda l,i:l[int(i)] if int(i) in range(len(l)) else None)

    def init_advanced_funcs(self):
        # 注入高级Builtins函数
        def _get_scb_score(s: str, t: str):
            try:
                return game_utils.getScore(s, t)
            except Exception as err:
                Print.print_war(f"ZBasic: 获取计分板 {s} 上 {t} 的分数失败: {err}")
                return None
        def _cmd_res(cmd: str):
            try:
                return game_utils.isCmdSuccess(cmd)
            except TimeoutError:
                Print.print_err(f"ZBasic: {cmd[:10]}.. 指令返回超时")
                return False
        def _get_pos(t: str):
            try:
                x, y, z = game_utils.getPosXYZ(t)
                return (x, y, z)
            except Exception as e:
                Print.print_err(f"ZBasic: 获取目标 {t} 的坐标失败: {e}")
                return None
        def _de_optional_check(x: list):
            if len(x) not in (1, 2) or not isinstance(x[0], OptionalType):
                return "可空[任意类型] [, 默认值:任意类型]"
            elif len(x) == 2 and (gft := x[1]) != x[0].type:
                return f"可空[任意类型(当前为{gft})] [, 默认值(当前可用的):{gft}]"
            return None
        def _de_optional(t: None | Any, default: Any = None):
            if t is None:
                if default is None:
                    raise SystemExit
                else:
                    return default
            else:
                return t

        self.register_func_syntax("获取计分板分数", OptionalType(NUMBER), (STRING, STRING), _get_scb_score)
        self.register_func_syntax("指令执行成功", BOOLEAN, (STRING,), _cmd_res)
        self.register_func_syntax("获取目标坐标", OptionalType(POSITION), (STRING,), _get_pos)
        self.register_func_syntax("玩家在线", BOOLEAN, (STRING,), lambda x:x in self.game_ctrl.allplayers)
        self.register_func_syntax("在线玩家列表", LIST[STRING], (), lambda :self.game_ctrl.allplayers.copy())
        self.register_func_syntax("转换为非空变量", lambda x:x[0].type, _de_optional_check, _de_optional)

    def reload(self):
        for v in self.scripts.values():
            v.clear()
        for i in self.threads:
            i.stop()
        for cb in self.reload_cbs:
            cb()
        self.load_scripts()
        self.new_thread("启动时执行ZBasic脚本", self.execute_init)
        Print.print_suc("ZBasic脚本重载成功")

    def new_thread(self, name: str, func: Callable, args = ()):
        def _thread():
            try:
                func(*args)
            finally:
                # don't remove it
                time.sleep(0.01)
                self.threads.remove(thread)
        thread = Utils.createThread(_thread, (), name)
        self.threads.append(thread)

    def execute_loaded_script(self, clsfy: str, local_vars: VAR_MAP):
        try:
            for script_name, code in self.scripts[clsfy].items():
                run(code, local_vars)
        except CodeSyntaxError as err:
            Print.print_err(f"执行脚本文件 {script_name}/{clsfy} 出现问题: {err}")

    def on_def(self):
        self.init()
        self.init_basic_funcs()
        self.init_advanced_funcs()
        set_game_ctrl(self.game_ctrl)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(["重载脚本"], None, "重载所有ZBasic脚本", lambda _:self.reload())
        self.frame.add_console_cmd_trigger(["脚本线程"], None, "查看正在运行的脚本线程", self.check_threads)
        for t in self.threads:
            t.stop()
        self.load_scripts()
        self.new_thread("启动时执行ZBasic脚本", self.execute_init)

    def on_player_join(self, player: str):
        self.new_thread("玩家进入时执行ZBasic脚本", self.execute_player_join, (player,))

    def on_player_leave(self, player: str):
        self.new_thread("玩家退出时执行ZBasic脚本", self.execute_player_leave, (player,))

    def on_player_message(self, player: str, msg: str):
        self.new_thread("玩家发言时执行ZBasic脚本", self.execute_player_message, (player, msg))

    def on_player_death(self, player: str, killer: str | None, _):
        self.new_thread("玩家死亡时执行ZBasic脚本", self.execute_player_death, (player, killer or ""))

    def check_threads(self, _):
        Print.print_inf("目前正在运行的ZBasic脚本线程:")
        if self.threads == []:
            Print.print_inf(" - 无")
            return
        for i in self.threads:
            Print.print_inf(f" - {i.name}")

    def execute_init(self):
        with self.on_init_counter:
            self.execute_loaded_script("启动", {})

    def execute_player_join(self, player: str):
        with self.on_player_join_counter:
            self.execute_loaded_script("玩家进入", {"玩家名": player})

    def execute_player_leave(self, player: str):
        with self.on_player_leave_counter:
            self.execute_loaded_script("玩家退出", {"玩家名": player})

    def execute_player_message(self, player: str, msg: str):
        with self.on_player_message_counter:
            self.execute_loaded_script("玩家发言", {"玩家名": player, "消息": msg})

    def execute_player_death(self, player: str, killer: str):
        with self.on_player_death_counter:
            self.execute_loaded_script("玩家发言", {"玩家名": player, "击杀者": killer})

class ZBasic_TasksCounter:
    def __init__(self, name: str):
        self.name = name
        self.tasks = 0

    def __enter__(self):
        self.tasks += 1
        if self.tasks >= 15:
            Print.print_war(f"ZBasic: {self.name}线程任务数大于15, 可能是脚本内有死循环")
        if self.tasks >= 31:
            Print.print_err(f"ZBasic {self.name}线程任务数大于31, 已被迫终止")
            raise SystemExit
        return self

    def __exit__(self, _, _2, _3):
        self.tasks -= 1
        if _2:
            Print.print_war(f"脚本执行线程 {self.name} 被迫中断")