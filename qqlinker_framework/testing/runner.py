# testing/runner.py
"""通用测试运行器 — 收集并运行所有测试。

用法:
  python -m qqlinker_framework.testing.runner
  python -m qqlinker_framework --test
"""
import importlib
import inspect
import logging
import os
import sys
import traceback
from typing import Callable, List, Tuple


def discover_tests(package_prefix: str = "tests") -> List[Tuple[str, Callable]]:
    """自动发现所有 test_ 前缀的函数。

    扫描路径:
      1. tests/ 目录下的 test_*.py 文件
      2. 本包内的 test_ 函数
    """
    tests: List[Tuple[str, Callable]] = []

    # 1. 从 tests/ 目录加载
    tests_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "tests"
    )
    if os.path.isdir(tests_dir):
        sys.path.insert(0, os.path.dirname(tests_dir))
        for fname in sorted(os.listdir(tests_dir)):
            if fname.startswith("test_") and fname.endswith(".py"):
                modname = fname[:-3]
                try:
                    mod = importlib.import_module(modname)
                    for name, obj in inspect.getmembers(mod):
                        if name.startswith("test_") and callable(obj):
                            tests.append((f"{modname}.{name}", obj))
                except Exception as e:
                    logging.warning("加载测试模块 %s 失败: %s", modname, e)

    # 2. 从本模块显式注册的测试
    for name, obj in inspect.getmembers(sys.modules[__name__]):
        if name.startswith("test_") and callable(obj):
            tests.append((name, obj))

    return tests


def run_all_tests(
    tests: List[Tuple[str, Callable]] | None = None,
    verbose: bool = True,
) -> bool:
    """运行所有测试并打印结果。

    Returns:
        True 表示全部通过。
    """
    if tests is None:
        tests = discover_tests()

    if not tests:
        print("⚠ 未发现任何测试")
        return True

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            if verbose:
                print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {name}: {type(e).__name__}: {e}")
            if verbose:
                traceback.print_exc()
            failed += 1

    total = passed + failed
    print(f"\n{'='*50}")
    print(f"  {passed}/{total} 通过")
    if failed:
        print(f"  ❌ {failed} 个测试失败")
    else:
        print(f"  ✅ 全部通过")

    return failed == 0


# ── 内建快速测试 ──

def test_mock_adapter_core():
    """内建: MockAdapter 基本操作"""
    from .mock_adapter import MockAdapter
    a = MockAdapter()
    a.set_online(["P1", "P2"])
    assert a.get_online_players() == ["P1", "P2"]
    a.send_game_command("list")
    assert any("list" in c for c in a._commands)
    a.send_group_msg(123, "hi")
    assert (123, "hi") in a._group_messages
    a.set_admins([100])
    assert a.is_user_admin(100)
    assert not a.is_user_admin(999)


def test_mock_lifecycle():
    """内建: MockAdapter 生命周期事件"""
    from .mock_adapter import MockAdapter
    a = MockAdapter()
    called = []
    a.listen_active(lambda: called.append("active"))
    a.fire_active()
    assert called == ["active"]
    assert a._active

def test_config_schema():
    """内建: config_schema 注入"""
    import tempfile, json
    from ..managers.config_mgr import ConfigManager
    from ..core.services import ServiceContainer
    from ..core.module import Module

    tmp = os.path.join(tempfile.gettempdir(), f"test_cfg_{os.getpid()}.json")
    with open(tmp, "w") as f:
        json.dump({"测试": {"是否调试": False, "条数": 10}}, f)
    try:
        cm = ConfigManager(tmp, data_dir=tempfile.gettempdir())
        sc = ServiceContainer()
        sc.register("config", cm)
        cm.register_section("测试", {"是否调试": True, "条数": 5})
        cm.load()

        class Inj(Module):
            name = "inj"
            required_services = []
            config_schema = {"debug": ("测试.是否调试", True), "count": ("测试.条数", 5)}
            async def on_init(self): pass

        m = Inj(sc, None)
        m._apply_conventions()
        assert m.cfg_debug is False
        assert m.cfg_count == 10
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def test_json_db():
    """内建: JsonDatabase CRUD"""
    import tempfile
    from ..core.module import JsonDatabase
    with tempfile.TemporaryDirectory() as tmp:
        db = JsonDatabase(tmp, ["users", "items"])
        assert hasattr(db, "users")
        db.users.set("u1", {"name": "Alice"})
        assert db.users.get("u1")["name"] == "Alice"


if __name__ == "__main__":
    run_all_tests()
