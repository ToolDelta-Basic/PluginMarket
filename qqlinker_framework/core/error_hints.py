"""用户友好的错误原因解释系统

═══════════════════════════════════════════════════════════════════════════
设计原则:
  1. 每个框架可能出现的错误都附带"可能的原因"解释
  2. 非技术人员也能看懂发生了什么
  3. 提示应该能引导用户自行排查或提供有用信息给技术支持

错误显示模式:
  FRIENDLY (默认) — 只显示可能的原因，隐藏技术堆栈
  DEBUG           — 同时显示原因 + 完整 Python traceback

  配置方式:
    config.json → 网络连接.错误显示模式 = "友好" | "调试"
    环境变量    → QQLINKER_ERROR_MODE=friendly|debug
    命令行参数  → --error-mode=friendly|debug

使用方式:
  from qqlinker_framework.core.error_hints import hint, explain, ErrorMode

  # 获取当前模式
  mode = ErrorMode.current()

  # 根据模式记录错误
  import traceback
  if ErrorMode.is_friendly():
      logger.error("连接失败: %s。%s", e, hint.WS_CONNECT_FAILED)
  else:
      logger.error("连接失败: %s。%s\n%s", e, hint.WS_CONNECT_FAILED, traceback.format_exc())

═══════════════════════════════════════════════════════════════════════════
"""

import logging
import os
import sys
import traceback
from functools import wraps
from typing import Callable, Optional

_log = logging.getLogger(__name__)


class ErrorMode:
    """错误显示模式管理器 — 控制错误信息是显示友好原因还是技术堆栈。

    优先级: 命令行参数 > 环境变量 > config.json > 默认(FRIENDLY)
    """

    FRIENDLY = "friendly"
    DEBUG = "debug"

    _mode: Optional[str] = None
    _config_svc: Optional[object] = None

    @classmethod
    def set_config_source(cls, config_svc):
        """设置配置来源（在 ConfigManager 加载后调用）。"""
        cls._config_svc = config_svc

    @classmethod
    def current(cls) -> str:
        """获取当前错误显示模式。"""
        if cls._mode is not None:
            return cls._mode

        # 1) 命令行参数 (最高优先级)
        for arg in sys.argv:
            if arg.startswith("--error-mode="):
                val = arg.split("=", 1)[1].lower()
                if val in ("debug", "d", "trace", "stack"):
                    cls._mode = cls.DEBUG
                    return cls._mode
                cls._mode = cls.FRIENDLY
                return cls._mode

        # 2) 环境变量
        env = os.environ.get("QQLINKER_ERROR_MODE", "").lower()
        if env in ("debug", "d", "trace", "stack"):
            cls._mode = cls.DEBUG
            return cls._mode
        if env in ("friendly", "f", "friendly"):
            cls._mode = cls.FRIENDLY
            return cls._mode

        # 3) config.json
        if cls._config_svc:
            try:
                cfg_mode = cls._config_svc.get("网络连接.错误显示模式")
                if cfg_mode in ("调试", "debug", "Debug"):
                    cls._mode = cls.DEBUG
                    return cls._mode
            except Exception:
                pass

        # 4) 默认友好模式
        cls._mode = cls.FRIENDLY
        return cls._mode

    @classmethod
    def is_friendly(cls) -> bool:
        """当前是否为友好模式。"""
        return cls.current() == cls.FRIENDLY

    @classmethod
    def is_debug(cls) -> bool:
        """当前是否为调试模式。"""
        return cls.current() == cls.DEBUG

    @classmethod
    def reset(cls):
        """重置缓存的模式（用于测试或热重载配置）。"""
        cls._mode = None


def friendly_error(logger_or_func=None, *,
                   friendly_msg: str = "",
                   exc_info: bool = False) -> str:
    """根据当前错误模式生成日志消息。

    Args:
        friendly_msg: 友好模式下的消息（含 hint.xxx 原因解释）。
        exc_info: 是否附加 traceback。

    Returns:
        完整的日志消息字符串。

    用法:
        try:
            ws.connect()
        except Exception as e:
            msg = friendly_error(
                friendly_msg=f"WebSocket 连接失败: {e}。{hint.WS_CONNECT_FAILED}",
                exc_info=True,
            )
            logger.error(msg)
    """
    if ErrorMode.is_friendly():
        return friendly_msg
    # DEBUG 模式: 原因 + 堆栈
    tb_text = ""
    if exc_info:
        tb_text = "\n" + traceback.format_exc()
    return f"{friendly_msg}{tb_text}"


