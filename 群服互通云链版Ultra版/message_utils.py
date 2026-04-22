"""消息清洗和触发器定义。

这一层故意保持纯工具性质，不依赖插件实例，
这样别的模块在处理群消息时可以直接复用，而不用关心运行时状态。
"""

import inspect
import re
from typing import Any
from collections.abc import Callable


EASTER_EGG_QQIDS = {2528622340: ("SuperScript", "Super")}


class QQMsgTrigger:
    """群聊触发词的运行时描述对象。"""
    def __init__(
        self,
        triggers: list[str],
        argument_hint: str | None,
        usage: str,
        func: Callable[..., Any],
        args_pd: Callable[[int], bool] = lambda _: True,
        op_only: bool = False,
    ):
        """记录一条触发规则和它的回调元信息。"""
        self.triggers = triggers
        self.argument_hint = argument_hint
        self.usage = usage
        self.func = func
        self.args_pd = args_pd
        self.op_only = op_only
        self.accept_group = self._accept_group_arg(func)

    @staticmethod
    def _accept_group_arg(func: Callable[..., Any]) -> bool:
        """判断回调是否接受 group_id 这个上下文参数。"""
        # 兼容两种回调签名：老插件只收 qqid，新插件可以直接拿到 group_id。
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            return False
        positional_count = 0
        for param in sig.parameters.values():
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                positional_count += 1
            elif param.kind == inspect.Parameter.VAR_POSITIONAL:
                return True
        return positional_count >= 3

    def match(self, msg: str):
        """尝试匹配当前消息命中的触发词前缀。"""
        for trigger in self.triggers:
            if msg.startswith(trigger):
                return trigger
        return None


CQ_IMAGE_RULE = re.compile(r"\[CQ:image,([^\]])*\]")
CQ_VIDEO_RULE = re.compile(r"\[CQ:video,[^\]]*\]")
CQ_FILE_RULE = re.compile(r"\[CQ:file,[^\]]*\]")
CQ_AT_RULE = re.compile(r"\[CQ:at,[^\]]*\]")
CQ_REPLY_RULE = re.compile(r"\[CQ:reply,[^\]]*\]")
CQ_FACE_RULE = re.compile(r"\[CQ:face,[^\]]*\]")


def remove_cq_code(content: str):
    """移除消息中的 CQ 片段。"""
    # 发到游戏里的文本不适合保留 CQ 片段，这里直接做最朴素的剥离。
    cq_start = content.find("[CQ:")
    while cq_start != -1:
        cq_end = content.find("]", cq_start) + 1
        content = content[:cq_start] + content[cq_end:]
        cq_start = content.find("[CQ:")
    return content


def remove_color(content: str):
    """去掉 Minecraft 风格颜色码，避免群昵称和消息混进格式符。"""
    return re.compile(r"§(.)").sub("", content)


def replace_cq(content: str):
    """把常见 CQ 片段替换成可读占位文本，方便转发到游戏里。"""
    for rule, replacement in (
        (CQ_IMAGE_RULE, "[图片]"),
        (CQ_FILE_RULE, "[文件]"),
        (CQ_VIDEO_RULE, "[视频]"),
        (CQ_AT_RULE, "[@]"),
        (CQ_REPLY_RULE, "[回复]"),
        (CQ_FACE_RULE, "[表情]"),
    ):
        content = rule.sub(replacement, content)
    return content
