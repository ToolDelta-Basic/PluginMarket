"""驱动接口 — 内核与可选驱动的抽象协议

═══════════════════════════════════════════════════════════════════════════
 设计原则
═══════════════════════════════════════════════════════════════════════════
 内核永远不 import 驱动，驱动实现协议后注册到内核。
 卸载驱动 = 跳过注册 → 内核使用空实现（noop），零崩溃风险。
═══════════════════════════════════════════════════════════════════════════
"""
from typing import Any, Callable, Dict, List, Optional


class RecoveryProtocol:
    """崩溃恢复驱动协议。"""

    def check_restart_guard(self) -> bool:
        return True

    def get_blocked_path(self) -> str:
        return ""

    def was_crashed(self) -> bool:
        return False

    async def restore_all_checkpoints(self, loaded_modules: Dict[str, Any]) -> int:
        """恢复检查点，返回恢复数。"""
        return 0

    def register_module(self, module: Any) -> None:
        pass

    def start_heartbeat(self, interval: float = 5.0) -> None:
        pass

    def start_checkpoint_loop(self, interval: float = 30.0) -> None:
        pass

    async def stop(self) -> None:
        pass

    def mark_clean_exit(self) -> None:
        pass

    def clean_shutdown(self) -> None:
        pass


class EventBridgeProtocol:
    """事件桥接驱动协议。"""

    async def setup(self, host: Any) -> None:
        pass


class GatekeeperProtocol:
    """能力安全桥梁驱动协议。"""

    def register_default_capabilities(self) -> None:
        pass


class PackageManagerProtocol:
    """包管理驱动协议。"""

    def set_target_dir(self, path: str) -> None:
        pass

    def register_requirements(self, requirements: Dict[str, str]) -> None:
        pass

    def check_missing(self) -> Dict[str, str]:
        return {}


# 模块依赖 → 驱动标签映射
_MODULE_DRIVEN_DEPS = {
    # config_repair 依赖 group_config，group_config 本身是 manager 不是驱动
}