def explain(reason: str, hint_text: str = "", reraise: bool = True) -> Callable:
    """装饰器：捕获函数异常并根据错误模式处理。

    FRIENDLY 模式: 只记录原因解释
    DEBUG 模式:   记录原因 + 完整堆栈

    Args:
        reason: 简短的操作描述。
        hint_text: 具体原因解释。
        reraise: 是否重新抛出异常。
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                hint_detail = hint_text or f"{reason}失败"
                if ErrorMode.is_debug():
                    msg = f"{reason}异常: {e}。{hint_detail}\n{traceback.format_exc()}"
                else:
                    msg = f"{reason}异常: {e}。{hint_detail}"
                logging.getLogger(func.__module__).error(msg)
                if reraise:
                    raise
                return None

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                hint_detail = hint_text or f"{reason}失败"
                if ErrorMode.is_debug():
                    msg = f"{reason}异常: {e}。{hint_detail}\n{traceback.format_exc()}"
                else:
                    msg = f"{reason}异常: {e}。{hint_detail}"
                logging.getLogger(func.__module__).error(msg)
                if reraise:
                    raise
                return None

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator


class ErrorHint:
    """错误原因提示库。"""

    # ━━━ 连接与网络 ━━━
    WS_CONNECT_FAILED = (
        "可能的原因：① OneBot 服务未启动 ② 地址/端口配置错误 "
        "③ 网络防火墙阻止了连接 ④ 令牌(Token)不匹配。"
        "请检查配置中 [网络连接.地址] 和 [网络连接.令牌] 的值。"
    )
    WS_DISCONNECTED = (
        "WebSocket 连接已断开。可能是 OneBot 服务重启、网络波动或对方主动关闭。"
        "框架会自动重连，无需手动干预。"
    )
    WS_SEND_FAILED = (
        "向 QQ 发送消息失败。可能的原因：① WebSocket 连接已断开 "
        "② OneBot 服务响应超时 ③ 目标群聊/用户不存在或已退出。"
    )
    WS_MESSAGE_INVALID = (
        "收到了一条格式异常的 WebSocket 消息。可能是 OneBot 协议版本不兼容，"
        "或消息数据被意外修改。非消息类事件（如通知、请求）会被正常透传。"
    )

    # ━━━ 模块加载 ━━━
    MODULE_INIT_FAILED = (
        "模块初始化失败。可能的原因：① 模块依赖的服务未注册 "
        "② 模块代码存在语法错误 ③ 模块的 on_init() 中抛出了未捕获的异常。"
        "请检查上方日志中该模块的具体错误信息。"
    )
    MODULE_START_FAILED = (
        "模块启动失败（on_init 成功但 on_start 失败）。"
        "可能是模块在启动时访问了尚未就绪的外部资源。"
        "该模块已被卸载，其他模块不受影响。"
    )
    MODULE_STOP_FAILED = (
        "模块停止时出现异常。这不影响框架正常关闭，"
        "但可能导致该模块的资源未完全释放（如文件未关闭、定时任务未取消）。"
    )
    MODULE_INSTANTIATE_FAILED = (
        "模块实例化失败。可能的原因：① 模块类的 __init__ 抛出异常 "
        "② 模块声明了不存在的 required_services。"
        "该模块将被跳过，其他模块不受影响。"
    )
    MODULE_IMPORT_FAILED = (
        "导入模块文件失败。可能的原因：① 模块源文件有语法错误 "
        "② 模块依赖的第三方库未安装 ③ Python 版本不兼容。"
        "请输入 qqdeps check 检查缺失的依赖。"
    )

    # ━━━ 命令执行 ━━━
    COMMAND_EXEC_FAILED = (
        "命令执行异常。可能的原因：① 命令参数格式不正确 "
        "② 命令依赖的游戏未连接 ③ 模块对这个命令的处理逻辑有 bug。"
        "请检查命令用法是否正确（输入 .帮助 查看命令列表）。"
    )
    COMMAND_PERMISSION_DENIED = (
        "权限不足。该命令仅对管理员开放。"
        "如需使用，请联系管理员将你的 QQ 号添加到 [游戏管理.管理员QQ] 配置中。"
    )
    COMMAND_COOLDOWN = (
        "命令冷却中。为了防止滥用，该命令有使用频率限制，请稍后再试。"
    )
    COMMAND_NOT_FOUND = (
        "未找到匹配的命令。输入 .帮助 查看所有可用命令。"
        "如果是刚安装的模块，可能需要重载插件使其生效。"
    )

    # ━━━ 配置 ━━━
    CONFIG_TYPE_MISMATCH = (
        "配置文件中的类型与预期不符。可能的原因：① 手动编辑 config.json 时填错了格式 "
        "② 从旧版本升级时配置文件格式不兼容。框架将使用默认值继续运行。"
    )
    CONFIG_SECTION_MISSING = (
        "配置文件中缺少必要的配置节。这通常是正常的——"
        "框架会在首次加载时自动补全缺失的配置项，无需手动干预。"
    )
    CONFIG_FILE_CORRUPTED = (
        "配置文件损坏或格式错误。可能是手动编辑时引入了 JSON 语法错误。"
        "框架已使用默认配置继续运行。建议备份并删除 config.json 让框架重新生成。"
    )

    # ━━━ 依赖安装 ━━━
    DEPENDENCY_INSTALL_FAILED = (
        "Python 依赖安装失败。可能的原因：① 没有网络连接 "
        "② pip 镜像源不可用（框架会自动尝试多个镜像） ③ 磁盘空间不足。"
        "如果所有镜像都失败，可能是网络环境问题，可以手动 pip install。"
    )
    DEPENDENCY_MISSING = (
        "检测到缺失的 Python 依赖。请输入 qqdeps install 自动安装。"
        "如果自动安装失败，请在控制台手动执行: pip install <包名>"
    )
    DEPENDENCY_TARGET_MISSING = (
        "pip 安装目标目录未设置，依赖安装中止。这可能表示框架初始化不完整。"
    )

    # ━━━ 事件处理 ━━━
    EVENT_HANDLER_FAILED = (
        "某个事件处理器抛出了异常。这不影响其他处理器继续执行，"
        "也不会导致框架崩溃。可能是某个模块的监听函数存在 bug。"
    )
    EVENT_RECURSION_LIMIT = (
        "事件触发链达到最大深度限制（10层），已自动截断。"
        "可能是某个模块在处理事件时又发布了同类事件，形成了死循环。"
        "请检查是否有模块在处理 A 事件时又发布 A 事件。"
    )

    # ━━━ 游戏通信 ━━━
    GAME_COMMAND_FAILED = (
        "游戏指令执行失败。可能的原因：① 游戏服务器未连接 "
        "② 指令格式错误 ③ 适配器不支持该操作。"
    )
    GAME_SYNC_TIMEOUT = (
        "游戏同步指令响应超时。可能的原因：① 游戏服务器负载过高 "
        "② 网络延迟大 ③ 指令执行时间较长。"
    )
    GAME_PLAYER_NOT_FOUND = (
        "未找到指定玩家。该玩家可能已离线，或玩家名拼写有误。"
    )

    # ━━━ 模块市场 ━━━
    MARKET_UPLOAD_FAILED = (
        "模块上传失败。可能的原因：① 文件格式不是 .py "
        "② 上传密钥不正确 ③ 模块数据损坏。"
    )
    MARKET_DOWNLOAD_FAILED = (
        "模块下载失败。可能的原因：① 模块名不存在于市场源中 "
        "② 网络连接失败 ③ 该模块未加入白名单。"
    )
    MARKET_SERVER_FAILED = (
        "模块市场 HTTP 服务异常。可能是端口被占用或权限不足。"
    )

    # ━━━ 通用 ━━━
    SERVICE_NOT_FOUND = (
        "请求的服务未在容器中注册。通常是框架初始化顺序问题，"
        "或模块的 required_services 声明了不存在的服务名。"
    )
    UNEXPECTED_ERROR = (
        "发生了未预期的错误。如果这个问题反复出现，"
        "请查看 framework.log 获取完整信息，或切换为调试模式重新运行。"
        "切换方式: 启动时加 --error-mode=debug 或在 config.json 中设置"
        " [网络连接.错误显示模式] 为 \"调试\"。"
    )
    DATA_CORRUPTED = (
        "数据文件损坏或格式错误。框架会尝试恢复，"
        "但如果数据丢失，可能需要手动删除对应的数据文件让框架重建。"
    )
    RESOURCE_EXHAUSTED = (
        "资源耗尽或达到限制。可能的原因：① 消息频率超限 "
        "② 本地缓存已满 ③ 系统内存不足。"
    )

    # ━━━ 文件完整性 ━━━
    FILE_MISSING_FATAL = (
        "框架关键文件缺失，无法继续运行。可能的原因：\n"
        "① 安装包不完整或被损坏\n"
        "② 文件被手动删除或移动\n"
        "③ 解压/部署时出错\n"
        "建议重新下载并安装完整的框架包。"
    )
    FILE_MISSING_NONFATAL = (
        "非关键文件缺失，框架可降级运行。"
        "如果某功能异常，可能是由于该文件缺失导致。"
    )


# ── 单例 ─────────────────────────────────────────────────────

hint = ErrorHint()
