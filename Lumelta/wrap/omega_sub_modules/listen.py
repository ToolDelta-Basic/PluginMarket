from tooldelta import utils
from ..conversion import python_to_lua_table
import threading
import queue
import inspect

class MuxPollerDataDistribution:
    def __init__(self):
        self.mux_pollers = {}  # {mux_poller实例: [注册的func列表]}
        self.pollers = {}      # {func: {注册的mux_poller实例集合}}
        self.threads = []      # 维护线程列表
        self.lock = threading.Lock()  # 线程锁
        self.stop_all_flag = False    # 全局停止标志（可选）

    def poll(self, mux_poller, func, *args):
        """注册事件到分发器"""
        with self.lock:
            if self.stop_all_flag:
                return self  # 全局停止时不允许新注册
            
            # 初始化mux_poller对应的函数列表
            if mux_poller not in self.mux_pollers:
                self.mux_pollers[mux_poller] = []
            
            # 避免重复注册同一个func到同一个mux_poller
            if mux_poller in self.pollers.get(func, set()):
                return self
            
            # 添加到数据结构
            self.mux_pollers[mux_poller].append(func)
            if func not in self.pollers:
                self.pollers[func] = set()
            self.pollers[func].add(mux_poller)

            # 创建并启动线程
            def thread_wrapper():
                try:
                    poller = func(*args)
                    # 处理非生成器情况（转为可迭代对象）
                    if not inspect.isgenerator(poller):
                        poller = iter([poller])  # 支持普通函数返回单个值或可迭代对象
                    
                    for data in poller:
                        with self.lock:
                            if self.stop_all_flag:
                                break  # 全局停止时退出循环
                            
                            # 分发数据到所有注册的mux_poller
                            target_pollers = self.pollers.get(func, set())
                            for poller_instance in target_pollers:
                                if not poller_instance.stop_flag:  # 检查实例停止标志
                                    poller_instance.result_queue.put({
                                        'type': func,
                                        'data': data
                                    })
                except Exception as e:
                    print(f"Poller线程异常: {e}")
            
            thread = utils.createThread(
                thread_wrapper,
                (),
                f"omega poller for {func.__name__}"
            )
            self.threads.append(thread)
        return self

    def stop(self, mux_poller):
        """停止单个MuxPoller的所有事件"""
        with self.lock:
            if mux_poller not in self.mux_pollers:
                return
            
            # 从pollers中移除关联的mux_poller
            for func in self.mux_pollers[mux_poller]:
                if func in self.pollers:
                    self.pollers[func].discard(mux_poller)  # 安全移除集合元素
                    if not self.pollers[func]:  # 清理空集合
                        del self.pollers[func]
            
            # 移除mux_poller的注册
            del self.mux_pollers[mux_poller]
            
            # 尝试终止相关线程（示例逻辑）
            for thread in list(self.threads):  # 避免迭代时修改列表
                if thread.is_alive():
                    thread.join(0.1)  # 等待线程优雅终止

    def stop_all(self):
        """全局停止所有事件"""
        with self.lock:
            self.stop_all_flag = True
            self.mux_pollers.clear()
            self.pollers.clear()
            """
            for thread in self.threads:
                if thread.is_alive():
                    thread.join(1)
            """
            self.threads = []


class MuxPoller:
    def __init__(self, omega, distribution):
        self.omega = omega
        self.lua_runtime = self.omega.lua_runtime
        self.stop_flag = False  # 实例级停止标志
        self.result_queue = queue.Queue()  # 建议设置队列大小
        self.distribution = distribution

    def poll(self, poller_func, *args):
        """注册事件到分发器"""
        self.distribution.poll(self, poller_func, *args)
        return self

    def block_get_next(self):
        """阻塞获取下一个事件"""
        while not self.stop_flag:
            try:
                return self.result_queue.get(timeout=0.1)
            except queue.Empty:
                continue
    get_next = block_get_next

    def stop(self):
        """优雅停止Poller"""
        self.stop_flag = True
        self.distribution.stop(self)  # 通知分发器停止关联事件
        # 清理队列残留（可选）
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                pass

    def block_has_next(self):
        """检查是否有未处理事件"""
        return not self.result_queue.empty() or not self.stop_flag
    has_next = block_has_next


class Listen:  # 保持类名不变
    def __init__(self, omega):
        self.omega = omega
        self.distribution = MuxPollerDataDistribution()  # 全局分发器实例

    def make_mux_poller(self):  # 保持方法名不变
        """创建新的Poller实例"""
        return MuxPoller(self.omega, self.distribution)
    
    new_mux_poller = make_mux_poller  # 保持别名不变

    def stop_all_pollers(self):
        """全局停止所有Poller"""
        self.distribution.stop_all()
