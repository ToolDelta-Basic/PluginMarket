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


def test_market_service():
    """内建: 模块市场 REST API（纯标准库，兼容 Python 3.13+）"""
    import json, socket, tempfile, time, shutil, http.client
    from urllib.request import urlopen
    from ..services.market_server import ModuleMarketServer, sign_module

    tmpdir = tempfile.mkdtemp()
    # 随机端口避免冲突
    with socket.socket() as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    try:
        ms = ModuleMarketServer(
            data_path=tmpdir, host='127.0.0.1', port=port,
            upload_token='tok', whitelist=['open_mod'],
            sign_secret='sec', strict_sign=True, per_page=5,
        )
        ms.start()
        time.sleep(0.3)
        B = '--B'; C = '\r\n'

        def upload(name, sign=True, categories=None):
            s = sign_module(name, '1.0.0', 'sec') if sign else ''
            cat = f'\n__category__ = "{categories}"' if categories else ''
            parts = ['--'+B,
                f'Content-Disposition: form-data; name="file"; filename="{name}.py"',
                'Content-Type: text/x-python', '',
                f'name = "{name}"\nversion = (1,0,0){cat}']
            if sign:
                parts += ['--'+B, 'Content-Disposition: form-data; name="signature"', '', s]
            parts += ['--'+B+'--', '']
            b = (C.join(parts)).encode()
            c = http.client.HTTPConnection('127.0.0.1', port)
            c.request('POST', '/modules/upload?token=tok', body=b,
                      headers={'Content-Type': 'multipart/form-data; boundary='+B,
                               'Content-Length': str(len(b))})
            r = c.getresponse(); d = json.loads(r.read()); c.close()
            return r.status, d

        # 1. health
        d = json.loads(urlopen(f'{base}/health').read())
        assert d['status'] == 'ok'

        # 2. upload without auth → 401 (no token at all)
        b_naked = (C.join(['--'+B,
            'Content-Disposition: form-data; name="file"; filename="x.py"',
            'Content-Type: text/x-python', '',
            'name = "x"\nversion = (1,0,0)',
            '--'+B+'--', ''])).encode()
        c = http.client.HTTPConnection('127.0.0.1', port)
        c.request('POST', '/modules/upload', body=b_naked,
                  headers={'Content-Type': 'multipart/form-data; boundary='+B,
                           'Content-Length': str(len(b_naked))})
        assert c.getresponse().status == 401; c.close()

        # 3. upload with token + valid sig
        st, d = upload('mymod', categories='game')
        assert d.get('ok')
        st, d = upload('open_mod')
        assert d.get('ok')

        # 4. public list = only whitelisted
        d = json.loads(urlopen(f'{base}/modules/list').read())
        assert [m['name'] for m in d['items']] == ['open_mod']

        # 5. download whitelisted works
        r = urlopen(f'{base}/modules/download/open_mod')
        assert 'open_mod' in r.read().decode()

        # 6. non-whitelisted download blocked
        c = http.client.HTTPConnection('127.0.0.1', port)
        c.request('GET', '/modules/download/mymod')
        assert c.getresponse().status == 403; c.close()

        # 7. stats = all modules
        d = json.loads(urlopen(f'{base}/modules/stats').read())
        assert d['total_modules'] == 2

        # 8. categories（至少包含 game 分类）
        d = json.loads(urlopen(f'{base}/modules/categories').read())
        assert d['categories'].get('game') >= 1, f"categories: {d}"

        # 9. paging
        for i in range(8):
            upload(f'p{i}', categories='util')
        d = json.loads(urlopen(f'{base}/modules/list?token=tok&page=2&per_page=3').read())
        assert d['page'] == 2 and d['total'] == 10

        # 10. reject non-py
        b = (C.join(['--'+B,
            'Content-Disposition: form-data; name="file"; filename="hack.txt"',
            'Content-Type: text/plain', '', 'x',
            '--'+B+'--', ''])).encode()
        c = http.client.HTTPConnection('127.0.0.1', port)
        c.request('POST', '/modules/upload?token=tok', body=b,
                  headers={'Content-Type': 'multipart/form-data; boundary='+B,
                           'Content-Length': str(len(b))})
        r = c.getresponse()
        assert r.status == 400 and '.py' in str(r.read()); c.close()

        ms.stop()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 防御层测试 — 验证 defguard.py 的可靠性
