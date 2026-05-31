"""文件完整性守卫 (Bootstrap Guard)

========================================================================
在框架加载任何模块之前，对关键文件进行校验。
缺失关键文件时，优雅终止并输出明确的修复建议，防止崩溃扩散到宿主编排系统。
========================================================================

设计:
  1. 文件分为 FATAL（缺失则终止）和 NONFATAL（缺失则警告降级）
  2. 检查在 __init__.py 的 import 之前执行
  3. 输出包含: 文件名、类型、影响、修复步骤

配置:
  config.json → 启动检查.跳过完整性校验 = false (默认不跳过)
========================================================================
"""

import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)

# ── 关键文件清单 ──────────────────────────────────────────────

_FRAMEWORK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 缺失则框架无法运行
FATAL_FILES: Dict[str, str] = {
    "core/host.py":            "框架核心调度器，负责模块加载和生命周期管理",
    "core/module.py":          "模块基类，所有模块的父类",
    "core/bus.py":             "事件总线，消息分发的核心",
    "core/services.py":        "服务容器，管理所有服务注册和获取",
    "core/events.py":          "事件定义，所有事件类型的声明",
    "core/routing.py":         "命令路由，处理 QQ 群消息命令分发",
    "core/defguard.py":        "防御层，输入验证和安全标准化",
    "core/error_hints.py":     "错误提示库，提供用户友好的错误解释",
    "managers/config_mgr.py":  "配置管理器，读写 JSON 配置文件",
    "managers/module_mgr.py":  "模块管理器，模块生命周期控制",
    "managers/command_mgr.py": "命令管理器，命令注册和查询",
    "managers/message_mgr.py": "消息管理器，限流发送队列",
    "adapters/base.py":        "适配器基类，定义平台接口契约",
}

# 缺失会导致功能降级但不阻止启动
NONFATAL_FILES: Dict[str, str] = {
    "services/ws_client.py":       "WebSocket 客户端，QQ 消息收发（缺失则无法收发 QQ 消息）",
    "services/debug_engine.py":    "调试引擎，运行时监控（缺失则无监控统计）",
    "services/market_server.py":   "模块市场 HTTP 服务（缺失则无法使用模块市场）",
    "services/dedup/layered_dedup.py": "去重引擎（缺失则消息可能重复）",
    "managers/tool_mgr.py":        "工具管理器（缺失则 AI 工具不可用）",
    "managers/package_mgr.py":     "包管理器（缺失则无法自动安装依赖）",
    "core/autodiscover.py":        "模块发现引擎（缺失则无法加载外部模块）",
    "core/decorators.py":          "装饰器定义（缺失则 @command/@listen 等无效）",
    "core/context.py":             "命令上下文（缺失则命令处理异常）",
    "adapters/tooldelta_adapter.py": "ToolDelta 适配器（缺失则无法在 ToolDelta 环境运行）",
    "testing/mock_adapter.py":     "Mock 适配器（缺失则测试模式不可用）",
}

# 数据文件（缺失可用默认值重建）
DATA_FILES: Dict[str, str] = {
    "datas.json": "前置插件依赖声明，缺失则忽略前置插件",
}


def check_fatal_files(base_dir: Optional[str] = None) -> Tuple[bool, List[str]]:
    """检查所有关键文件是否存在。

    Args:
        base_dir: 框架根目录（默认自动检测）。

    Returns:
        (ok, missing_files) — ok=True 表示全部存在。
    """
    if base_dir is None:
        base_dir = _FRAMEWORK_DIR

    missing = []
    for rel_path, description in FATAL_FILES.items():
        full = os.path.join(base_dir, rel_path)
        if not os.path.isfile(full):
            missing.append(f"{rel_path} ({description})")
    return len(missing) == 0, missing


def check_all_files(base_dir: Optional[str] = None) -> Dict[str, List[Tuple[str, str]]]:
    """检查所有文件（FATAL + NONFATAL + DATA）。

    Returns:
        {
            "fatal_missing": [(path, description), ...],
            "nonfatal_missing": [...],
            "data_missing": [...],
        }
    """
    if base_dir is None:
        base_dir = _FRAMEWORK_DIR

    result = {
        "fatal_missing": [],
        "nonfatal_missing": [],
        "data_missing": [],
    }

    for name, files in [("fatal_missing", FATAL_FILES),
                         ("nonfatal_missing", NONFATAL_FILES),
                         ("data_missing", DATA_FILES)]:
        for rel_path, description in files.items():
            full = os.path.join(base_dir, rel_path)
            if not os.path.isfile(full):
                result[name].append((rel_path, description))

    return result


def bootstrap_integrity_check(base_dir: Optional[str] = None,
                               skip: bool = False) -> bool:
    """启动前完整性校验——在 import 任何模块之前执行。

    这是框架的第一道防线。在 __init__.py 的 import 之前调用。
    缺失关键文件时，优雅终止而不是让 Python 在深层代码中崩溃。

    Args:
        base_dir: 框架根目录。
        skip: 是否跳过检查（用户可通过配置禁用）。

    Returns:
        True 表示检查通过，可以继续加载。

    注意: 失败时直接 exit(1)，不返回 False。
    """
    if skip:
        return True

    from .error_hints import hint

    # 快速检查 fatal 文件
    ok, missing = check_fatal_files(base_dir)

    if not ok:
        msg_lines = [
            "",
            "╔══════════════════════════════════════════════════════════╗",
            "║  ❌ 群服互通框架 启动失败                                ║",
            "╠══════════════════════════════════════════════════════════╣",
            "║  关键文件缺失，框架无法继续运行。                       ║",
            "╠══════════════════════════════════════════════════════════╣",
        ]
        for i, m in enumerate(missing[:10], 1):
            display = m[:60]
            msg_lines.append(f"║  {i}. {display}")
            if len(m) > 60:
                msg_lines.append(f"║     {m[60:]}")

        if len(missing) > 10:
            msg_lines.append(f"║  ... 及其他 {len(missing) - 10} 个文件")

        msg_lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            "║  " + hint.FILE_MISSING_FATAL[:58],
        ])

        # 对齐第二个续行
        if len(hint.FILE_MISSING_FATAL) > 58:
            for i in range(58, len(hint.FILE_MISSING_FATAL), 58):
                msg_lines.append("║  " + hint.FILE_MISSING_FATAL[i:i+58])

        msg_lines.extend([
            "║  框架包位置: " + (base_dir or _FRAMEWORK_DIR)[:50],
            "╚══════════════════════════════════════════════════════════╝",
            "",
            "💡 如需跳过此检查（不推荐），设置环境变量:",
            "   QQLINKER_SKIP_INTEGRITY=1",
            "",
        ])

        print("\n".join(msg_lines), file=sys.stderr)
        sys.exit(1)

    # 检查 nonfatal 文件，只记录警告
    for rel_path, description in NONFATAL_FILES.items():
        full = os.path.join(base_dir or _FRAMEWORK_DIR, rel_path)
        if not os.path.isfile(full):
            _log.warning(
                "非关键文件缺失: %s (%s)。部分功能可能不可用。%s",
                rel_path, description, hint.FILE_MISSING_NONFATAL,
            )

    # 检查数据文件
    for rel_path, description in DATA_FILES.items():
        full = os.path.join(base_dir or _FRAMEWORK_DIR, rel_path)
        if not os.path.isfile(full):
            _log.info(
                "数据文件 '%s' 不存在 (%s)。框架将使用默认值。", rel_path, description
            )

    return True
