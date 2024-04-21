import re, time, os, random
from typing import Any, Callable

from tooldelta import Frame, Plugin, plugins, Config, Builtins, Print

from syntax_compile import (
    parse as syntax_parse,
    deal_stxgrp,
    get_final_type,
    register_func_syntax,
    register_var,
)
from syntax_lib import *
from basic_types import *

tmpjson = Builtins.TMPJson

@plugins.add_plugin_as_api("TD中文Basic")
class Compiler(Plugin):
    name = "ZDelta-中文Basic语言"
    author = "SuperScript"
    version = (0, 0, 3)

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
            args_checker: Callable[[list[int]], bool],
            return_type: int,
            callback: Callable
        ):
        """
        向 TD-中文Basic 添加函数, 扩展函数库
        参数:
            name: 函数名
            args_checker: 参数类型检测器, 传入参数类型列表(用int表示), 合法返回True, 不合法返回False
                e.g. api = plugins.get_plugin_api("TD中文Basic")
                e.g. args_checker = lambda a:a[0]==api.STRING and a[1]==api.NUMBER # 检测第一个参数是否是字符串, 第二个参数是否为数字
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
        self.f = f
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
            "取整", lambda x:len(x)==1 and x[0]==NUMBER,
            NUMBER,
            lambda x:int(x)
        )
        self.add_func_ptr(
            "四舍五入", lambda x:len(x)==1 and x[0]==NUMBER,
            NUMBER,
            lambda x:round(x)
        )
        self.add_func_ptr(
            "随机整数", lambda x:len(x)==2 and x[0]==x[1]==NUMBER,
            NUMBER,
            lambda x,y:random.randint(x,y)
        )

    def load_scripts(self):
        for script_folder in os.listdir(os.path.join(self.data_path, "脚本文件")):
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

    def on_inject(self):
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
        loc_vars_register = self.builtins_register_vars
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
        _get_var_type = lambda varname : loc_vars_register.get(varname)
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
                cmds = lett.split()[1:]
                if cmds == []:
                    return "", AssertionError(f"第 {lett.split()[0]} 行无有效指令")
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
                        seq1 = " ".join(args[1:])
                        _add_cmp(2, seq1)
                        # 执行 <mc指令>
                    case "SET" | "设定" | "设定变量" | "设置变量":
                        """
                        md: 0=const_int, 1=const_str, 2=等待聊天栏输入, 3=等待聊天栏输入纯数字, 4=玩家计分板分数, 5=玩家坐标, 9=表达式
                        md: 0=math_syntax, 1=str
                        md2: 0=int, 1=str
                        """
                        assert len(args) > 2, "设定命令 至少需要2个参数"
                        assert args[2] == "为", "语法错误"
                        seq1 = args[1]
                        seq2 = args[3]
                        res = None
                        if seq2.isnumeric() or (len(seq2) > 1 and seq2[0] == "-" and seq2[1:].isnumeric()):
                            md = 0
                            md2 = NUMBER
                            res = int(seq2)
                        elif " ".join(args[3:]).startswith('"') and " ".join(args[3:]).endswith('"'):
                            md = 1
                            md2 = STRING
                            res = " ".join(args[3:])[1:-1]
                        elif seq2 == "等待聊天栏输入":
                            if loc_vars_register.get("玩家名") is None:
                                raise SyntaxError("无法在此时取得玩家名")
                            md = 2
                            md2 = STRING
                        elif seq2 == "等待聊天栏输入纯数字":
                            if loc_vars_register.get("玩家名") is None:
                                raise SyntaxError("无法在此时取得玩家名")
                            md = 3
                            md2 = NUMBER
                        elif seq2 == "当前玩家计分板分数":
                            _simple_assert_len(args, 5)
                            if loc_vars_register.get("玩家名") is None:
                                raise SyntaxError("无法在此时取得玩家名")
                            md = 4
                            md2 = NUMBER
                            res = args[4]
                        elif seq2 == "玩家当前坐标":
                            if loc_vars_register.get("玩家名") is None:
                                raise SyntaxError("无法在此时取得玩家名")
                            md = 5
                            md2 = STRING
                        elif seq2 == "当前时间ticks":
                            md = 6
                            md2 = NUMBER
                        else:
                            try:
                                res = deal_stxgrp(syntax_parse(" ".join(args[3:])))
                                md2 = get_final_type(res)
                                self.varcheck_exists(res, list(loc_vars_register.keys()))
                            except NameError as err:
                                raise AssertionError(f"表达式异常: {err}")
                            except SyntaxError as err:
                                raise AssertionError(f"表达式错误: {err}")
                            md = 9
                        #else:
                        #    raise AssertionError(f"无法识别的表达式: " + " ".join(args[3:]))
                        assert not(loc_vars_register.get(seq1)is not None and loc_vars_register.get(seq1) != md2), "变量类型已被定义, 无法更改"
                        loc_vars_register[seq1] = md2
                        register_var(seq1, md2)
                        _add_cmp(3, [md, md2, seq1, res])
                        # 设定变量 设定模式, 变量类型, 变量名[, 值]
                    case "IFS" | "判断":
                        # 判断 变量 操作符 变量 成立=跳转到??? 不成立=跳转到???
                        _simple_assert_len(args, 6)
                        arg1, arg1type, arg1_is_constant = auto_to_type_r(args[1])
                        arg2, arg2type, arg2_is_constant = auto_to_type_r(args[3])
                        if not arg1_is_constant and _get_var_type(arg1) is None:
                            raise AssertionError(f"变量 {seq1} 未定义")
                        if not arg2_is_constant and _get_var_type(arg2) is None:
                            raise AssertionError(f"变量 {seq2} 未定义")
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
                            raise AssertionError("判断命令: 暂时只能比较数值变量大小")
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
                    case "OUT" | "导出变量" | "存储变量":
                        _simple_assert_len(args, 4)
                        assert args[2] == "->", "导出个人变量格式应为 内存变量名 -> 磁盘变量名"
                        assert args[1] in loc_vars_register.keys(), f"变量 {args[1]} 未定义, 不能使用, 请先设定"
                        _add_cmp(6, (args[1], args[3]))
                    case "IN" | "导入变量" | "读取变量":
                        _simple_assert_len(args, 6)
                        assert args[2] == "<-" and args[4] == "类型为" and args[5] in ["数值", "字符串"], "读取个人变量格式应为 内存变量名 <- 磁盘变量名 类型为 数值/字符串"
                        _add_cmp(7, (args[1], args[3]))
                        loc_vars_register[args[1]] = ["数值", "字符串"].index(args[5])
                    case "PRINT" | "输出":
                        assert len(args) >= 2, f"输出 需要至少1个参数, 目前{len(args) - 1}个"
                        _add_cmp(8, " ".join(args[1:]))
                    case _:
                        # 扩展命令
                        if args[0] in self.reg_cmds_with_checkers.keys():
                            cmd = args[0]
                            self.reg_cmds_with_checkers[cmd](len(args))
                            _add_cmp(hash(cmd), None if len(args) == 1 else args[1:])
                        else:
                            raise AssertionError(f"无法被识别的指令: {args[0]}")
            return cmp_scripts, None
        except AssertionError as err:
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
        if pre_variables.get("玩家名") is not None:
            if pre_variables.get("玩家名") is not None:
                player = pre_variables["玩家名"]
                path = self.get_player_plot_path(player)
                tmpjson.loadPathJson(path, False)
        else:
            player = None
            path = os.path.join(self.data_path, "全局变量.json")
            tmpjson.loadPathJson(path, False)
        if tmpjson.read(path) is None:
            tmpjson.write(path, {})
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
                cmd = script_code[pointer]
                match cmd[0]:
                    case 0:
                        break
                    case 1:
                        pointer = cmd[1]
                        continue
                    case 2:
                        self.game_ctrl.sendwocmd(self.var_replace(loc_vars, cmd[1]))
                    case 3:
                        setmode, _, name, value = cmd[1]
                        match setmode:
                            case 9:
                                loc_vars[name] = self.eval(value, loc_vars)
                            case 1:
                                loc_vars[name] = value
                            case 2:
                                try:
                                    res = self.funclib.waitMsg(player, 180) # type: ignore
                                    if res is None:
                                        res = ""
                                    else:
                                        self.game_ctrl.say_to(player, "§a输入完成, 请退出聊天栏") # type: ignore
                                    loc_vars[name] = res
                                except IOError:
                                    plot_terminated = True
                                    break
                            case 3:
                                while 1:
                                    try:
                                        res = int(self.funclib.waitMsg(player, 180)) # type: ignore
                                        loc_vars[name] = res
                                        self.game_ctrl.say_to(player, "§a输入完成, 请退出聊天栏") # type: ignore
                                        break
                                    except ValueError:
                                        self.game_ctrl.say_to(player, "§c请输入纯数字") # type: ignore
                                    except IOError:
                                        plot_terminated = True
                                        break
                            case 4:
                                try:
                                    res = self.funclib.getScore(player, value) # type: ignore
                                except:
                                    res = None
                                loc_vars[name] = res
                            case 5:
                                x, y, z = self.funclib.getPosXYZ(player) # type: ignore
                                loc_vars[name] = f"{int(x)} {int(y)} {int(z)}"
                            case 6:
                                loc_vars[name] = int(time.time())
                    case 4:
                        arg1, arg1_is_constant, op, arg2, arg2_is_constant, jmp1, jmp2 = cmd[1]
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
                        time.sleep(cmd[1])
                    case 6:
                        seq1, seq2 = cmd[1]
                        old = tmpjson.read(path)
                        old[seq2] = loc_vars[seq1]
                        tmpjson.write(path, old)
                    case 7:
                        seq1, seq2 = cmd[1]
                        old = tmpjson.read(path)
                        loc_vars[seq1] = old.get(seq2) # type: ignore
                    case 8:
                        Print.print_with_info(self.var_replace(loc_vars, cmd[1]), "§f 输出 §r")
                pointer += 1
        except self.PlayerExitInterrupt:
            if player not in [self.game_ctrl.bot_name, "服务器"]:
                Print.print_war(f"玩家 {player} 在脚本执行结束之前退出了游戏")
        except self.ScriptExit:
            ...

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

def identity_type(param: str):
    if is_valid_num(param):
        return NUMBER
    elif is_valid_str(param):
        return STRING
    else:
        return -1

def auto_to_type_r(n: str):
    t = identity_type(n)
    if t == -1:
        return n, -1, False
    elif t == NUMBER:
        return to_number(n), NUMBER, True
    elif t == STRING:
        return to_string(n), STRING, True
    else:
        raise Exception

def is_valid_num(n: str):
    try:
        float(n)
        return True
    except:
        return False

def is_valid_str(n: str):
    return n.startswith('"') and n.endswith('"') and n.count('"') == 2

def to_string(n: str):
    return n[1:-1]

def to_number(n: str):
    s = float(n)
    if s % 1:
        return s
    else:
        return int(s)

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
    examplefunc2()