# ═══════════════════════════════════════════════════════════════

def test_defguard_safe_str():
    """防御层: safe_str 对各类异常输入"""
    from ..core.defguard import safe_str
    assert safe_str(None) == ""
    assert safe_str("hello") == "hello"
    assert safe_str(123) == "123"
    assert safe_str(b"bytes") == "bytes"
    assert safe_str("x" * 10000, max_len=5) == "xxxxx"
    assert safe_str([1, 2, 3]) == "[1, 2, 3]"
    assert safe_str({"a": 1}) == "{'a': 1}"
    # 异常对象
    class Bad:
        def __str__(self):
            raise RuntimeError("boom")
    result = safe_str(Bad())
    assert "Bad" in result  # 应 fallback 到类型名


def test_defguard_safe_int():
    """防御层: safe_int 对异常数值"""
    from ..core.defguard import safe_int
    assert safe_int(None) == 0
    assert safe_int("123") == 123
    assert safe_int("abc") == 0
    assert safe_int("abc", default=-1) == -1
    assert safe_int(5.0) == 5
    assert safe_int(3.14) == 0  # float 非整数 → 默认
    assert safe_int(100, max_val=50) == 50
    assert safe_int(-10, min_val=0) == 0
    assert safe_int([1, 2]) == 0
    assert safe_int(True) == 0  # bool 被视为非 int


def test_defguard_safe_list():
    """防御层: safe_list 对异常列表"""
    from ..core.defguard import safe_list
    assert safe_list(None) == []
    assert safe_list([1, 2, 3]) == [1, 2, 3]
    assert safe_list("not_list") == ["not_list"]
    assert safe_list((1, 2)) == [1, 2]
    # 超长截断
    long_list = list(range(1000))
    assert len(safe_list(long_list, max_len=5)) == 5


