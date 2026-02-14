import queue
import threading
import requests
from urllib.parse import parse_qs
from tooldelta import utils

class AsyncHttp:
    def __init__(self, omega):
        self.omega = omega
        self.result_queue = queue.Queue()

    def request(self, method, address, option, callback):
        """发起HTTP请求
        
        :param method: HTTP方法（GET/POST/PUT/DELETE/HEAD/PATCH）
        :param address: 请求地址
        :param option: 请求选项（包含query/headers/timeout/body等）
        :param callback: 回调函数
        """
        @utils.thread_func(f"HTTP {method} {address}")
        def _run_request():
            try:
                # 处理请求参数
                params = {}
                headers = {}
                timeout = 30
                data = None

                if option:
                    # 处理查询参数
                    if 'query' in option:
                        params = parse_qs(option['query'])
                        params = {k: v[0] for k, v in params.items()}
                    
                    # 处理请求头
                    headers = option.get('headers', {})
                    
                    # 处理超时时间
                    timeout_str = option.get('timeout', '30s')
                    if timeout_str.endswith('s'):
                        timeout = int(timeout_str[:-1])
                    else:
                        timeout = int(timeout_str)
                    
                    # 处理请求体
                    data = option.get('body')

                # 发送HTTP请求
                response = requests.request(
                    method=method.upper(),
                    url=address,
                    params=params,
                    headers=headers,
                    data=data,
                    timeout=timeout
                )

                # 构建响应字典
                response_dict = {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'body': response.text,
                    'body_size': len(response.content),
                    'cookies': [
                        {
                            'name': c.name,
                            'value': c.value,
                            'domain': c.domain,
                            'path': c.path
                        } for c in response.cookies
                    ],
                    'url': response.url
                }
                self.result_queue.put((callback, response_dict, None))
            except Exception as e:
                self.result_queue.put((callback, None, str(e)))

        _run_request()

    def resp(self):
        """响应生成器，持续从队列获取请求结果"""
        while True:
            try:
                cb, resp, err = self.result_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            yield {
                "cb": cb,              # 回调
                "err": err,             # 错误信息
                "resp": resp          # 成功时的响应数据
            }