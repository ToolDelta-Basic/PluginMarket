import os, time, asyncio, shutil
from tooldelta import Utils, Print, constants
from tooldelta.plugin_load.injected_plugin import init
from tooldelta.plugin_load.injected_plugin.movent import sendwocmd

__plugin_meta__ = {
    "name": "定时任务",
    "version": "0.0.1",
    "author": "System",
}


class Task:
    def __init__(self, cmds: list[str], time: int, spec=False):
        self.cmds = cmds
        self.wtime = time
        self.spec = spec


data_path = os.path.join(constants.TOOLDELTA_PLUGIN_DATA_DIR, "计划任务")
tasks: dict[int, list[Task]] = {}


@init()
async def on_inject():
    if not os.path.isdir(data_path):
        os.mkdir(data_path)
        c_dir = os.path.join(os.path.dirname(__file__), "示例计划任务")
        for dir in os.listdir(c_dir):
            shutil.copytree(os.path.join(c_dir, dir), data_path)
    read_files()
    Utils.createThread(asyncio.run, (run_tasks(),), "计划任务主线程")


def read_files():
    for file in os.listdir(data_path):
        if file.endswith(".mcfunction"):
            load_mcf_file(os.path.join(data_path, file))


def load_mcf_file(path: str):
    name = os.path.basename(path).replace(".mcfunction", "")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    try:
        s_time, is_spec = parse_sth(content)
    except SyntaxError as err:
        Print.print_err(f"无法加载计划任务 {name}: {err}")
        return
    cmds = []
    for ln in content.split("\n"):
        if not ln.strip().startswith("#"):
            cmds.append(ln)
    if s_time not in tasks.keys():
        tasks[s_time] = []
    tasks[s_time].append(Task(cmds, s_time, is_spec))
    Print.print_suc(f"计划任务: 已加载 {s_time}s任务 {name}")


def parse_sth(f: str):
    s_time = None
    spec = False
    for l in f.split("\n"):
        if l.startswith("# 定时:"):
            s_time = Utils.try_int(l[6:])
        elif l.startswith("sleep"):
            spec = True
    if s_time is None:
        raise SyntaxError("没有设定延时时间")
    elif s_time <= 0:
        raise SyntaxError("设定时间应大于0")
    return s_time, spec


async def run_tasks():
    counter = 0
    while 1:
        await asyncio.sleep(1)
        for k, v in tasks.items():
            if counter % k == 0:
                await asyncio.gather(*(execute_task(task) for task in v))
        counter += 1


async def execute_task(task: Task):
    if task.spec:
        execute_task_spec(task)
    else:
        for cmd in task.cmds:
            sendwocmd(cmd)


@Utils.thread_func("特殊计划任务执行")
def execute_task_spec(task: Task):
    for cmd in task.cmds:
        if cmd.startswith("sleep"):
            time.sleep(Utils.try_int(cmd[6:]) or 0)
        else:
            sendwocmd(cmd)