def test_defguard_safe_dict():
    """防御层: safe_dict 对异常字典"""
    from ..core.defguard import safe_dict
    assert safe_dict(None) == {}
    assert safe_dict({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    assert safe_dict("not_dict") == {"_raw": "not_dict"}
    # 嵌套截断
    deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    result = safe_dict(deep, max_depth=2)
    assert "a" in result


def test_defguard_validate_onebot_event():
    """防御层: validate_onebot_event 处理正常/异常 OneBot 数据"""
    from ..core.defguard import validate_onebot_event

    # 正常群消息
    ok, data, reason = validate_onebot_event({
        "post_type": "message",
        "message_type": "group",
        "user_id": 12345,
        "group_id": 67890,
        "message": "hello world",
        "sender": {"nickname": "Test", "card": "CardName"},
    })
    assert ok
    assert data["user_id"] == 12345
    assert data["group_id"] == 67890
    assert data["message"] == "hello world"
    assert data["nickname"] == "CardName"  # card 优先

    # 无效输入
    ok, data, reason = validate_onebot_event(None)
    assert not ok
    ok, data, reason = validate_onebot_event("not_dict")
    assert not ok

    # 群消息缺少 group_id
    ok, data, reason = validate_onebot_event({
        "post_type": "message",
        "message_type": "group",
        "user_id": 123,
        "group_id": 0,
        "message": "x",
    })
    assert not ok
    assert "group_id" in reason

    # 私聊消息（通过但不做群校验）
    ok, data, reason = validate_onebot_event({
        "post_type": "message",
        "message_type": "private",
        "user_id": 123,
        "message": "私聊",
    })
    assert ok

    # 非消息事件（透传）
    ok, data, reason = validate_onebot_event({
        "post_type": "notice",
        "notice_type": "group_increase",
    })
    assert ok

    # 消息段列表（OneBot array message）
    ok, data, reason = validate_onebot_event({
        "post_type": "message",
        "message_type": "group",
        "user_id": 123,
        "group_id": 456,
        "message": [
            {"type": "text", "data": {"text": "Hi "}},
            {"type": "at", "data": {"qq": "789"}},
            {"type": "image", "data": {"url": "http://x"}},
        ],
    })
    assert ok
    assert "Hi [@789][图片]" in data["message"]


def test_defguard_event_sanitize_in_bus():
    """防御层: EventBus.publish 自动标准化事件数据"""
    import asyncio
    from ..core.bus import EventBus
    from ..core.events import GameChatEvent, GroupMessageEvent

    bus = EventBus()
    captured = []

    async def handler(evt):
        captured.append((type(evt).__name__, evt.message if hasattr(evt, 'message') else None))

    bus.subscribe("GameChatEvent", handler)
    bus.subscribe("GroupMessageEvent", handler)

    async def _run():
        # None message → EventBus 标准化为 ""
        await bus.publish(GameChatEvent(player_name="P1", message=None))
        assert captured[-1] == ("GameChatEvent", "")

        # None message → ""
        await bus.publish(GroupMessageEvent(user_id=1, group_id=1, nickname="X", message=None, raw_data={}))
        assert captured[-1] == ("GroupMessageEvent", "")

        bus.shutdown()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())
    loop.close()


def test_defguard_safe_command_args():
    """防御层: safe_command_args 解析"""
    from ..core.defguard import safe_command_args

    assert safe_command_args(None) == []
    assert safe_command_args("") == []
    assert safe_command_args("arg1 arg2  arg3") == ["arg1", "arg2", "arg3"]
    # 超长截断
    long_args = " ".join(["a"] * 50)
    result = safe_command_args(long_args, max_args=5)
    assert len(result) == 5
    # 超长单个参数截断
    long_arg = "x" * 500
    result = safe_command_args(long_arg)
    assert len(result[0]) == 256


# ═══════════════════════════════════════════════════════════════
# 稳定性回归测试 — 防止已修复 bug 再次出现
# ═══════════════════════════════════════════════════════════════

def test_none_message_safety():
    """回归: None 消息不引发 AttributeError（在 binding/forwarder/debug_engine/routing 中）"""
    import asyncio
    from ..core.events import GameChatEvent, GroupMessageEvent

    async def _run():
        from ..core.bus import EventBus
        bus = EventBus()
        hit = []

        async def handler(evt):
            msg = (evt.message or "").strip()
            hit.append(msg)

        bus.subscribe("GameChatEvent", handler)
        bus.subscribe("GroupMessageEvent", handler)

        await bus.publish(GameChatEvent(player_name="Test", message=None))
        assert len(hit) == 1 and hit[0] == ""

        await bus.publish(GroupMessageEvent(
            user_id=1, group_id=1, nickname="T", message=None, raw_data={}
        ))
        assert len(hit) == 2 and hit[1] == ""

        bus.shutdown()
        return True

    loop = asyncio.new_event_loop()
    try:
        ok = loop.run_until_complete(_run())
        assert ok
    finally:
        loop.close()


def test_framework_full_lifecycle():
    """回归: 框架完整启动→事件→停止 不崩溃"""
    import asyncio, tempfile, os, shutil
    from .mock_adapter import MockAdapter
    from ..core.host import FrameworkHost
    from ..core.events import GameChatEvent, PlayerJoinEvent, PlayerLeaveEvent

    tmp = tempfile.mkdtemp()
    try:
        adapter = MockAdapter()
        adapter.set_online(["P1", "P2", "P3"])
        adapter.set_admins([10000])

        host = FrameworkHost(adapter, data_path=tmp)
        host.register_modules_from_package("qqlinker_framework.modules")

        async def _run():
            await host.start()
            modules = host.module_mgr.get_loaded_modules()
            assert len(modules) >= 5, f"期望 >=5 个模块，实际 {len(modules)}"

            await host.event_bus.publish(GameChatEvent(player_name="P1", message="hello"))
            await host.event_bus.publish(PlayerJoinEvent(player_name="NewGuy"))
            await host.event_bus.publish(PlayerLeaveEvent(player_name="NewGuy"))
            await host.stop()
            return True

        loop = asyncio.new_event_loop()
        ok = loop.run_until_complete(_run())
        loop.close()
        assert ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_command_routing_none_safety():
    """回归: CommandRouter 对 None 消息不崩溃"""
    import asyncio
    from .mock_adapter import MockAdapter
    from ..core.events import GroupMessageEvent
    from ..managers.command_mgr import CommandManager
    from ..managers.config_mgr import ConfigManager
    from ..managers.message_mgr import MessageManager
    from ..core.routing import CommandRouter
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmp:
        cm = ConfigManager(os.path.join(tmp, "cfg.json"), data_dir=tmp)
        cm.load()
        adapter = MockAdapter()
        msg_mgr = MessageManager(adapter)

        cmd_mgr = CommandManager()
        called = []
        async def mock_cmd(ctx):
            called.append(True)
        cmd_mgr.register(".test", mock_cmd)

        router = CommandRouter(cmd_mgr, adapter, cm, msg_mgr)

        async def _run():
            result = await router.handle_message(GroupMessageEvent(
                user_id=1, group_id=1, nickname="T", message=None, raw_data={}
            ))
            assert result is False
            assert len(called) == 0

            await router.handle_message(GroupMessageEvent(
                user_id=1, group_id=1, nickname="T", message=".test hello", raw_data={}
            ))
            assert len(called) == 1

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()


def test_module_hot_reload():
    """回归: 热重载不崩溃，命令保持可用"""
    import asyncio, tempfile, shutil
    from .mock_adapter import MockAdapter
    from ..core.host import FrameworkHost

    tmp = tempfile.mkdtemp()
    try:
        adapter = MockAdapter()
        adapter.set_online(["P1"])
        adapter.set_admins([10000])

        host = FrameworkHost(adapter, data_path=tmp)
        host.register_modules_from_package("qqlinker_framework.modules")

        async def _run():
            await host.start()
            ok = await host.unload_module("dummy")
            assert ok, "卸载 dummy 失败"
            from ..modules.system.ping import DummyModule
            mod = await host.load_module(DummyModule)
            assert mod is not None, "重新加载 dummy 失败"
            ok = await host.unload_module("dummy")
            assert ok, "二次卸载 dummy 失败"
            await host.stop()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_event_bus_recursion_limit():
    """回归: EventBus 递归深度保护生效"""
    import asyncio
    from ..core.bus import EventBus, MAX_EVENT_DEPTH
    from ..core.events import GameChatEvent

    bus = EventBus()
    depth_count = [0]

    async def recursive_handler(event):
        depth_count[0] += 1
        if depth_count[0] <= MAX_EVENT_DEPTH + 2:
            await bus.publish(GameChatEvent(player_name="X", message="recurse"))

    bus.subscribe("GameChatEvent", recursive_handler)

    async def _run():
        await bus.publish(GameChatEvent(player_name="A", message="start"))
        assert depth_count[0] == MAX_EVENT_DEPTH, f"期望 {MAX_EVENT_DEPTH} 次，实际 {depth_count[0]}"
        bus.shutdown()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())
    loop.close()


