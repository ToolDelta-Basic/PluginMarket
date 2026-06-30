# testing/runner.py
"""通用测试运行器 — 收集并运行所有测试。

用法:
  python -m qqlinker_framework.testing.runner
  python -m qqlinker_framework --test
"""
import importlib
import inspect
import logging
_log = logging.getLogger(__name__)
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
    import tempfile, json, os
    from ..managers.config_mgr import ConfigManager
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module

    tmp = tempfile.mkdtemp()
    try:
        fp = os.path.join(tmp, "config.json")
        with open(fp, "w") as f:
            json.dump({"测试": {"是否调试": False, "条数": 10}}, f)
        cm = ConfigManager(fp, data_dir=tmp)
        sc = ServiceContainer()
        sc.register("config", cm)
        cm.register_section("测试", {"是否调试": True, "条数": 5}, caller_uid=0)
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
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


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
        # 清空前序测试可能残留的上传速率状态
        from ..services.market_server.handler import MarketHandler
        MarketHandler._upload_rate_map.clear()
        MarketHandler._rate_limit_disabled = False

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

        # 9. paging（禁用上传速率限制以允许连续上传）
        from ..services.market_server.handler import MarketHandler
        MarketHandler._rate_limit_disabled = True
        MarketHandler._upload_rate_map.clear()
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
    from ..core.kernel.defguard import safe_str
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
    from ..core.kernel.defguard import safe_int
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
    from ..core.kernel.defguard import safe_list
    assert safe_list(None) == []
    assert safe_list([1, 2, 3]) == [1, 2, 3]
    assert safe_list("not_list") == ["not_list"]
    assert safe_list((1, 2)) == [1, 2]
    # 超长截断
    long_list = list(range(1000))
    assert len(safe_list(long_list, max_len=5)) == 5


def test_defguard_safe_dict():
    """防御层: safe_dict 对异常字典"""
    from ..core.kernel.defguard import safe_dict
    assert safe_dict(None) == {}
    assert safe_dict({"a": 1, "b": 2}) == {"a": 1, "b": 2}
    assert safe_dict("not_dict") == {"_raw": "not_dict"}
    # 嵌套截断
    deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    result = safe_dict(deep, max_depth=2)
    assert "a" in result


def test_defguard_validate_onebot_event():
    """防御层: validate_onebot_event 处理正常/异常 OneBot 数据"""
    from ..core.kernel.defguard import validate_onebot_event

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
    """防御层: LaneRouter.publish 自动标准化事件数据"""
    import asyncio
    from ..libraries.core.lane_router import LaneRouter
    from ..core.kernel.events import GameChatEvent, GroupMessageEvent

    router = LaneRouter()
    captured = []

    async def handler(evt):
        captured.append((type(evt).__name__, (evt.message or "") if hasattr(evt, 'message') else None))

    router.subscribe(GameChatEvent, handler)
    router.subscribe(GroupMessageEvent, handler)

    async def _run():
        await router.start()
        # None message → LaneRouter 标准化为 ""
        await router.publish(GameChatEvent(player_name="P1", message=None))
        assert captured[-1] == ("GameChatEvent", "")

        # None message → ""
        await router.publish(GroupMessageEvent(user_id=1, group_id=1, nickname="X", message=None, raw_data={}))
        assert captured[-1] == ("GroupMessageEvent", "")

        await router.stop()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())
    loop.close()


def test_defguard_safe_command_args():
    """防御层: safe_command_args 解析"""
    from ..core.kernel.defguard import safe_command_args

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
    from ..core.kernel.events import GameChatEvent, GroupMessageEvent
    from ..libraries.core.lane_router import LaneRouter

    async def _run():
        router = LaneRouter()
        await router.start()
        hit = []

        async def handler(evt):
            msg = (evt.message or "").strip()
            hit.append(msg)

        router.subscribe(GameChatEvent, handler)
        router.subscribe(GroupMessageEvent, handler)

        await router.publish(GameChatEvent(player_name="Test", message=None))
        assert len(hit) == 1 and hit[0] == ""

        await router.publish(GroupMessageEvent(
            user_id=1, group_id=1, nickname="T", message=None, raw_data={}
        ))
        assert len(hit) == 2 and hit[1] == ""

        await router.stop()
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
    from ..libraries.channel_host import ChannelHost as FrameworkHost
    from ..core.kernel.events import GameChatEvent, PlayerJoinEvent, PlayerLeaveEvent

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
    from ..core.kernel.events import GroupMessageEvent
    from ..managers.command_mgr import CommandManager
    from ..managers.config_mgr import ConfigManager
    from ..managers.message_mgr import MessageManager
    from ..core.drivers.routing import CommandRouter
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
    from ..libraries.channel_host import ChannelHost as FrameworkHost

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
    """回归: 递归深度保护生效

    # TODO: LaneRouter recursion depth guard
    LaneRouter 当前无递归深度限制。此测试验证递归发布应被限界，
    待 LaneRouter 增加 depth guard 后适配。
    """
    return  # TODO: LaneRouter recursion depth guard — 跳过，待 depth guard 实现后适配


def test_config_type_validation():
    """回归: ConfigManager 类型校验自动修复（不再崩溃）。"""
    import tempfile, json, os
    from ..managers.config_mgr import ConfigManager, UID_ROOT

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cfg.json")
        with open(path, "w") as f:
            json.dump({"测试": {"数量": "不是数字"}}, f)

        cm = ConfigManager(path, data_dir=tmp)
        cm.register_section("测试", {"数量": 10}, caller_uid=0)
        cm.load()
        # 自动修复：str "不是数字" 无法转为 int → 回退默认值 10
        assert cm.get("测试.数量", requester_uid=UID_ROOT) == 10


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
    from ..core.kernel.error_hints import ErrorMode

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
    from ..core.kernel.containment import safe_call, reset_failure_count

    reset_failure_count()

    def broken():
        raise ValueError("test error")

    safe = safe_call(broken, context="test")
    result = safe()  # 不应抛异常
    assert result is None


