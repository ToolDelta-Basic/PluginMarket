import queue

class BotAction:
    def __init__(self, omega):
        self.omega = omega
        self.result_queue = queue.Queue()

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