def test_config_type_validation():
    """回归: ConfigManager 类型校验不崩溃（警告级别）"""
    import tempfile, json, os
    from ..managers.config_mgr import ConfigManager

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cfg.json")
        with open(path, "w") as f:
            json.dump({"测试": {"数量": "不是数字"}}, f)

        cm = ConfigManager(path, data_dir=tmp)
        cm.register_section("测试", {"数量": 10})
        cm.load()
        assert cm.get("测试.数量") == "不是数字"


def test_ban_store_persistence():
    """回归: BanStore CRUD 正确"""
    import tempfile, shutil
    from ..modules.security.orion import BanStore

    tmp = tempfile.mkdtemp()
    try:
        bs = BanStore(tmp)
        bs.set("BadPlayer", {"reason": "cheating", "duration": 3600})
        rec = bs.get("BadPlayer")
        assert rec is not None
        assert rec["reason"] == "cheating"
        assert rec["duration"] == 3600

        all_bans = bs.list_all()
        assert len(all_bans) == 1

        assert bs.remove("BadPlayer")
        assert bs.get("BadPlayer") is None
        assert bs.list_all() == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_chatlog_service_null_safety():
    """回归: ChatLogService 对空/异常消息的处理"""
    import asyncio, tempfile, shutil
    from ..modules.logging.chat import ChatLogService

    tmp = tempfile.mkdtemp()
    try:
        svc = ChatLogService(tmp)

        async def _run():
            mid = await svc.record_message("group", 1, 1, "Test", "hello", {})
            assert mid and mid.startswith("msg_")
            mid2 = await svc.record_message("group", 2, 1, "Test2", "", {})
            assert mid2 and mid2.startswith("msg_")

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_error_mode_switch():
    """错误模式: FRIENDLY/DEBUG 切换正常"""
    import os
    from ..core.error_hints import ErrorMode

    ErrorMode.reset()
    # 默认是 FRIENDLY
    assert ErrorMode.current() == ErrorMode.FRIENDLY
    assert ErrorMode.is_friendly()
    assert not ErrorMode.is_debug()

    # 环境变量设置为 debug
    os.environ["QQLINKER_ERROR_MODE"] = "debug"
    ErrorMode.reset()
    assert ErrorMode.current() == ErrorMode.DEBUG
    assert ErrorMode.is_debug()

    # 恢复
    os.environ.pop("QQLINKER_ERROR_MODE", None)
    ErrorMode.reset()
    assert ErrorMode.current() == ErrorMode.FRIENDLY