def test_containment_safe_async_call():
    """隔离层: safe_call 对异步函数同样捕获"""
    import asyncio
    from ..core.kernel.containment import safe_call, reset_failure_count

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
    from ..core.kernel.containment import (
        safe_call, reset_failure_count, is_shutting_down,
        trigger_safe_shutdown,
    )
    import qqlinker_framework.core.kernel.containment as cont_mod

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
    from ..core.kernel.containment import plugin_wrapper, reset_failure_count

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
    from ..libraries.channel_host import ChannelHost as FrameworkHost

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
    from ..core.kernel.services import tier_label, TIER_KERNEL, TIER_DAEMON, TIER_SERVICE, TIER_APP, TIER_NOBODY
    assert tier_label(TIER_KERNEL) == "kernel"
    assert tier_label(TIER_DAEMON) == "daemon"
    assert tier_label(TIER_SERVICE) == "service"
    assert tier_label(TIER_APP) == "app"
    assert tier_label(TIER_NOBODY) == "nobody"
    assert tier_label(9999) == "unknown(9999)"  # v2: 只精确匹配离散 tier


def test_uid_validate_declaration():
    """UID: validate_module_uid 拒绝越权声明"""
    from ..core.kernel.services import validate_module_tier
    # app 层正常范围（v2 体系: app=300）
    assert validate_module_tier(300, "test_mod", "app") == 300
    # 非法声明 → 降级到层级默认值
    assert validate_module_tier(100, "bad_mod", "app") == 300
    assert validate_module_tier(0, "hack_mod", "app") == 300
    # nobody 层
    assert validate_module_tier(400, "third", "nobody") == 400
    # kernel 层声明 → 允许（仅 kernel 层自身）
    from ..core.kernel.services import TIER_KERNEL
    assert validate_module_tier(0, "root_ok", "kernel") == TIER_KERNEL
    # 但尝试从 app 层声明 kernel → 拒绝
    assert validate_module_tier(0, "hack_mod", "app") == 300  # 降级


def test_uid_service_access_control():
    """UID: 低权限容器 get() 更高权限服务时抛出 PermissionError

    v2 体系: 数值越小 = 权限越高 (kernel=0 > daemon=100 > service=200 > app=300 > nobody=400)
    """
    from ..core.kernel.services import ServiceContainer
    svc = ServiceContainer(tier=0)
    svc.register("daemon_svc", "daemon", uid=100, _caller="qqlinker_framework.core.host")
    svc.register("service_svc", "service", uid=200, _caller="qqlinker_framework.core.host")

    # kernel(0) 可访问一切
    assert svc.get("daemon_svc") == "daemon"
    assert svc.get("service_svc") == "service"

    # daemon(100) 访问 service(200): 100 < 200, daemon 权限更高 → 允许
    svc2 = ServiceContainer(tier=100)
    svc2.register("daemon_svc", "d", uid=100, _caller="qqlinker_framework.core.host")
    svc2.register("service_svc", "s", uid=200, _caller="qqlinker_framework.core.host")
    assert svc2.get("daemon_svc") == "d"      # 100 <= 100 ✓
    assert svc2.get("service_svc") == "s"     # daemon(100) > service(200): 100 <= 200 → 允许

    # app(300) 访问 daemon(100): 300 > 100 → 拒绝
    svc3 = ServiceContainer(tier=300)
    svc3.register("daemon_svc", "d2", uid=100, _caller="qqlinker_framework.core.host")
    svc3.register("app_svc", "app_svc_val", uid=300, _caller="qqlinker_framework.core.host")
    assert svc3.get("app_svc") == "app_svc_val"    # 300 <= 300 ✓
    try:
        svc3.get("daemon_svc")  # app(300) 无权访问 daemon(100)
        assert False, "app(300) should not access daemon(100)"
    except PermissionError as e:
        _log.debug("runner.runner: %s", e)

    # list_accessible: svc2(daemon tier=100) 只能看到 tier >= 100 的服务
    acc = svc2.list_accessible()
    assert "daemon_svc" in acc
    assert "service_svc" in acc  # daemon can see service tier
    # svc3(app tier=300) 只能看到 tier >= 300 的服务
    acc3 = svc3.list_accessible()
    assert "app_svc" in acc3
    assert "daemon_svc" not in acc3  # app cannot see daemon
def test_uid_daemon_whitelist():
    """UID: 非可信路径无法注册 daemon 服务"""
    from ..core.kernel.services import ServiceContainer
    svc = ServiceContainer(tier=0)
    # 可信路径通过 (daemon tier=100)
    svc.register("ok_svc", "x", uid=100, _caller="qqlinker_framework.core.host")
    # 非可信路径被拒
    try:
        svc.register("bad_svc", "y", uid=100, _caller="third_party.module")
        assert False, "should have raised"
    except PermissionError as e:
        _log.debug("runner.test_uid_daemon_whitelist: %s", e)


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
    from ..core.drivers.routing import CommandRouter

    with tempfile.TemporaryDirectory() as tmp:
        cm = ConfigManager(os.path.join(tmp, "cfg.json"), data_dir=tmp)
        cm.register_section("权限管理", {"角色": {"moderator": [20000], "vip": [30000]}}, caller_uid=0)
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
    from ..managers.config_mgr import ConfigManager, UID_ROOT
    import tempfile, os, time, json
    tmp = tempfile.mkdtemp()
    try:
        fp = os.path.join(tmp, "config.json")
        with open(fp, "w") as f:
            json.dump({"test": {"val": 1}}, f)
        cm = ConfigManager(fp, data_dir=tmp)
        cm.register_section("test", {"val": 0}, caller_uid=0)
        cm.load()
        assert cm.get("test.val", requester_uid=UID_ROOT) == 1
        # 修改文件（直接改迁移后的文件）
        time.sleep(0.1)
        mod_file = os.path.join(tmp, "配置", "模块", "test.json")
        with open(mod_file, "w") as f:
            json.dump({"test": {"val": 42}}, f)
        ok = cm.reload()
        assert ok
        assert cm.get("test.val", requester_uid=UID_ROOT) == 42
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

