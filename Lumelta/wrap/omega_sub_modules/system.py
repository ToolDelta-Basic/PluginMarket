from tooldelta import utils
from .players import Players
import threading
import sys
import os
import platform
import queue
import time
import tempfile

def get_os_name():
    if sys.platform == 'linux':
        # 检查是否是Android
        android_indicators = [
            '/system/bin',
            '/system/build.prop',
            '/system/app',
            '/system/framework'
        ]
        is_android = any(os.path.exists(indicator) for indicator in android_indicators)
        if not is_android:
            is_android = os.environ.get('ANDROID_ROOT') is not None
        return 'android' if is_android else 'linux'
    elif sys.platform == 'darwin':
        return 'macos'
    elif sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('cygwin'):
        return 'cygwin'
    elif sys.platform.startswith('freebsd'):
        return 'freebsd'
    else:
        return sys.platform

def get_arch():
    machine = platform.machine().lower()
    # 处理ARM架构
    if machine.startswith('arm') or machine.startswith('aarch'):
        if machine in ('aarch64', 'arm64'):
            return 'arm64'
        elif '64' in machine or machine.startswith(('armv8', 'armv9')):
            return 'arm64'
        else:
            return 'arm'
    # 处理x86架构
    elif machine in ('x86_64', 'amd64'):
        return 'amd64'
    elif machine in ('i386', 'i486', 'i586', 'i686'):
        return 'i386'
    # 其他情况直接返回
    return machine

def get_os_arch():
    return f"{get_os_name()}-{get_arch()}"

import unicodedata
def get_char_display_width(char):
    """获取字符的终端显示宽度（全角字符为2，半角为1）"""
    if unicodedata.east_asian_width(char) in ('F', 'W'):
        return 2
    else:
        return 1

class BlockInput:
    def __init__(self):
        self.stop_flag = False

    def __call__(self, prompt):
        print(prompt, end='', flush=True)
        if platform.system() == 'Windows':
            # Windows 原有逻辑（支持中文回显）
            import msvcrt
            buf = []
            while not self.stop_flag:
                if msvcrt.kbhit():
                    c = msvcrt.getwch()
                    if c == '\r':
                        print()
                        break
                    elif c == '\x08':  # 退格键
                        if buf:
                            buf.pop()
                            sys.stdout.write('\b \b')
                    else:
                        buf.append(c)
                        sys.stdout.write(c)  # 直接回显（Windows 自动处理多字节字符）
                    sys.stdout.flush()
            return ''.join(buf)
        else:
            import tty, termios, select, os
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                buf = []
                utf8_bytes = bytearray()
                while not self.stop_flag:
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if rlist:
                        byte = os.read(fd, 1)
                        if byte:
                            utf8_bytes.extend(byte)
                            try:
                                char = utf8_bytes.decode('utf-8')
                                utf8_bytes.clear()
                            except UnicodeDecodeError:
                                continue

                            if char == '\r':
                                sys.stdout.write('\n')
                                break
                            elif char == '\x7f':  # 退格键
                                if buf:
                                    removed_char = buf.pop()
                                    # 计算被删除字符的显示宽度
                                    width = get_char_display_width(removed_char)
                                    # ANSI转义：左移N列 + 清除到行尾
                                    sys.stdout.write(f'\033[{width}D\033[K')
                                    sys.stdout.flush()
                            else:
                                buf.append(char)
                                sys.stdout.write(char)
                                sys.stdout.flush()
                    if self.stop_flag:
                        break
                return ''.join(buf)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def stop(self):
        self.stop_flag = True
block_input = BlockInput()

from tooldelta.utils import fmts
class System:
    def __init__(self, omega):
        self.omega = omega
        self.fmts_header = self.omega.fmts_header
        self._start_time = time.time()  # 记录启动时间
        self.result_queue = queue.Queue()

    # 显示与日志
    def fmt(self, text):
        lines = []
        for line in text.split("\n"):
            lines.append(self.fmts_header + line)
        return "\n".join(lines)

    def print(self, text):
        self.info_out(text[:-1] if text.endswith("\n") else text)

    def sprint(self, text):
        fmts.clean_print(self.fmt(text), end="")

    def log(self, text):
        fmts.c_log("", text) # 不正确

    def log_and_print(self, text):
        self.log(text)
        self.print(self.fmt(text))

    def debug_out(self, text):
        pass

    def info_out(self, text):
        fmts.print_inf(self.fmt(text))

    def success_out(self, text):
        fmts.print_suc(self.fmt(text))

    def warning_out(self, text):
        fmts.print_war(self.fmt(text))

    def error_out(self, text):
        fmts.print_err(self.fmt(text))

    def color_trans_print(self, text):
        self.sprint(text)

#    def info_out(self, *args):
#        fmts.print_inf(self.fmt(" ".join([str(arg) for arg in args])))

    # 控制台输入
    def input(self, callback, timeout):
        @utils.thread_func("omega.system.input")
        def run():
            user_input = input("")
            self.result_queue.put((callback, user_input))
        run()

    # 系统与文件
    def os(self):
        return get_os_arch()
    
    def cwd(self):
        """获取当前工作目录"""
        return os.getcwd()
    
    def make_dir(self, path):
        """创建目录（支持多级目录）"""
        os.makedirs(path, exist_ok=True)
    
    def now(self):
        """获取当前Unix时间戳（秒）"""
        return time.time()
    
    def now_since_start(self):
        """获取插件启动后的持续时间（秒）"""
        return time.time() - self._start_time
    
    def temp_dir(self):
        """创建临时目录（由框架负责清理）"""
        return tempfile.mkdtemp()

    def block_sleep(self, sleep_time):
        time.sleep(sleep_time)

    def sleep(self, sleep_time, callback):
        @utils.thread_func("omega.system.sleep")
        def run():
            time.sleep(sleep_time)
            self.result_queue.put((callback, None))
        run()

    def resp(self):
        while True:
            try:
                cb, output = self.result_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            yield {
                "cb": cb,
                "output": output
            }