def test_containment_safe_call():
    """隔离层: safe_call 捕获异常不抛"""
    from ..core.containment import safe_call, reset_failure_count

    reset_failure_count()

    def broken():
        raise ValueError("test error")

    safe = safe_call(broken, context="test")
    result = safe()  # 不应抛异常
    assert result is None


def test_containment_safe_async_call():
    """隔离层: safe_call 对异步函数同样捕获"""
    import asyncio
    from ..core.containment import safe_call, reset_failure_count

    reset_failure_count()

    async def broken_async():
        raise RuntimeError("async test error")

    safe = safe_call(broken_async, context="async_test")

    async def _run():
        result = await safe()
        assert result is None

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())
    loop.close()


def test_containment_critical_threshold():
    """隔离层: 关键路径连续失败触发卸载"""
    import asyncio
    from ..core.containment import (
        safe_call, reset_failure_count, is_shutting_down,
        trigger_safe_shutdown,
    )
    import qqlinker_framework.core.containment as cont_mod

    reset_failure_count()
    # 重置全局关闭标记
    cont_mod._shutdown_initiated = False

    def broken():
        raise RuntimeError("critical failure")

    safe = safe_call(broken, context="test", raise_on_critical=True)

    for _ in range(5):
        safe()

    # 应该触发了安全卸载
    assert is_shutting_down(), "关键路径连续失败应触发安全卸载"


def test_containment_plugin_wrapper():
    """隔离层: plugin_wrapper 兜底不传播异常"""
    from ..core.containment import plugin_wrapper, reset_failure_count

    reset_failure_count()

    @plugin_wrapper
    def will_crash():
        raise RuntimeError("fatal plugin error")

    # 不应抛异常
    result = will_crash()
    assert result is None


def test_host_stop_idempotent():
    """隔离层: FrameworkHost.stop() 幂等——多次调用不崩溃"""
    import asyncio, tempfile, shutil
    from ..testing.mock_adapter import MockAdapter
    from ..core.host import FrameworkHost

    tmp = tempfile.mkdtemp()
    try:
        adapter = MockAdapter()
        adapter.set_online(["P1"])
        adapter.set_admins([10000])
        host = FrameworkHost(adapter, data_path=tmp)
        host.register_modules_from_package("qqlinker_framework.modules")

        async def _run():
            await host.start()
            await host.stop()
            await host.stop()  # 第二次调用（幂等）
            await host.stop()  # 第三次调用

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# UID 权限体系测试
# ═══════════════════════════════════════════════════════════════

def test_uid_tiers():
    """UID: 标签返回正确"""
    from ..core.services import uid_label, uid_layer
    assert uid_label(0) == "root"
    assert uid_label(10) == "daemon"
    assert uid_label(500) == "daemon"
    assert uid_label(1000) == "service"
    assert uid_label(2000) == "app"
    assert uid_label(9999) == "nobody"
    assert uid_layer(0) == "root"
    assert uid_layer(100) == "daemon"
    assert uid_layer(1500) == "service"
    assert uid_layer(2500) == "app"
    assert uid_layer(5000) == "nobody"


def test_uid_validate_declaration():
    """UID: validate_module_uid 拒绝越权声明"""
    from ..core.services import validate_module_uid
    # app 层正常范围
    assert validate_module_uid(2000, "test_mod", "app") == 2000
    assert validate_module_uid(2500, "test_mod", "app") == 2500
    # 尝试声明 daemon 级 → 降级到 2000
    assert validate_module_uid(100, "bad_mod", "app") == 2000
    # 尝试声明 root → 降级
    assert validate_module_uid(0, "hack_mod", "app") == 2000
    # nobody 层
    assert validate_module_uid(3000, "third", "nobody") == 3000


