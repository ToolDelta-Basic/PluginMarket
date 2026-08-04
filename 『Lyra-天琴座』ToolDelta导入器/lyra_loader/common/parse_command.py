"""解析命令响应"""

from tooldelta.internal.types import Packet_CommandOutput


def parse_command(response: Packet_CommandOutput) -> tuple[bool, str]:
    """解析命令响应, 并返回成功状态和错误详情"""
    try:
        messages = response.as_dict.get("OutputMessages", [])
        if not messages:
            return False, "命令响应没有 OutputMessages"
        message = messages[0]
        if bool(message.get("Success")):
            return True, ""
        detail = str(
            message.get("Message") or message.get("MessageId") or "命令执行失败"
        )
        if parameters := message.get("Parameters"):
            detail += f"; Parameters={parameters}"
        return False, detail
    except Exception as error:
        return False, f"无法解析命令响应: {error}"
