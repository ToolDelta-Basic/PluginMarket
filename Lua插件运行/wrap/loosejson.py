# 基于 FlorianDietz 的 loosejson 项目修改
# 源码地址: https://github.com/FlorianDietz/loosejson 

import ast
import json
import math
import re
import sys
import traceback

from six import string_types

##############################################################################################################
# 这是一个宽松的JSON解析器，不像标准json库那么严格。
# 不敢相信居然没有现成的库，只能自己写一个...
##############################################################################################################


class JsonParsingException(Exception):
    """JSON解析异常"""
    pass


def loads(text):
    """
    解析一个表示JSON对象的字符串，规则比标准json库更宽松。
    功能包括：
    * 支持Unicode（隐式支持，因为直接使用Python的字符串格式）
    * 支持标准JSON转义字符
    * 支持多余的逗号
    * 支持未加引号的字符串（适用于规则和选项中常见的多种字符）
    * 支持引号字符串中的换行符（视为\n处理，换行后的空格和制表符会被忽略）
    * 支持单引号和双引号
    * 支持null和None（同时兼容JavaScript和Python）
    * 支持True/true和False/false
    * 支持列表中出现多个逗号
    * 支持用空格分隔列表元素
    * 支持Infinity、-Infinity和NaN数值
    * 提供有用的错误提示信息
    """
    parser = LooseJsonParser(text)
    raised_error = None
    try:
        res = parser.get_object()
    except Exception as e:
        # 不直接抛出异常，避免Python自动链式包装异常
        raised_error = e
        raised_error_details = get_error_message_details()
    if raised_error is not None:
        raise JsonParsingException(
            "解析文本为JSON格式时发生异常。\n异常出现在第%d行，第%d列，%s处：\n%s" % 
            (parser.line, parser.col, "字符串末尾" if parser.EOF else f"字符 '{parser.chars[parser.pos]}' ", str(raised_error))
        )
    # 转换为JSON字符串再解析回来，确保结果符合标准JSON格式
    res = json.loads(json.dumps(res))
    return res