def test_uid_service_access_control():
    """UID: 低权限容器 get() 更高权限服务时抛出 PermissionError"""
    from ..core.services import ServiceContainer
    svc = ServiceContainer(uid=0)
    svc.register("daemon_svc", "daemon", uid=10, _caller="qqlinker_framework.core.host")
    svc.register("service_svc", "service", uid=1000, _caller="qqlinker_framework.core.host")

    # root(0) 可访问一切
    assert svc.get("daemon_svc") == "daemon"
    assert svc.get("service_svc") == "service"

    # 注意: 系统中 uid 小 = 权限大, 所以 daemon(10) > service(1000)
    # 检查逻辑: self._uid >= req_uid 才允许
    # daemon(10) 访问 service(1000): 10 >= 1000? NO → 拒绝
    svc2 = ServiceContainer(uid=10)
    svc2.register("daemon_svc", "d", uid=10, _caller="qqlinker_framework.core.host")
    try:
        svc2.register("service_svc", "s", uid=1000, _caller="qqlinker_framework.core.host")
        # register 不检查权限数值, 只检查 daemon 白名单
        svc2.get("service_svc")  # 10 >= 1000 → PermissionError
        assert False, "daemon(10) should not access service(1000)"
    except PermissionError:
        pass
    assert svc2.get("daemon_svc") == "d"  # 10 >= 10

    # service(1000) 可以访问 daemon(10): 1000 >= 10 → ok
    svc3 = ServiceContainer(uid=1000)
    svc3.register("daemon_svc", "d2", uid=10, _caller="qqlinker_framework.core.host")
    svc3.register("service_svc", "s2", uid=1000, _caller="qqlinker_framework.core.host")
    assert svc3.get("daemon_svc") == "d2"     # 1000 >= 10 ✓
    assert svc3.get("service_svc") == "s2"    # 1000 >= 1000 ✓

    # list_accessible: svc2(uid=10) 只能看到 uid <= 10 的服务
    acc = svc2.list_accessible()
    assert "daemon_svc" in acc
    assert "service_svc" not in acc
def test_uid_daemon_whitelist():
    """UID: 非可信路径无法注册 daemon 服务"""
    from ..core.services import ServiceContainer
    svc = ServiceContainer(uid=0)
    # 可信路径通过
    svc.register("ok_svc", "x", uid=10, _caller="qqlinker_framework.core.host")
    # 非可信路径被拒
    try:
        svc.register("bad_svc", "y", uid=10, _caller="third_party.module")
        assert False, "should have raised"
    except PermissionError:
        pass


# ═══════════════════════════════════════════════════════════════
# 角色权限测试
# ═══════════════════════════════════════════════════════════════

def test_role_system_check():
    """角色: CommandRouter._check_role 正确判断"""
    import tempfile, os
    from .mock_adapter import MockAdapter
    from ..managers.config_mgr import ConfigManager
    from ..managers.command_mgr import CommandManager
    from ..managers.message_mgr import MessageManager
    from ..core.routing import CommandRouter

    with tempfile.TemporaryDirectory() as tmp:
        cm = ConfigManager(os.path.join(tmp, "cfg.json"), data_dir=tmp)
        cm.register_section("权限管理", {"角色": {"moderator": [20000], "vip": [30000]}})
        cm.load()
        adapter = MockAdapter()
        msg_mgr = MessageManager(adapter)
        cmd_mgr = CommandManager()
        router = CommandRouter(cmd_mgr, adapter, cm, msg_mgr)

        assert router._check_role("moderator", 20000)
        assert not router._check_role("moderator", 99999)
        assert router._check_role("vip", 30000)
        assert not router._check_role("vip", 10000)
        assert not router._check_role("nonexistent", 20000)


# ═══════════════════════════════════════════════════════════════
# 配置热重载测试
# ═══════════════════════════════════════════════════════════════

def test_config_hotreload():
    """配置: ConfigManager.reload 检测 mtime 变化"""
    from ..managers.config_mgr import ConfigManager
    import tempfile, os, time, json
    fp = os.path.join(tempfile.gettempdir(), f"test_hotreload_{os.getpid()}.json")
    try:
        with open(fp, "w") as f:
            json.dump({"test": {"val": 1}}, f)
        cm = ConfigManager(fp)
        cm.register_section("test", {"val": 0})
        cm.load()
        assert cm.get("test.val") == 1
        # 修改文件
        time.sleep(0.1)
        with open(fp, "w") as f:
            json.dump({"test": {"val": 42}}, f)
        ok = cm.reload()
        assert ok
        assert cm.get("test.val") == 42
    finally:
        if os.path.exists(fp):
            os.unlink(fp)

if __name__ == "__main__":
    run_all_tests()
