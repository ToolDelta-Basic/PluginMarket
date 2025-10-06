import random
import time
from tooldelta import Plugin, plugin_entry, Chat, utils

from tooldelta.utils.cfg_meta import (
    JsonSchema,
    field,
    get_plugin_config_and_version,
)


class Q2AConfig(JsonSchema):
    min_num: int = field("最小数值", -50)
    max_num: int = field("最大数值", 50)
    syntax_length_min: int = field("表达式最小长度", 3)
    syntax_length_max: int = field("表达式最大长度", 5)
    question_throw_delay_min: int = field("最少出题间隔(秒)", 300)
    question_throw_delay_max: int = field("最多出题间隔(秒)", 400)
    timeout: int = field("答题超时时间(秒)", 180)
    question_fmt: str = field(
        "问题格式", "§eQ2A§7>> §f[表达式]的结果是什么？可以在聊天栏发送答案！"
    )
    ans_timeout_fmt: str = field(
        "回答过期提示", "§eQ2A§7>> §c三分钟内没有人答对， 答案是[答案]啦！"
    )
    award_cmds: list[str] = field(
        "奖励指令",
        [
            r'/tellraw @a {"rawtext":[{"text":"§eQ&A§7>> §a恭喜[玩家名]最先答对了答案！ 获得 1 颗钻石！"}]}',
            r"/give [玩家名] diamond",
        ],
    )


def generate_syntax_and_its_answer(
    min_length: int, max_length: int, num_min: int, num_max: int
):
    ans = 0
    output = ""
    for _ in range(random.randint(min_length, max_length)):
        num = random.randint(num_min, num_max)
        ans += num
        if output == "":
            output += str(num)
        else:
            output += f"+{num}" if num >= 0 else f"{num}"
    return output, ans


class Questions(Plugin):
    name = "Q&A答题"
    author = "SuperScript"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.config, _ = get_plugin_config_and_version(
            self.name, Q2AConfig, self.version
        )
        self.ListenActive(self.on_active)
        self.ListenChat(self.on_chat)
        self.last_ans = None
        self.last_question_throw_time = 0

    def on_active(self):
        self.flush_next_question_time()
        self.on_seconds()

    def on_chat(self, chat: Chat):
        if self.last_ans is not None and chat.msg == str(self.last_ans):
            for cmd in self.config.award_cmds:
                self.game_ctrl.sendwocmd(
                    utils.simple_fmt(
                        {"[答案]": self.last_ans, "[玩家名]": chat.player.name}, cmd
                    )
                )
            self.last_ans = None
            self.flush_next_question_time()

    @utils.timer_event(1, "Q&A定时任务")
    def on_seconds(self):
        if (
            self.last_ans is not None
            and time.time() - self.last_question_throw_time > self.config.timeout
        ):
            self.game_ctrl.say_to(
                "@a",
                utils.simple_fmt(
                    {"[答案]": str(self.last_ans)}, self.config.ans_timeout_fmt
                ),
            )
            self.last_ans = None
            self.flush_next_question_time()
        if self.last_ans is None and time.time() > self.next_question_time:
            self.on_throw_question()

    def on_throw_question(self):
        q, ans = generate_syntax_and_its_answer(
            self.config.syntax_length_min,
            self.config.syntax_length_max,
            self.config.min_num,
            self.config.max_num,
        )
        self.game_ctrl.say_to(
            "@a", utils.simple_fmt({"[表达式]": q}, self.config.question_fmt)
        )
        self.last_ans = ans
        self.last_question_throw_time = time.time()


    def flush_next_question_time(self):
        self.next_question_time = time.time() + random.randint(
            self.config.question_throw_delay_min, self.config.question_throw_delay_max
        )

entry = plugin_entry(Questions)
