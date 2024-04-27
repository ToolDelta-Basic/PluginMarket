import re, time, os, random
from typing import Any, Callable

from tooldelta import Frame, Plugin, plugins, Config, Builtins, Print

from syntax_compile import (
    parse as syntax_parse,
    deal_stxgrp,
    get_final_type,
    register_func_syntax,
    register_var,
    fun_stxs
)
from syntax_lib import (
    OpPtr,
    FuncPtr,
    VarPtr
)
from basic_types import *
from utils import (
    is_valid_num,
    is_valid_str,
    auto_to_type_r,
    split_by_quote,
    to_number,
    to_string
)

tmpjson = Builtins.TMPJson

@plugins.add_plugin_as_api("TD中文Basic")
class Compiler(Plugin):
    name = "ZDelta-中文Basic语言"
    author = "SuperScript"
    version = (0, 1, 1)

    class ScriptExit(Exception):...
    class PlayerExitInterrupt(ScriptExit):...
    class SelectTimeout(ScriptExit):...

    ruleFindStrVar = re.compile(r'([^ ]*?)="([^"]*)"')
    ruleFindIntVar = re.compile(r'([^ ]*?)=([0-9]+)')

    # ---------------- API ------------------

    STRING = STRING
    NUMBER = NUMBER
    NULL = NULL

    def add_command(
            self,
            cmd: str,
            cmd_valid_checker: Callable[[list[str]], bool],
            executer: Callable
        ):
        """
        扩展 TD-中文Basic 的语法, 添加命令语句
        !此方法暂时不能使用!
        参数:
            cmd: 指令名
            cmd_valid_checker: 函数, 检查传入的指令参数是否合法, 不合法可使用 assert 引发报错提示
            executer: 接收参数并执行的方法
        """
        self.commands_id_hashmap[hash(cmd)] = executer
        self.reg_cmds_with_checkers[cmd] = cmd_valid_checker

    def add_func_ptr(
            self,
            name: str,
            args_checker: Callable[[list[int]], None | str] = lambda _:None,
            return_type: BasicType | OptionalType = NULL,
            callback: Callable = lambda _:None
        ):
        """
        向 TD-中文Basic 添加函数, 扩展函数库
        参数:
            name: 函数名
            args_checker: 参数类型检测器, 传入参数类型列表(用int表示), 合法返回None, 不合法返回字符串(报错消息)
            return_type: 返回的值的类型
                e.g. return_type = api.STRING # 返回值为字符串
            callback: 接受参数, 并返回结果
                e.g. callback = lambda x:round(x) # 实现四舍五入的功能
        """
        if self.reg_func_ptrs.get(name):
            raise ValueError("注册了重复的函数表达式名: " + name)
        register_func_syntax(name, return_type, args_checker)
        self.reg_func_ptrs[name] = callback

    # ------------------------------------------

    def __init__(self, f: Frame):
        self.frame = f
        self.game_ctrl = f.get_game_control()
        self.commands_id_hashmap = {}
        self.reg_cmds_with_checkers = {}
        self.reg_func_ptrs: dict[str, Callable] = {}
        self.pre_register_vars: dict[str, int] = {}
        self.builtins_register_vars = {"空变量": NULL}
        self.evt_scripts = {
            "injected": {},
            "player_message": {},
            "player_join": {},
            "player_leave": {}
        }
        self.make_dirs()
        self.add_basic_functions()

    def add_basic_functions(self):
        # 基础函数
        self.add_func_ptr(
            "取整", lambda x:None if (len(x)==1 and x[0]==NUMBER) else "数值",
            NUMBER,
            lambda x:int(x)
        )
        self.add_func_ptr(
            "四舍五入", lambda x:None if(len(x)==1 and x[0]==NUMBER) else "数值",
            NUMBER,
            lambda x:round(x)
        )
        self.add_func_ptr(
            "随机整数", lambda x:None if(len(x)==2 and x[0]==x[1]==NUMBER) else "数值 数值",
            NUMBER,
            lambda x,y:random.randint(int(x), int(y)) if x<y else 0
        )
        self.add_func_ptr(
            "是否为空变量", lambda x:None if len(x)==1 else "任意变量",
            NUMBER,
            lambda x:x is None
        )
        self.add_func_ptr(
            "当前系统时间戳",
            return_type=NUMBER,
            callback=lambda :int(time.time())
        )
        self.add_func_ptr(
            "格式化时间", lambda x:None if x[0]==STRING else "字符串",
            STRING,
            lambda t:time.strftime(t)
        )


    def load_scripts(self):
        script_path = os.path.join(self.data_path, "脚本文件")
        for script_folder in os.listdir(script_path):
            fopath = os.path.join(self.data_path, "脚本文件", script_folder)
            err = 0
            for file in os.listdir(fopath):
                match file:
                    case "启动.txt":
                        with open(fopath + "/" + "启动.txt", "r", encoding="utf-8") as f:
                            self.evt_scripts["injected"][fopath], err = self.script_parse(f.read())
                    case "玩家进入.txt":
                        with open(fopath + "/" + "玩家进入.txt", "r", encoding="utf-8") as f:
                            self.evt_scripts["player_join"][fopath], err = self.script_parse(f.read(), {"玩家名": STRING})
                    case "玩家退出.txt":
                        with open(fopath + "/" + "玩家退出.txt", "r", encoding="utf-8") as f:
                            self.evt_scripts["player_leave"][fopath], err = self.script_parse(f.read(), {"玩家名": STRING})
                    case "玩家发言.txt":
                        with open(fopath + "/" + "玩家发言.txt", "r", encoding="utf-8") as f:
                            self.evt_scripts["player_message"][fopath], err = self.script_parse(f.read(), {"玩家名": STRING, "消息": STRING})
                if err is None:
                    Print.print_suc(f"ToolDelta-中文Basic: 已加载脚本: {fopath}/{file}")
                elif err == 0:
                    Print.print_war(f"ToolDelta-中文Basic: 脚本文件夹为空: {fopath}")
                else:
                    Print.print_err(f"ToolDelta-中文Basic: 加载脚本 {fopath}/{file} 出现问题:\n" + str(err.args[0]))
                    raise SystemExit

    def get_player_plot_path(self, player: str) -> str:
        return self.data_path + f"/player_vars/{player}.json"

    def param_2_dict(self, re_str):
        # 识别变量赋值表达式
        res = {}
        re_list1 = self.ruleFindIntVar.findall(re_str)
        re_list2 = self.ruleFindStrVar.findall(re_str)
        for k, v in re_list1:
            res[k] = int(v)
        for k, v in re_list2:
            res[k] = v
        return res

    def on_def(self):
        self.funclib = plugins.get_plugin_api("基本插件功能库")
        Print.print_load("§bToolDelta §a中文Basic语言 §fV" + ".".join(str(i) for i in self.version))
        Print.print_load("§b使用TDBasic, 小白也会写插件!")
        Print.print_load("交流群(ToolDelta官方群聊): 194838530")
        self.load_scripts()
        self.frame.add_console_cmd_trigger(["重载中文脚本"], None, "重新载入所有ZBasic中文脚本", self.reload_all)

    def on_inject(self):
        self.frame.add_console_cmd_trigger(["test-l&j"], "玩家名", "测试中文脚本的玩家进入和退出脚本", self.test_player_leave_and_join)
        for k, v in self.evt_scripts["injected"].items():
            self.run_script(v, {})

    def on_player_join(self, player: str):
        for k, v in self.evt_scripts["player_join"].items():
            self.run_script(v, {"玩家名": player})

    def on_player_leave(self, player: str):
        for k, v in self.evt_scripts["player_leave"].items():
            self.run_script(v, {"玩家名": player})

    def on_player_message(self, player: str, msg: str):
        for k, v in self.evt_scripts["player_message"].items():
            self.run_script(v, {"玩家名": player, "消息": msg})

    def test_player_leave_and_join(self, p: list[str]):
        if len(p) != 1:
            Print.print_war("菜单关键词: 玩家名")
            return
        player = p[0]
        if player not in self.game_ctrl.allplayers:
            Print.print_war(f"玩家不在玩家列表: {player}")
            return
        Print.print_inf("正在执行 玩家退出的所有脚本..")
        for k, v in self.evt_scripts["player_leave"].items():
            self.run_script(v, {"玩家名": player})
        Print.print_inf("正在执行 玩家加入的所有脚本..")
        for k, v in self.evt_scripts["player_join"].items():
            self.run_script(v, {"玩家名": player})
        Print.print_suc("执行完成.")

    @Builtins.new_thread
    def run_script(self, script_code, args_dict):
        self.execute_script(script_code, args_dict)

    def make_dirs(self):
        os.makedirs(os.path.join(self.data_path, "player_vars"), exist_ok = True)
        os.makedirs(os.path.join(self.data_path, "脚本文件"), exist_ok = True)

    def script_parse(self, scripts: str, pre_variables_reg: None | dict = None):
        """
        将脚本编译为执行器可以执行的命令序列.
        (ID)
        退出: 0, 跳转: 1, 执行: 2
        设定: 3, 判断: 4, 等待: 5,
        导出变量: 6, 读取变量: 7, 输出: 8
        """
        scr_lines: list[tuple[int, list[str]]] = []
        cmp_scripts = []
        loc_vars_register: dict[str, BasicType | OptionalType] = self.builtins_register_vars # type: ignore
        scr_lines_finder: dict[int, int] = {}
        now_line_counter = 0
        # 注册初始变量的类型: 0=int, 1=string, 2=空变量
        scr_lines_register = []
        if pre_variables_reg is not None:
            for k, v in pre_variables_reg.items():
                loc_vars_register[k] = v
        def _add_cmp(id: int, args = None):
            "添加操作码和参数"
            cmp_scripts.append((id, args))
        def _simple_assert_len(args, nlen):
            "简单地判断参数数量是否合法"
            assert len(args) == nlen, f"需要参数数量 {nlen} 个， 实际上 {len(args)} 个"
        def _simple_assert_ln(ln):
            "简单地判断代码行数是否合法"
            assert ln in scr_lines_register, f"不存在第 {ln} 行代码"
        def _check_defined(varname):
            if varname not in loc_vars_register.keys():
                raise NameError(f"变量名 {varname} 还未被赋值")
        _get_var_type = lambda varname : loc_vars_register[varname]
        try:
            rawlines = scripts.splitlines()
            for lett in rawlines:
                if not lett.strip() or lett.startswith("#"):
                    continue
                try:
                    linecount = int(lett.split()[0])
                    scr_lines_register.append(linecount)
                except ValueError:
                    return "", AssertionError(f"{lett.split()[0]} 不是有效的行数")
                cmds = split_by_quote(lett)[1:]
                if cmds == []:
                    return "", AssertionError(f"第 {lett.split()[0]} 行没有有效指令")
                scr_lines.append((linecount, cmds))
                scr_lines_finder[linecount] = now_line_counter
                now_line_counter += 1
        except Exception as err:
            return "", err
        try:
            for (ln, args) in sorted(scr_lines, key = lambda x: x[0]):
                match args[0]:
                    case "END" | "结束":
                        _simple_assert_len(args, 1)
                        _add_cmp(0)
                        # 结束
                    case "JUMP" | "跳转" | "跳转到":
                        _simple_assert_len(args, 2)
                        seq1 = int(args[1])
                        _simple_assert_ln(seq1)
                        _add_cmp(1, scr_lines_finder[seq1])
                        # 跳转到 <代码行数>
                    case "CMD" | "执行" | "执行指令":
                        assert len(args) > 1, "执行命令 至少需要2个参数"
                        seq1 = args[1]
                        if not is_valid_str(seq1):
                            raise AssertionError("执行 指令后需要作为MC指令的合法字符串(需要双引号括起来)")
                        _add_cmp(2, seq1)
                        # 执行 <mc指令>
                    case "SET" | "设定" | "设定变量" | "设置变量":
                        """
                        md: 0=const_int, 1=const_str, 2=表达式
                        md: 0=math_syntax, 1=str
                        md2: 0=int, 1=str
                        """
                        assert len(args) > 2, "设定命令 至少需要2个参数"
                        assert args[2] == "为", "语法错误"
                        varname = args[1]
                        syntax = " ".join(args[3:])
                        if is_valid_num(syntax):
                            is_constant = True
                            ftype = NUMBER
                            res = to_number(syntax)
                        elif is_valid_str(syntax):
                            is_constant = True
                            ftype = STRING
                            res = to_string(syntax)
                        else:
                            is_constant = False
                            try:
                                res = deal_stxgrp(syntax_parse(syntax, loc_vars_register))
                                ftype = get_final_type(res)
                                self.varcheck_exists(res, list(loc_vars_register.keys()))
                            except NameError as err:
                                raise AssertionError(f"表达式异常: {err}")
                            except SyntaxError as err:
                                raise AssertionError(f"表达式错误: {err}")
                        #else:
                        #    raise AssertionError(f"无法识别的表达式: " + " ".join(args[3:]))
                        old_t = loc_vars_register.get(varname)
                        assert not(
                            old_t is not None and old_t != ftype
                            ) or (isinstance(old_t, OptionalType) and old_t.type == ftype), "变量类型已被定义, 无法更改"
                        loc_vars_register[varname] = ftype
                        register_var(varname, ftype)
                        _add_cmp(3, (varname, is_constant, ftype, res))
                        # 设定变量 设定模式, 变量类型, 变量名[, 值]
                    case "IFS" | "判断":
                        # 判断 变量 操作符 变量 成立=跳转到??? 不成立=跳转到???
                        _simple_assert_len(args, 6)
                        arg1, arg1type, arg1_is_constant = auto_to_type_r(args[1], loc_vars_register)
                        arg2, arg2type, arg2_is_constant = auto_to_type_r(args[3], loc_vars_register)
                        if not arg1_is_constant:
                            _check_defined(arg1)
                        if not arg2_is_constant:
                            _check_defined(arg2)
                        match args[2]:
                            case "=" | "==": args[2] = 0 # type: ignore
                            case "!=" | "=!": args[2] = 1 # type: ignore
                            case "<": args[2] = 2 # type: ignore
                            case "<=": args[2] = 3 # type: ignore
                            case ">": args[2] = 4 # type: ignore
                            case ">=": args[2] = 5 # type: ignore
                            case _:
                                raise AssertionError("判断操作符只能为 <, >, ==, <=, >= !=")
                        assert args[4].startswith("成立=跳转到") and args[5].startswith("不成立=跳转到"), (
                            "判断命令: 第5、6个参数应为： 成立=跳转到<脚本行数>, 不成立=跳转到<脚本行数>"
                        )
                        if args[2] in [2, 3, 4, 5] and (arg1type != NUMBER or arg2type != NUMBER):
                            raise AssertionError(f"判断命令: 暂时只能比较数值变量大小, 也无法比较可能为空的变量: {get_typename_zhcn(arg1type)}, {get_typename_zhcn(arg2type)}")
                        try:
                            seq3 = int(args[4][6:])
                            seq4 = int(args[5][7:])
                            _simple_assert_ln(seq3)
                            _simple_assert_ln(seq4)
                        except ValueError:
                            raise AssertionError('"跳转到"指向的代码行数只能为纯数字')
                        _add_cmp(4, (arg1, arg1_is_constant, args[2], arg2, arg2_is_constant, scr_lines_finder[seq3], scr_lines_finder[seq4]))
                        # 变量1, 操作符, 变量2, 成立跳转, 不成立跳转
                    case "WAIT" | "等待":
                        _simple_assert_len(args, 2)
                        try:
                            seq1 = float(args[1])
                            assert seq1 > 0
                        except:
                            raise AssertionError(f"等待命令 参数应为正整数, 为秒数")
                        _add_cmp(5, seq1)
                    case "OUT-PRIVATE" | "导出个人变量" | "存储个人变量":
                        _simple_assert_len(args, 4)
                        if loc_vars_register.get("玩家名") is None:
                            raise AssertionError("此时无法存储玩家个人变量: 没有目标玩家")
                        assert args[2] == "->", "导出个人变量格式应为 内存变量名 -> 磁盘变量名"
                        _check_defined(args[1])
                        _add_cmp(6, (args[1], args[3]))
                    case "IN-PRIVATE" | "导入个人变量" | "读取个人变量":
                        _simple_assert_len(args, 6)
                        if loc_vars_register.get("玩家名") is None:
                            raise AssertionError("此时无法读取玩家个人变量: 没有目标玩家")
                        assert args[2] == "<-" and args[4] == "类型为" and args[5] in ["数值", "字符串"], "读取个人变量格式应为 内存变量名 <- 磁盘变量名 类型为 数值/字符串"
                        _add_cmp(7, (args[1], args[3]))
                        loc_vars_register[args[1]] = OptionalType(get_zhcn_type(args[5]))
                    case "PRINT" | "输出":
                        assert len(args) >= 2, f"输出 需要1个参数, 目前{len(args) - 1}个"
                        if not is_valid_str(args[1]):
                            raise ValueError("输出 命令需要一项参数: 输出内容(字符串)")
                        _add_cmp(8, to_string(args[1]))
                    case "SAY" | "聊天栏显示":
                        assert len(args) >= 3, f"聊天栏显示 需要2个参数, 目前{len(args) - 1}个"
                        if not is_valid_str(args[1]):
                            raise ValueError("聊天栏显示 第一项参数应为: 目标(字符串)")
                        if not is_valid_str(args[1]):
                            raise ValueError("聊天栏显示 第二项参数应为: 文本(字符串)")
                        _add_cmp(9, (to_string(args[1]), to_string(args[2])))
                    case "OUT-GLOBAL" | "导出公共变量" | "存储公共变量":
                        _simple_assert_len(args, 4)
                        assert args[2] == "->", "导出个人变量格式应为 内存变量名 -> 磁盘变量名"
                        _check_defined(args[1])
                        _add_cmp(10, (args[1], args[3]))
                    case "IN-GLOBAL" | "导入公共变量" | "读取公共变量":
                        _simple_assert_len(args, 6)
                        assert args[2] == "<-" and args[4] == "类型为" and args[5] in ["数值", "字符串"], "读取个人变量格式应为 内存变量名 <- 磁盘变量名 类型为 数值/字符串"
                        loc_vars_register[args[1]] = OptionalType(get_zhcn_type(args[5]))
                        _add_cmp(11, (args[1], args[3]))
                    case "IGNORE-NULL" | "忽略空变量":
                        _simple_assert_len(args, 2)
                        _check_defined(args[1])
                        old_t = _get_var_type(args[1])
                        if isinstance(old_t, OptionalType):
                            loc_vars_register[args[1]] = de_optional(old_t)
                        else:
                            raise AssertionError(f"变量 {args[1]} 不可能是空变量, 不需要忽略")
                    case _:
                        # 扩展命令
                        if args[0] in self.reg_cmds_with_checkers.keys():
                            cmd = args[0]
                            self.reg_cmds_with_checkers[cmd](len(args))
                            _add_cmp(hash(cmd), None if len(args) == 1 else args[1:])
                        else:
                            raise AssertionError(f"无法被识别的指令: {args[0]}")
            return cmp_scripts, None
        except (AssertionError, ValueError, SyntaxError) as err:
            return [], AssertionError(f"第{ln}行 出现问题: {err}")

    def execute_script(self, script_code, pre_variables: dict | None = None):
        """"
        执行传入的指令码.
        """
        # 保存指令执行位, DANGEROUS
        # last_save_pos = tmpjson.read(self.get_player_plot_path(player))["plots_progress"].get(plot_name)
        # if last_save_pos is not None:
        #     pointer = last_save_pos
        # else:
        #     pointer = 0
        if pre_variables is None:
            pre_variables = {}
        # 特殊类型: 玩家个人变量
        if pre_variables.get("玩家名") is not None:
            player = pre_variables["玩家名"]
            p_path = self.get_player_plot_path(player)
            tmpjson.loadPathJson(p_path, False)
            if tmpjson.read(p_path) is None:
                tmpjson.write(p_path, {})
        else:
            player = None
            p_path = None
        g_path = os.path.join(self.data_path, "全局变量.json")
        tmpjson.loadPathJson(g_path, False)
        if tmpjson.read(g_path) is None:
            tmpjson.write(g_path, {})
        pointer = 0
        loc_vars: dict[str, object] = {"空变量": None}
        if pre_variables is not None:
            loc_vars.update(pre_variables)
        plot_terminated = False
        try:
            while pointer < len(script_code):
                if plot_terminated:
                    raise self.SelectTimeout()
                if player is not None and not player in self.game_ctrl.allplayers:
                    raise self.PlayerExitInterrupt()
                code, *cmd = script_code[pointer]
                match code:
                    case 0:
                        # 结束
                        break
                    case 1:
                        # 跳转到
                        pointer = cmd[0]
                        continue
                    case 2:
                        # 执行
                        self.game_ctrl.sendwocmd(self.var_replace(loc_vars, cmd[0]))
                    case 3:
                        # 设置
                        varname, arg1, _, syntax = cmd[0]
                        if arg1:
                            loc_vars[varname] = syntax
                        else:
                            loc_vars[varname] = self.eval(syntax, loc_vars)
                    case 4:
                        # 判断
                        arg1, arg1_is_constant, op, arg2, arg2_is_constant, jmp1, jmp2 = cmd[0]
                        if not arg1_is_constant:
                            arg1 = loc_vars[arg1]
                        if not arg2_is_constant:
                            arg2 = loc_vars[arg2]
                        res = [
                            (lambda x, y: x == y),
                            (lambda x, y: x != y),
                            (lambda x, y: x < y),
                            (lambda x, y: x <= y),
                            (lambda x, y: x > y),
                            (lambda x, y: x >= y)
                        ][op](arg1, arg2)
                        pointer = jmp1 if res else jmp2
                        continue
                    case 5:
                        # 等待
                        time.sleep(cmd[0])
                    case 6:
                        # 读取个人变量
                        assert isinstance(p_path, str), "CODE PANIC: 01"
                        seq1, seq2 = cmd[0]
                        old = tmpjson.read(p_path)
                        old[seq2] = loc_vars[seq1]
                        tmpjson.write(p_path, old)
                    case 7:
                        # 导出个人变量
                        assert isinstance(p_path, str), "CODE PANIC: 02"
                        seq1, seq2 = cmd[0]
                        old = tmpjson.read(p_path)
                        loc_vars[seq1] = old.get(seq2) # type: ignore
                    case 8:
                        # 输出
                        Print.print_with_info(self.var_replace(loc_vars, cmd[0]), "§f 输出 §r")
                    case 9:
                        target, msg = cmd[0]
                        self.game_ctrl.say_to(self.var_replace(loc_vars, target), self.var_replace(loc_vars, msg))
                    case 10:
                        # 读取全局变量
                        seq1, seq2 = cmd[0]
                        old = tmpjson.read(g_path)
                        old[seq2] = loc_vars[seq1]
                        tmpjson.write(g_path, old)
                    case 11:
                        # 导出全局变量
                        seq1, seq2 = cmd[0]
                        old = tmpjson.read(g_path)
                        loc_vars[seq1] = old.get(seq2) # type: ignore
                pointer += 1
        except self.PlayerExitInterrupt:
            if player not in [self.game_ctrl.bot_name, "服务器"]:
                Print.print_war(f"玩家 {player} 在脚本执行结束之前退出了游戏")
        except self.ScriptExit:
            ...
        except SkipScript:
            ...

    def reload_all(self, _):
        self.load_scripts()

    @staticmethod
    def var_replace(loc_vars: dict[str, object], sub: str):
        myrule = re.compile(r"(\[变量:([^\]]*)\])")
        for varsub, varname in myrule.findall(sub):
            varvalue = loc_vars.get(varname, f"<未定义的变量名:{varname}>")
            sub = sub.replace(varsub, str(varvalue))
        return sub

    def eval(self, syntax, loc_vars: dict):
        return self._eval_recr(syntax, loc_vars)

    def _eval_recr(self, ptr, loc_vars: dict) -> Any:
        if isinstance(ptr, OpPtr):
            return ptr.op(self._eval_recr(ptr.arg1, loc_vars), self._eval_recr(ptr.arg2, loc_vars))
        elif isinstance(ptr, FuncPtr):
            args = (self._eval_recr(arg, loc_vars) for arg in ptr.args)
            return self.reg_func_ptrs[ptr.name](*args)
        elif isinstance(ptr, VarPtr):
            return loc_vars.get(ptr.name)
        else:
            return ptr

    def varcheck_exists(self, ptr, register: list):
        self._varcheck_eval_recr(ptr, register)

    def _varcheck_eval_recr(self, ptr, register):
        if isinstance(ptr, OpPtr):
            self._varcheck_eval_recr(ptr.arg1, register)
            self._varcheck_eval_recr(ptr.arg1, register)
        elif isinstance(ptr, FuncPtr):
            if ptr.name not in self.reg_func_ptrs:
                raise NameError(f"函数 {ptr.name} 未定义")
            for arg in ptr.args:
                self._varcheck_eval_recr(arg, register)
        elif isinstance(ptr, VarPtr):
            if ptr.name not in register:
                raise NameError(f"变量 {ptr.name} 未定义")
        elif isinstance(ptr, int):
            pass
        else:
            raise ValueError(f"Unknown type waiting check: {ptr}")

def examplefunc1():
    rule = re.compile(r'([^ ]*?)=([0-9]+)')
    print(rule.findall(' 变量1=""  变量2=154154 '))

def examplefunc2():
    example = """
    10 设定 a 为 1
    20 设定 b 为 2
    100 判断 a == b 成立=跳转到200 不成立=跳转到300
    200 结束
    300 结束
    """
    compiler = Compiler(Frame())
    res, err = compiler.script_parse(example) # type: ignore
    if err:
        raise err
    else:
        print(res)

if __name__ == "__main__":
    print(split_by_quote('123 345 "567 890" 75'))
    os._exit(0)