import queue

class Flex:
    def __init__(self, omega):
        self.omega = omega
        self.control = self.omega.control
        self.flex_api = self.control.flex_api
        self.result_queue = queue.Queue()

    def expose(self, api_name):
        result_queue = self.flex_api.expose(api_name)
        def entry():
            while True:
                try:
                    args, cb = result_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield {
                    "args": args,
                    "cb": cb
                }
        return entry

    def call(self, api_name, args, cb, timeout = None):
        self.flex_api.call(api_name, args, cb, timeout)

    def listen(self, topic):
        result_queue = self.flex_api.listen(topic)
        def entry():
            while True:
                try:
                    data = result_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield data
        return entry

    def pub(self, topic, data):
        self.flex_api.put(topic, data)

    def set(self, key, val):
        self.flex_api.set(key, val)

    def get(self, key):
        self.flex_api.get(key)

    def resp(self):
        while True:
            try:
                cb, output, err = self.result_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            yield {
                "cb": cb,
                "output": output,
                "err": err
            }