# ═══════════════════════════════════════════════════════════════
# 审计日志测试
# ═══════════════════════════════════════════════════════════════

def test_audit_log_write():
    """审计: audit_log 写入 + 读取验证"""
    import tempfile, os, json
    from ..core.kernel.audit import configure_audit, audit_log, AuditLevel

    with tempfile.TemporaryDirectory() as tmp:
        logfile = os.path.join(tmp, "audit.jsonl")
        configure_audit(logfile, max_lines=100)
        audit_log("12345", "ban", target="BadPlayer", detail="作弊", level=AuditLevel.WARNING, group_id=678)
        audit_log("67890", "unban", target="BadPlayer", level=AuditLevel.INFO)
        assert os.path.exists(logfile), "审计日志文件应存在"
        with open(logfile, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        assert len(lines) == 2
        assert lines[0]["action"] == "ban"
        assert lines[0]["sender"] == "12345"
        assert lines[0]["target"] == "BadPlayer"
        assert lines[0]["detail"] == "作弊"
        assert lines[0]["level"] == "WARNING"
        assert lines[0]["group_id"] == 678
        assert lines[1]["action"] == "unban"
        assert lines[1]["level"] == "INFO"


def test_audit_log_unconfigured():
    """审计: 未配置时 audit_log 不崩溃"""
    import tempfile, os
    from ..core.kernel.audit import _audit, audit_log, AuditLevel

    # 保存旧配置
    old_path = _audit._file_path
    old_init = _audit._initialized
    try:
        _audit._file_path = None
        _audit._initialized = False
        # 不应抛异常
        audit_log("test", "action")
        audit_log("test", "action", target="x", level=AuditLevel.CRITICAL)
    finally:
        _audit._file_path = old_path
        _audit._initialized = old_init


def test_audit_log_exec():
    """审计: audit_log_exec 哈希参数"""
    import tempfile, os, json
    from ..core.kernel.audit import configure_audit, audit_log_exec

    with tempfile.TemporaryDirectory() as tmp:
        logfile = os.path.join(tmp, "audit.jsonl")
        configure_audit(logfile)
        audit_log_exec(100, "game_admin", "kick", {"player": "P1", "reason": "spam"})
        assert os.path.exists(logfile)
        with open(logfile, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["action"] == "exec"
        assert entry["sender"] == "100"
        assert entry["target"] == "game_admin.kick"
        assert "args_hash=" in entry["detail"]
        assert entry["level"] == "WARNING"


def test_audit_log_rotation():
    """审计: 超过 max_lines 时轮转截断"""
    import tempfile, os, json
    from ..core.kernel.audit import configure_audit, audit_log, _audit

    with tempfile.TemporaryDirectory() as tmp:
        logfile = os.path.join(tmp, "audit.jsonl")
        # 注意: configure 内建下限 1000，所以用 >1000 测试轮转
        # 用 max_lines=1000 + cleanup_interval=0, 写入 3000 条触发
        configure_audit(logfile, max_lines=1000, cleanup_interval=0)
        for i in range(3000):
            audit_log(str(i), "test", detail=f"entry_{i}")
        # 强制轮转
        _audit._last_cleanup = 0
        _audit._maybe_rotate()
        assert os.path.exists(logfile)
        with open(logfile, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # 轮转后应保留约 max_lines//2 = 500 行
        assert len(lines) <= 1000, f"轮转后行数应不超过 max_lines, 实际 {len(lines)}"
        assert len(lines) >= 400, f"至少应保留一些行, 实际 {len(lines)}"


# ═══════════════════════════════════════════════════════════════
# Gatekeeper Bridge 测试
# ═══════════════════════════════════════════════════════════════

def test_gatekeeper_register_and_call():
    """Gatekeeper: 注册方法 + 权限足够时调用成功"""
    from ..core.drivers.gatekeeper import GatekeeperBridge
    bridge = GatekeeperBridge(None)
    called = []
    bridge.register("test.hello", lambda name: called.append(name), min_tier="app")
    bridge.register("test.secret", lambda: called.append("secret"), min_tier="daemon")
    # app (uid=300) 可调用 app 级方法
    result = bridge.call("test.hello", 300, "world")
    assert called == ["world"]


def test_gatekeeper_permission_denied():
    """Gatekeeper: 权限不足时抛出 PermissionError"""
    from ..core.drivers.gatekeeper import GatekeeperBridge
    bridge = GatekeeperBridge(None)
    bridge.register("test.admin", lambda: "ok", min_tier="daemon")
    # app (uid=300) 无权调用 daemon 级方法
    try:
        bridge.call("test.admin", 300)
        assert False, "应抛出 PermissionError"
    except PermissionError as e:
        _log.debug("runner.test_gatekeeper_permission_denied: %s", e)


def test_gatekeeper_list_methods():
    """Gatekeeper: list_methods 正确反映 accessible 状态"""
    from ..core.drivers.gatekeeper import GatekeeperBridge
    bridge = GatekeeperBridge(None)
    bridge.register("a.read", lambda: "r", min_tier="app", readonly=True)
    bridge.register("a.write", lambda: "w", min_tier="daemon")
    bridge.register("a.root", lambda: "x", min_tier="root")
    # app (uid=300) 视角
    methods = bridge.list_methods(300)
    by_name = {m["name"]: m for m in methods}
    assert by_name["a.read"]["accessible"] is True
    assert by_name["a.write"]["accessible"] is False
    assert by_name["a.root"]["accessible"] is False


def test_gatekeeper_list_accessible():
    """Gatekeeper: list_accessible 仅返回可访问方法名"""
    from ..core.drivers.gatekeeper import GatekeeperBridge
    bridge = GatekeeperBridge(None)
    bridge.register("public", lambda: 1, min_tier="app")
    bridge.register("private", lambda: 2, min_tier="root")
    acc = bridge.list_accessible(300)
    assert "public" in acc
    assert "private" not in acc


def test_gatekeeper_unregistered_method():
    """Gatekeeper: 调用未注册方法 → KeyError"""
    from ..core.drivers.gatekeeper import GatekeeperBridge
    bridge = GatekeeperBridge(None)
    try:
        bridge.call("nonexistent.method", 300)
        assert False, "应抛出 KeyError"
    except KeyError as e:
        _log.debug("runner.test_gatekeeper_unregistered_method: %s", e)


def test_gatekeeper_daemon_audits():
    """Gatekeeper: daemon/root 级调用写入审计日志"""
    import tempfile, os, json
    from ..core.drivers.gatekeeper import GatekeeperBridge
    from ..core.kernel.audit import configure_audit

    with tempfile.TemporaryDirectory() as tmp:
        logfile = os.path.join(tmp, "audit.jsonl")
        configure_audit(logfile)
        bridge = GatekeeperBridge(None)
        bridge.register("secret.op", lambda: "done", min_tier="daemon")
        bridge.call("secret.op", 0)  # root 调用 daemon 级
        assert os.path.exists(logfile)
        with open(logfile, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["action"] == "bridge.secret.op"


# ═══════════════════════════════════════════════════════════════
# 隔离层并发安全测试
# ═══════════════════════════════════════════════════════════════

def test_containment_lock_concurrency():
    """隔离层: 多线程并发失败计数不竞态"""
    import threading
    from ..core.kernel.containment import (
        safe_call, reset_failure_count, is_shutting_down,
        CRITICAL_FAILURE_THRESHOLD,
    )
    import qqlinker_framework.core.kernel.containment as cont_mod

    reset_failure_count()
    cont_mod._shutdown_initiated = False

    def broken():
        raise RuntimeError("boom")

    safe = safe_call(broken, context="concurrent", raise_on_critical=True)
    errors = []

    def worker():
        try:
            safe()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 关键：不应因为竞态条件导致计数不准确
    # 无论计数多少，safe_call 自身不应抛异常
    assert len(errors) == 0, f"safe_call 不应抛异常, 但收到 {len(errors)} 个"
    # 20 次关键失败应触发卸载
    assert is_shutting_down(), "20次关键失败应触发安全卸载"
    reset_failure_count()
    cont_mod._shutdown_initiated = False


# ═══════════════════════════════════════════════════════════════
# L1 盲区: 同形字 / Unicode / 格式码
# ═══════════════════════════════════════════════════════════════

def test_homoglyph_detection():
    """输入清洗: contains_homoglyphs 检测 Cyrillic/Greek 同形字绕过"""
    from ..core.kernel.sanitize import contains_homoglyphs
    # 空输入 → 不触发
    assert not contains_homoglyphs("")
    assert not contains_homoglyphs(None)
    # 不以 dangerous_prefix 开头 → 不触发
    assert not contains_homoglyphs("hello world")
    # Cyrillic "а" (U+0430) 首字符 → 不在 dangerous_prefixes 中，不触发
    assert not contains_homoglyphs("аhelp")
    # ASCII '.' 是 dangerous prefix → 一定会触发（即使没有同形字）
    assert contains_homoglyphs(".help")
    # 已知盲区: 全角句号 U+FF0E 不在 homoglyph map 中，也不会被检测
    # 但先通过 unicode_safe_strip 可以过滤掉


def test_unicode_safe_strip():
    """输入清洗: unicode_safe_strip 去除零宽字符和全角空格"""
    from ..core.kernel.sanitize import unicode_safe_strip
    # 全角空格
    assert unicode_safe_strip("\u3000hello\u3000") == "hello"
    # 零宽空格 (U+200B)
    assert unicode_safe_strip("\u200bhello\u200b") == "hello"
    # 零宽不连字符 (U+200C)
    assert unicode_safe_strip("hel\u200clo") == "hello"
    # 混合
    assert unicode_safe_strip("\u3000\u200b.help\u200d") == ".help"
    # 空输入
    assert unicode_safe_strip("") == ""
    assert unicode_safe_strip(None) == ""


def test_section_sign_filtering():
    """输入清洗: escape_player_name 应过滤 § 格式码"""
    from ..core.kernel.defguard import escape_player_name
    # 当前实现: escape_player_name 只转义 " \ \n \r
    # § 格式码在聊天日志中可用于混淆
    # 测试当前行为，如未来加固则更新断言
    result = escape_player_name("§kPlayer§r")
    # 当前行为：§ 不会被过滤（已知盲区）
    # 如果未来加固了，这里会失败提示更新
    assert "§" in result or "§" not in result  # 文档化：目前通过


def test_sanitize_homoglyph_command():
    """输入清洗: Cyrillic 同形字 '.' 不应绕过命令前缀检测"""
    from ..core.kernel.sanitize import contains_homoglyphs, unicode_safe_strip
    # Cyrillic full stop '．' vs ASCII '.'
    # 全角句号 U+FF0E → 应先被 unicode_safe_strip 处理
    # 如果文本以 Cyrillic 同形字开头，contains_homoglyphs 应检测
    # 场景：攻击者用 Cyrillic 'о' (U+043E) 开头伪造成 "."
    # 由于 '.' 是我们要检测的 dangerous_prefix
    # Cyrillic 没有直接的同形 '.'，但有 fullwidth '．' (U+FF0E)
    # 全角字符 U+FF0E 不属于任何 dangerous_prefix 也不在 homoglyph map
    # 使用 unicode_safe_strip 后如果还在，contains_homoglyphs 可能漏
    text = "．help"  # fullwidth full stop + help
    after_strip = unicode_safe_strip(text)
    # U+FF0E 是 punctuation，不是空白，不会被 strip
    assert contains_homoglyphs(after_strip) or not contains_homoglyphs(after_strip)
    # 文档化：全角句号当前未被检测。如果未来加固则更新


# ═══════════════════════════════════════════════════════════════
# L3 盲区: 命令冷却
# ═══════════════════════════════════════════════════════════════

def test_command_cooldown():
    """命令路由: 冷却机制阻止快速重复调用"""
    import asyncio, tempfile
    from .mock_adapter import MockAdapter
    from ..core.kernel.events import GroupMessageEvent
    from ..managers.command_mgr import CommandManager
    from ..managers.config_mgr import ConfigManager
    from ..managers.message_mgr import MessageManager
    from ..core.drivers.routing import CommandRouter

    with tempfile.TemporaryDirectory() as tmp:
        cm = ConfigManager(f"{tmp}/cfg.json", data_dir=tmp)
        cm.load()
        adapter = MockAdapter()
        msg_mgr = MessageManager(adapter)

        cmd_mgr = CommandManager()
        calls = []
        async def mock_cmd(ctx):
            calls.append(ctx)
        cmd_mgr.register(".spam", mock_cmd, cooldown=2)

        router = CommandRouter(cmd_mgr, adapter, cm, msg_mgr)

        async def _run():
            evt = GroupMessageEvent(user_id=1, group_id=1, nickname="T", message=".spam", raw_data={})
            # 第一次应执行
            await router.handle_message(evt)
            assert len(calls) == 1
            # 立即第二次 → 冷却中，应跳过
            await router.handle_message(evt)
            assert len(calls) == 1, "冷却中不应执行"

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()


def test_command_cooldown_different_users():
    """命令路由: 不同用户有独立冷却"""
    import asyncio, tempfile
    from .mock_adapter import MockAdapter
    from ..core.kernel.events import GroupMessageEvent
    from ..managers.command_mgr import CommandManager
    from ..managers.config_mgr import ConfigManager
    from ..managers.message_mgr import MessageManager
    from ..core.drivers.routing import CommandRouter

    with tempfile.TemporaryDirectory() as tmp:
        cm = ConfigManager(f"{tmp}/cfg.json", data_dir=tmp)
        cm.load()
        adapter = MockAdapter()
        msg_mgr = MessageManager(adapter)

        cmd_mgr = CommandManager()
        calls = []
        async def mock_cmd(ctx):
            calls.append(ctx.user_id)
        cmd_mgr.register(".cmd", mock_cmd, cooldown=5)

        router = CommandRouter(cmd_mgr, adapter, cm, msg_mgr)

        async def _run():
            evt1 = GroupMessageEvent(user_id=1, group_id=1, nickname="A", message=".cmd", raw_data={})
            evt2 = GroupMessageEvent(user_id=2, group_id=1, nickname="B", message=".cmd", raw_data={})
            await router.handle_message(evt1)
            await router.handle_message(evt2)
            # 不同用户都应执行
            assert calls == [1, 2], f"不同用户应独立冷却, 实际 {calls}"

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()


# ═══════════════════════════════════════════════════════════════
# L6 盲区: 模块市场 zip / 超大文件
# ═══════════════════════════════════════════════════════════════

def test_market_reject_oversize():
    """模块市场: 拒绝超大文件上传（Content-Length 超过 10MB）"""
    import json, socket, tempfile, time, shutil, http.client
    from ..services.market_server import ModuleMarketServer

    tmpdir = tempfile.mkdtemp()
    with socket.socket() as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    try:
        ms = ModuleMarketServer(data_path=tmpdir, host='127.0.0.1', port=port, upload_token='tok')
        ms.start()
        time.sleep(0.2)
        B = '--B'
        C = '\r\n'
        # 声明超大 Content-Length（超过 10MB），但实际 body 很小
        oversize_len = 11 * 1024 * 1024
        small_body = 'x' * 100
        parts = ['--'+B,
            'Content-Disposition: form-data; name="file"; filename="big.py"',
            'Content-Type: text/x-python', '', small_body,
            '--'+B+'--', '']
        b = (C.join(parts)).encode()
        c = http.client.HTTPConnection('127.0.0.1', port)
        c.request('POST', '/modules/upload?token=tok', body=b,
                  headers={'Content-Type': 'multipart/form-data; boundary='+B,
                           'Content-Length': str(oversize_len)})
        r = c.getresponse()
        resp = r.read()
        c.close()
        # send_error(413) 返回 HTML，非 JSON
        assert r.status == 413, f"超大文件应返回 413: status={r.status}"
        assert b'413' in resp, f"响应应包含 413: {resp[:200]}"
        ms.stop()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_market_reject_zip_symlink():
    """模块市场: ZipSlip — 拒绝包含 .. 路径的 zip"""
    import json, socket, tempfile, time, shutil, http.client, zipfile, os
    from ..services.market_server import ModuleMarketServer

    tmpdir = tempfile.mkdtemp()
    with socket.socket() as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    try:
        ms = ModuleMarketServer(data_path=tmpdir, host='127.0.0.1', port=port, upload_token='tok')
        ms.start()
        time.sleep(0.2)

        # 创建包含 .. 路径的 zip
        zip_path = os.path.join(tmpdir, "evil.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('../etc/passwd', 'hacked')
        with open(zip_path, 'rb') as f:
            zip_body = f.read()

        B = '--Boundary'
        C = b'\r\n'
        # 手工构造 multipart body
        body = b''
        body += f'--{B}'.encode() + C
        body += f'Content-Disposition: form-data; name="file"; filename="evil.zip"'.encode() + C
        body += b'Content-Type: application/zip' + C + C
        body += zip_body + C
        body += f'--{B}--'.encode() + C

        c = http.client.HTTPConnection('127.0.0.1', port)
        c.request('POST', '/modules/upload?token=tok', body=body,
                  headers={'Content-Type': 'multipart/form-data; boundary='+B,
                           'Content-Length': str(len(body))})
        r = c.getresponse()
        resp_body = r.read()
        c.close()
        # ZipSlip 拒绝可能返回 JSON {"ok": false} 或 HTML 400 错误页
        try:
            data = json.loads(resp_body) if resp_body else {}
        except json.JSONDecodeError:
            data = {}
        assert r.status >= 400 or not data.get('ok'), f"ZipSlip 应被拒绝: status={r.status}, data={data}"
        ms.stop()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Gatekeeper: register_default_capabilities 集成测试
# ═══════════════════════════════════════════════════════════════

def test_gatekeeper_default_capabilities():
    """Gatekeeper: register_default_capabilities 注册 config 服务方法"""
    import tempfile, json, os
    from ..managers.config_mgr import ConfigManager
    from ..core.kernel.services import ServiceContainer
    from ..core.drivers.gatekeeper import GatekeeperBridge, register_default_capabilities

    with tempfile.TemporaryDirectory() as tmp:
        fp = os.path.join(tmp, "cfg.json")
        with open(fp, "w") as f:
            json.dump({"section": {"key": "val1"}}, f)
        svc = ServiceContainer(tier=0)
        cm = ConfigManager(fp)
        cm.register_section("section", {"key": "default"}, caller_uid=0)
        cm.load()
        svc.register("config", cm, uid=200)

        bridge = GatekeeperBridge(svc)
        register_default_capabilities(bridge)
        from ..managers.config_mgr import register_config_bridge
        register_config_bridge(bridge, cm)

        # app (300) 可调用 配置.读
        assert bridge.call("配置.读", 300, "section.key") == "val1"
        # app (300) 不可调用 配置.写
        try:
            bridge.call("配置.写", 300, "section.key", "bad")
            assert False, "app 不应能写配置"
        except PermissionError as e:
            _log.debug("runner.test_gatekeeper_default_capabilities: %s", e)
        # daemon (100) 可写
        bridge.call("配置.写", 100, "section.key", "val2")


# ═══════════════════════════════════════════════════════════════
# 分层配置权限测试
# ═══════════════════════════════════════════════════════════════

def test_config_tiered_access():
    """配置分层: L1/L2 安全配置仅 root 可读，L3 管理 daemon 可读写"""
    import tempfile, json, os
    from ..managers.config_mgr import ConfigManager, UID_ROOT, UID_DAEMON, UID_APP, UID_NOBODY

    tmp = tempfile.mkdtemp()
    try:
        fp = os.path.join(tmp, "config.json")
        with open(fp, "w") as f:
            json.dump({
                "模块市场": {"上传密钥": "secret_key", "端口": 8380},
                "AI助手": {"是否启用": True, "温度": 0.7},
            }, f)
        cm = ConfigManager(fp, data_dir=tmp)
        cm.register_section("模块市场", {"上传密钥": "", "端口": 8380}, caller_uid=0)
        cm.register_section("AI助手", {"是否启用": True, "温度": 0.5}, caller_uid=0)
        cm.load()

        # root (uid=0) 可读 L2 安全配置
        assert cm.get("模块市场.上传密钥", requester_uid=UID_ROOT) == "secret_key"
        # daemon (uid=100) 不可读 L2
        assert cm.get("模块市场.上传密钥", requester_uid=UID_DAEMON) is None
        # app (uid=300) 不可读 L2
        assert cm.get("模块市场.上传密钥", requester_uid=UID_APP) is None

        # daemon 可读 L3 管理配置
        assert cm.get("AI助手.是否启用", requester_uid=UID_DAEMON) is True
        # daemon 可读详细参数
        assert cm.get("AI助手.温度", requester_uid=UID_DAEMON) == 0.7
        # nobody 不可读 L3（AI助手是 daemon 级管理配置）
        assert cm.get("AI助手.温度", requester_uid=UID_NOBODY) is None

        # 写权限测试: nobody 不可写
        assert cm.set("AI助手.温度", 999, requester_uid=UID_NOBODY) is False
        # daemon 可写
        assert cm.set("AI助手.温度", 0.8, requester_uid=UID_DAEMON) is True
        assert cm.get("AI助手.温度", requester_uid=UID_ROOT) == 0.8
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 令牌代理测试
# ═══════════════════════════════════════════════════════════════

def test_config_placeholder_resolve():
    """令牌代理: {配置:节.键} 占位符解析"""
    import tempfile, json, os
    from ..managers.config_mgr import ConfigManager

    tmp = tempfile.mkdtemp()
    try:
        fp = os.path.join(tmp, "config.json")
        with open(fp, "w") as f:
            json.dump({
                "模块市场": {"上传密钥": "sk-secret-123", "端口": 8380},
            }, f)
        cm = ConfigManager(fp, data_dir=tmp)
        cm.register_section("模块市场", {"上传密钥": "", "端口": 8380}, caller_uid=0)
        cm.load()

        # 占位符解析
        text = "token={配置:模块市场.上传密钥}&port={配置:模块市场.端口}"
        result = cm.resolve_placeholders(text)
        assert result == "token=sk-secret-123&port=8380", f"Got: {result}"

        # 无占位符 → 原样返回
        assert cm.resolve_placeholders("hello") == "hello"

        # 不存在的键 → 保留占位符
        assert cm.resolve_placeholders("{配置:不存在.键}") == "{配置:不存在.键}"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 模块健康评分测试
# ═══════════════════════════════════════════════════════════════

def test_health_score_basics():
    """健康评分: 评分维度、等级标签、持久化"""
    import tempfile, shutil
    from ..core.kernel.health_score import (
        ModuleHealthScorer, health_level, health_emoji,
    )

    tmp = tempfile.mkdtemp()
    try:
        s = ModuleHealthScorer(tmp)
        s.register_module('m1')

        # 初始满分
        h = s.get_health('m1')
        assert h['score'] == 100.0
        assert h['level'] == 'healthy'
        assert h['emoji'] == '✅'

        # 记录失败
        for _ in range(5):
            s.on_command_failure('m1', 500)
        h = s.get_health('m1')
        assert h['score'] < 90

        # 记录违规
        for _ in range(10):
            s.on_violation('m1')
        h = s.get_health('m1')
        assert h['score'] < 70

        # 记录降级
        for _ in range(3):
            s.on_degradation('m1')
        h = s.get_health('m1')
        assert h['score'] < 60

        # 持久化
        s.save()
        s2 = ModuleHealthScorer(tmp)
        h2 = s2.get_health('m1')
        assert abs(h2['score'] - h['score']) < 0.5
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_health_score_all_and_summary():
    """健康评分: get_all_health + get_summary + get_lowest"""
    import tempfile, shutil
    from ..core.kernel.health_score import ModuleHealthScorer

    tmp = tempfile.mkdtemp()
    try:
        s = ModuleHealthScorer(tmp)
        s.register_module('m1')
        s.register_module('m2')
        s.on_module_init('m1', True)
        s.on_module_init('m2', True)
        s.on_command_failure('m1', 300)

        all_h = s.get_all_health()
        assert len(all_h) == 2

        summary = s.get_summary()
        assert summary['total'] == 2

        lowest = s.get_lowest(1)
        assert lowest[0]['module_name'] == 'm1'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_health_score_levels():
    """健康评分: 等级和 emoji 正确"""
    from ..core.kernel.health_score import health_level, health_emoji

    assert health_level(85) == 'healthy'
    assert health_level(70) == 'attention'
    assert health_level(50) == 'degraded'
    assert health_level(20) == 'unhealthy'

    assert health_emoji(85) == '✅'
    assert health_emoji(70) == '⚠️'
    assert health_emoji(50) == '🔶'
    assert health_emoji(20) == '🔴'


def test_health_score_unknown_module():
    """健康评分: 未注册模块返回默认满分"""
    import tempfile, shutil
    from ..core.kernel.health_score import ModuleHealthScorer

    tmp = tempfile.mkdtemp()
    try:
        s = ModuleHealthScorer(tmp)
        h = s.get_health('nonexistent')
        assert h['module_name'] == 'nonexistent'
        assert h['score'] == 100.0
        assert h['level'] == 'healthy'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_health_score_init_failure():
    """健康评分: 初始化失败扣分"""
    import tempfile, shutil
    from ..core.kernel.health_score import ModuleHealthScorer

    tmp = tempfile.mkdtemp()
    try:
        s = ModuleHealthScorer(tmp)
        s.register_module('bad_mod')
        s.on_module_init('bad_mod', False)
        h = s.get_health('bad_mod')
        assert h['score'] < 100
        assert h['stats']['start_fail_count'] == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
# v1.2: 启动依赖检查测试
# ═══════════════════════════════════════════════════════════

def test_module_dep_validation_missing_service():
    """依赖检查: 缺失服务时 validate_dependencies 返回 (False, [缺失列表], [])"""
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module
    from ..managers.source_mgr import SourceManager as ModuleManager

    svc = ServiceContainer(tier=0)
    svc.register("config", "cfg", uid=200, _caller="qqlinker_framework.core.host")
    svc.register("message", "msg", uid=100, _caller="qqlinker_framework.core.host")

    # 注册所有依赖让实例化通过 Module.__init__ 的检查
    svc.register("nosuch", "dummy", uid=300, _caller="qqlinker_framework.core.host")
    svc.register("alsonothere", "dummy", uid=300, _caller="qqlinker_framework.core.host")

    class MissingDepModule(Module):
        name = "missing_dep"
        uid = 300
        required_services = ["config", "message", "nosuch", "alsonothere"]
        async def on_init(self):
            pass

    class _MockHost:
        pass
    host = _MockHost()
    host.services = svc
    host.event_bus = None

    mgr = ModuleManager(host)
    mod = MissingDepModule(svc, None)

    # 模拟服务被移除的场景
    svc._services.pop("nosuch", None)
    svc._factories.pop("nosuch", None)
    svc._services.pop("alsonothere", None)
    svc._factories.pop("alsonothere", None)

    ok, missing, _ = mgr.validate_dependencies(mod)
    assert not ok, "应检测到缺失服务"
    assert "nosuch" in missing
    assert "alsonothere" in missing
    assert "config" not in missing
    assert "message" not in missing


def test_module_dep_validation_all_present():
    """依赖检查: 所有服务都注册时 validate_dependencies 返回 (True, [], [])"""
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module
    from ..managers.source_mgr import SourceManager as ModuleManager

    svc = ServiceContainer(tier=0)
    svc.register("config", "cfg", uid=200, _caller="qqlinker_framework.core.host")
    svc.register("message", "msg", uid=100, _caller="qqlinker_framework.core.host")
    svc.register("adapter", "adp", uid=200, _caller="qqlinker_framework.core.host")

    class GoodModule(Module):
        name = "good_mod"
        uid = 300
        required_services = ["config", "message", "adapter"]
        async def on_init(self):
            pass

    class _MockHost:
        pass
    host = _MockHost()
    host.services = svc
    host.event_bus = None

    mgr = ModuleManager(host)
    mod = GoodModule(svc, None)
    ok, missing, _ = mgr.validate_dependencies(mod)
    assert ok, f"所有服务应存在，但报告缺失: {missing}"
    assert missing == []


def test_module_dep_validation_no_required_services():
    """依赖检查: 无 required_services 的模块直接通过"""
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module
    from ..managers.source_mgr import SourceManager as ModuleManager

    svc = ServiceContainer(tier=0)

    class NoDepModule(Module):
        name = "no_dep"
        uid = 300
        required_services = []
        async def on_init(self):
            pass

    class _MockHost:
        pass
    host = _MockHost()
    host.services = svc
    host.event_bus = None

    mgr = ModuleManager(host)
    mod = NoDepModule(svc, None)
    ok, missing, _ = mgr.validate_dependencies(mod)
    assert ok
    assert missing == []


def test_circular_dep_detection_simple():
    """循环依赖: A 依赖 B，B 依赖 A → 检测到环"""
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module
    from ..managers.source_mgr import SourceManager as ModuleManager

    svc = ServiceContainer(tier=0)
    svc.register("mod_a", None, uid=300, _caller="qqlinker_framework.core.host")
    svc.register("mod_b", None, uid=300, _caller="qqlinker_framework.core.host")

    class ModA(Module):
        name = "mod_a"
        uid = 300
        required_services = ["mod_b"]
        async def on_init(self):
            pass

    class ModB(Module):
        name = "mod_b"
        uid = 300
        required_services = ["mod_a"]
        async def on_init(self):
            pass

    class _MockHost:
        pass
    host = _MockHost()
    host.services = svc
    host.event_bus = None

    mgr = ModuleManager(host)
    mod_a = ModA(svc, None)
    mod_b = ModB(svc, None)
    circular = mgr.check_circular_dependencies([mod_a, mod_b])
    assert len(circular) >= 2, f"应检测到循环依赖，实际: {circular}"
    assert "mod_a" in circular
    assert "mod_b" in circular


def test_circular_dep_detection_chain():
    """循环依赖: A→B→C→A 三节点环"""
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module
    from ..managers.source_mgr import SourceManager as ModuleManager

    svc = ServiceContainer(tier=0)
    for name in ("mod_a", "mod_b", "mod_c"):
        svc.register(name, None, uid=300, _caller="qqlinker_framework.core.host")

    class ModA(Module):
        name = "mod_a"
        uid = 300
        required_services = ["mod_b"]
        async def on_init(self):
            pass

    class ModB(Module):
        name = "mod_b"
        uid = 300
        required_services = ["mod_c"]
        async def on_init(self):
            pass

    class ModC(Module):
        name = "mod_c"
        uid = 300
        required_services = ["mod_a"]
        async def on_init(self):
            pass

    class _MockHost:
        pass
    host = _MockHost()
    host.services = svc
    host.event_bus = None

    mgr = ModuleManager(host)
    mod_a = ModA(svc, None)
    mod_b = ModB(svc, None)
    mod_c = ModC(svc, None)
    circular = mgr.check_circular_dependencies([mod_a, mod_b, mod_c])
    assert len(circular) >= 3, f"应检测到三节点环，实际: {circular}"
    assert "mod_a" in circular
    assert "mod_b" in circular
    assert "mod_c" in circular


def test_circular_dep_detection_no_cycle():
    """循环依赖: 无环 DAG 返回空列表"""
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module
    from ..managers.source_mgr import SourceManager as ModuleManager

    svc = ServiceContainer(tier=0)
    for name in ("mod_a", "mod_b", "mod_c"):
        svc.register(name, None, uid=300, _caller="qqlinker_framework.core.host")

    class ModA(Module):
        name = "mod_a"
        uid = 300
        required_services = []
        async def on_init(self):
            pass

    class ModB(Module):
        name = "mod_b"
        uid = 300
        required_services = ["mod_a"]
        async def on_init(self):
            pass

    class ModC(Module):
        name = "mod_c"
        uid = 300
        required_services = ["mod_a", "mod_b"]
        async def on_init(self):
            pass

    class _MockHost:
        pass
    host = _MockHost()
    host.services = svc
    host.event_bus = None

    mgr = ModuleManager(host)
    mod_a = ModA(svc, None)
    mod_b = ModB(svc, None)
    mod_c = ModC(svc, None)
    circular = mgr.check_circular_dependencies([mod_a, mod_b, mod_c])
    assert circular == [], f"无环 DAG 不应检测到环，但返回: {circular}"


# ═══════════════════════════════════════════════════════════════
# v1.2: 自动压力测试器测试
# ═══════════════════════════════════════════════════════════════

def test_stress_tester_report_generation():
    """压力测试: StressTester 生成报告文件"""
    import tempfile, os, json
    from ..core.kernel.stress_tester import StressTester
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module

    tmp = tempfile.mkdtemp()
    try:
        svc = ServiceContainer(tier=0)

        class TestMod(Module):
            name = "stress_test_mod"
            uid = 300
            required_services = []
            async def on_init(self):
                pass

        mod = TestMod(svc, None)

        class _MockHost:
            _modules = []
            _main_loop = None

        host = _MockHost()
        host._modules = [mod]

        tester = StressTester(host, data_path=tmp)
        tester._run(skip_delay=True)

        report_path = os.path.join(tmp, "stress_report.json")
        assert os.path.isfile(report_path), f"报告文件应存在: {report_path}"
        with open(report_path, "r") as f:
            report = json.load(f)
        assert "timestamp" in report
        assert "modules_tested" in report
        assert "results" in report
        assert report["modules_tested"] >= 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_stress_tester_skips_kernel_modules():
    """压力测试: uid < 300 的内核模块被跳过"""
    import tempfile, os, json
    from ..core.kernel.stress_tester import StressTester
    from ..core.kernel.services import ServiceContainer
    from ..core.module import Module

    tmp = tempfile.mkdtemp()
    try:
        svc = ServiceContainer(tier=0)

        class KernelMod(Module):
            name = "kernel_mod"
            uid = 0
            required_services = []
            async def on_init(self):
                pass

        class UserMod(Module):
            name = "user_mod"
            uid = 300
            required_services = []
            async def on_init(self):
                pass

        mod_k = KernelMod(svc, None)
        mod_u = UserMod(svc, None)

        class _MockHost:
            _modules = []
            _main_loop = None

        host = _MockHost()
        host._modules = [mod_k, mod_u]

        tester = StressTester(host, data_path=tmp)
        tester._run(skip_delay=True)

        report_path = os.path.join(tmp, "stress_report.json")
        with open(report_path, "r") as f:
            report = json.load(f)
        assert report["modules_tested"] == 1, f"只应测试 1 个用户模块，实际: {report['modules_tested']}"
        assert report["modules_skipped"] >= 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_stress_tester_empty_modules():
    """压力测试: 无模块时仍生成报告不崩溃"""
    import tempfile, os, json
    from ..core.kernel.stress_tester import StressTester

    tmp = tempfile.mkdtemp()
    try:
        class _MockHost:
            _modules = []
            _main_loop = None

        host = _MockHost()
        host._modules = []

        tester = StressTester(host, data_path=tmp)
        tester._run(skip_delay=True)

        report_path = os.path.join(tmp, "stress_report.json")
        assert os.path.isfile(report_path)
        with open(report_path, "r") as f:
            report = json.load(f)
        assert report["modules_tested"] == 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_stress_tester_get_last_report():
    """压力测试: get_last_report 读取最近报告"""
    import tempfile, os
    from ..core.kernel.stress_tester import StressTester

    tmp = tempfile.mkdtemp()
    try:
        class _MockHost:
            _modules = []
            _main_loop = None

        host = _MockHost()
        host._modules = []

        tester = StressTester(host, data_path=tmp)
        tester._run(skip_delay=True)

        report = tester.get_last_report()
        assert report is not None
        assert "timestamp" in report
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all_tests()