class LooseJsonParser:
    def __init__(self, text):
        self.pos = 0         # 当前解析位置
        self.line = 1        # 当前行号
        self.col = 1         # 当前列号
        self.chars = list(text)  # 解析字符列表
        self.unquoted_characters = r'[a-zA-Z0-9.?!\-\+_\u4e00-\u9fff]'  # 未加引号字符串允许的字符
        self.EOF = object()  # 结束标志
        self.chars.append(self.EOF)  # 在末尾添加结束标志

    def is_valid_element_start(self, char):
        """检查字符是否可以作为元素的起始"""
        return char in ['[', '{', '"', "'"] or re.match(self.unquoted_characters, char)

    def get_object(self):
        """
        从当前位置开始解析完整对象，解析完成后返回结果对象。
        开始时self.pos应位于对象起始位置（或前导空格），返回时self.pos位于对象末尾。
        """
        task = None
        while self.pos < len(self.chars):
            char = self.chars[self.pos]
            if char == self.EOF:
                raise JsonParsingException("字符串结束时未找到可解析的内容。")
            
            # 遇到换行符时更新行号和列号
            if char == '\n':
                self.line += 1
                self.col = 1
            
            # 根据当前任务处理字符
            if task is None:
                if re.match(r'\s', char):
                    # 未开始解析时忽略空白字符
                    pass
                elif char == '[':
                    task = '构建列表'
                    res_builder = []
                    expecting_comma = False
                elif char == '{':
                    task = '构建字典'
                    res_builder = {}
                    stage = '等待键'
                elif char == '"':
                    task = '构建基本类型'
                    quote_type = '双引号'
                    res_builder = []
                    string_escape = False
                elif char == "'":
                    task = '构建基本类型'
                    quote_type = '单引号'
                    res_builder = []
                    string_escape = False
                elif re.match(self.unquoted_characters, char):
                    task = '构建基本类型'
                    quote_type = '无引号'
                    res_builder = [char]
                    string_escape = False
                    # 提前检查是否需要结束未加引号的文本解析
                    is_finished, res = self._unquoted_text_lookahead_and_optionally_finish(res_builder)
                    if is_finished:
                        return res
                else:
                    raise JsonParsingException(f"寻找下一个对象起始时遇到意外字符：{char}")
            elif task == '构建列表':
                if re.match(r'\s', char):
                    # 列表中忽略空白字符
                    pass
                elif char == ',':
                    expecting_comma = False
                elif char == ']':
                    # 到达列表末尾，返回结果
                    return res_builder
                else:
                    if expecting_comma:
                        if self.is_valid_element_start(char):
                            # 允许省略逗号，直接解析下一个元素
                            next_list_element = self.get_object()
                            res_builder.append(next_list_element)
                            expecting_comma = True  # 添加元素后仍需逗号
                    else:
                        # 递归解析下一个列表元素
                        next_list_element = self.get_object()
                        res_builder.append(next_list_element)
                        expecting_comma = True
            elif task == '构建字典':
                if re.match(r'\s', char):
                    # 字典中忽略空白字符
                    pass
                elif char == '}':
                    if stage in ['等待键', '等待逗号']:
                        return res_builder
                    else:
                        raise JsonParsingException("字典提前结束，最后一个键缺少对应的值。")
                else:
                    if stage == '等待键':
                        # 递归解析键，并验证是否为字符串
                        next_dict_key = self.get_object()
                        if not isinstance(next_dict_key, string_types):
                            # 非字符串键转换为JSON字符串表示（确保None转换为null）
                            if isinstance(next_dict_key, (int, float, bool)):
                                next_dict_key = str(json.dumps(next_dict_key))
                        if next_dict_key in res_builder:
                            raise JsonParsingException(f"字典中出现重复键：{next_dict_key}")
                        stage = '等待冒号'
                    elif stage == '等待冒号':
                        if char == ':':
                            stage = '等待值'
                        else:
                            raise JsonParsingException("预期键值对之间的冒号")
                    elif stage == '等待值':
                        # 递归解析值
                        next_dict_value = self.get_object()
                        res_builder[next_dict_key] = next_dict_value
                        stage = '等待逗号'
                    elif stage == '等待逗号':
                        if char == ',':
                            stage = '等待键'
                        else:
                            raise JsonParsingException("预期键之间的逗号")
                    else:
                        raise Exception(f"程序错误：未知的字典解析阶段：{stage}")
            elif task == '构建基本类型':
                if quote_type in ['双引号', '单引号']:
                    limiting_quote = '"' if quote_type == '双引号' else "'"
                    if char == limiting_quote and not string_escape:
                        # 到达字符串末尾，处理换行和空白
                        tmp = []
                        encountered_linebreak = False
                        for chr in res_builder:
                            if chr == '\n':
                                encountered_linebreak = True
                                tmp.append('\\')
                                tmp.append('n')
                            elif (chr == ' ' or chr == '\t') and encountered_linebreak:
                                # 忽略换行后的空白字符
                                pass
                            else:
                                encountered_linebreak = False
                                tmp.append(chr)
                        # 组合字符串并求值
                        res = "".join(tmp)
                        res = ast.literal_eval(limiting_quote + res + limiting_quote)
                        return res
                    # 添加当前字符到字符串构建器
                    res_builder.append(char)
                    # 处理转义符状态
                    if char == '\\' and not string_escape:
                        string_escape = True
                    else:
                        string_escape = False
                elif quote_type == '无引号':
                    if not re.match(self.unquoted_characters, char):
                        raise Exception("程序错误：此处不应被访问（未加引号文本提前检查失败）")
                    res_builder.append(char)
                    # 提前检查是否需要结束未加引号的文本解析
                    is_finished, res = self._unquoted_text_lookahead_and_optionally_finish(res_builder)
                    if is_finished:
                        return res
                else:
                    raise Exception(f"程序错误：未知的引号类型：{quote_type}")
            else:
                raise Exception(f"程序错误：未知的解析任务：{task}")
            
            # 移动解析位置并更新列号
            self.pos += 1
            self.col += 1
        raise JsonParsingException("程序错误：到达字符串末尾，但应该在遇到EOF时提前检测到")

    def _unquoted_text_lookahead_and_optionally_finish(self, res_builder):
        """
        前瞻检查未加引号的文本是否结束，若是则完成解析并返回结果。
        支持解析布尔值、null、数值（包括Infinity和NaN）和字符串。
        """
        next_char = self.chars[self.pos + 1]
        if next_char != self.EOF and re.match(self.unquoted_characters, next_char):
            return (False, None)  # 后续还有有效字符，继续解析
        
        res = "".join(res_builder)
        
        # 处理布尔值
        if res in ['true', 'True']:
            return (True, True)
        if res in ['false', 'False']:
            return (True, False)
        
        # 处理null/None
        if res in ['null', 'None']:
            return (True, None)
        
        # 处理数值（包括Infinity和NaN）
        try:
            # 优先尝试转换为整数
            return (True, int(res))
        except:
            pass
        
        try:
            # 转换为浮点数（允许Infinity和NaN）
            flt = float(res)
            return (True, flt)
        except:
            pass
        
        # 默认作为字符串处理
        return (True, res)


def get_error_message_details(exception=None):
    """
    获取格式化的错误信息（包含堆栈跟踪）
    """
    if exception is None:
        exception = sys.exc_info()
    exc_type, exc_obj, exc_trace = exception
    trace = traceback.extract_tb(exc_trace)
    error_msg = "堆栈跟踪：\n"
    for (file, linenumber, affected, line) in trace:
        error_msg += f"\t> 错误出现在函数 {affected}\n"
        error_msg += f"\t  位置：{file}:{linenumber}\n"
        error_msg += f"\t  代码行：{line}\n"
    error_msg += f"{exc_type}: {exc_obj}\n"
    return error_msg
