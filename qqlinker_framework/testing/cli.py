# testing/cli.py
"""测试模式终端命令行 — 当插件不在 ToolDelta 环境中时自动启动。

支持命令:
  test                  运行全部测试
  mock                  启动 mock 模式交互
  send <玩家> <消息>    模拟游戏聊天
  join <玩家>           模拟玩家加入
  leave <玩家>          模拟玩家离开
  prejoin <玩家>        模拟玩家预加入
  cmd <QQ号> <群号> <命令> 模拟 QQ 群命令
  online <玩家1> <玩家2> ... 设置在线玩家列表
  status                查看 mock 状态
  active                模拟游戏连接就绪
  exit                  模拟框架退出
  help                  显示帮助
  quit                  退出
"""
import asyncio
import cmd
import logging
import threading
from typing import Optional

from .mock_adapter import MockAdapter
from ..core.host import FrameworkHost


class MockFrameworkCLI(cmd.Cmd):
    """测试模式交互命令行。"""

    intro = (
        "\n╔══════════════════════════════════════╗\n"
        "║   QQLinker Framework · 测试模式     ║\n"
        "║   输入 help 查看可用命令             ║\n"
        "╚══════════════════════════════════════╝\n"
    )
    prompt = "\n[测试] >>> "

    def __init__(self, data_dir: str = ".", start_framework: bool = True):
        super().__init__()
        self.adapter = MockAdapter()
        self.adapter.set_online(["TestPlayer1", "TestPlayer2"])
        self.adapter.set_admins([10000])

        self.host: Optional[FrameworkHost] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._data_dir = data_dir
        self._running = False

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

        if start_framework:
            self._start()

    # ── 框架生命周期 ──

    def _start(self):
        """启动 mock 框架。"""
        self.host = FrameworkHost(self.adapter, data_path=self._data_dir)
        self.host.register_modules_from_package("qqlinker_framework.modules")

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._running = True

    def _run_loop(self):
        """后台事件循环线程。"""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self.host.start())
            self._loop.run_forever()
        except Exception:
            logging.getLogger(__name__).exception("Mock 框架异常")

    def _stop(self):
        """优雅停止 mock 框架。"""
        if self.host and self._loop:
            asyncio.run_coroutine_threadsafe(self.host.stop(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._running = False

    # ── 命令 ──

    @staticmethod
    def do_test(arg: str):
        """运行所有测试。"""
        from .runner import run_all_tests
        run_all_tests()

    def do_mock(self, arg: str):
        """重启 mock 模式。"""
        if self._running:
            self._stop()
        self._start()
        print("✅ Mock 框架已重启")

    def do_send(self, arg: str):
        """模拟游戏聊天: send <玩家名> <消息>"""
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            print("用法: send <玩家名> <消息>")
            return
        player, msg = parts
        self.adapter.fire_game_chat(player, msg)
        print(f"📨 游戏聊天: <{player}> {msg}")

    def do_join(self, arg: str):
        """模拟玩家加入: join <玩家名>"""
        if not arg.strip():
            print("用法: join <玩家名>")
            return
        self.adapter.fire_player_join(arg.strip())
        print(f"🚪 玩家加入: {arg.strip()}")

    def do_leave(self, arg: str):
        """模拟玩家离开: leave <玩家名>"""
        if not arg.strip():
            print("用法: leave <玩家名>")
            return
        self.adapter.fire_player_leave(arg.strip())
        print(f"🚪 玩家离开: {arg.strip()}")

    def do_prejoin(self, arg: str):
        """模拟玩家预加入: prejoin <玩家名>"""
        if not arg.strip():
            print("用法: prejoin <玩家名>")
            return
        self.adapter.fire_player_pre_join(arg.strip())
        print(f"👤 玩家预加入: {arg.strip()}")

    def do_active(self, arg: str):
        """模拟游戏连接就绪。"""
        self.adapter.fire_active()
        print("✅ 游戏连接已就绪")

    def do_exit(self, arg: str):
        """模拟框架退出。"""
        self.adapter.fire_frame_exit({"signal": 0, "reason": "mock_exit"})
        print("🛑 框架退出信号已发送")

    def do_cmd(self, arg: str):
        """模拟QQ群命令: cmd <QQ号> <群号> <命令文本>"""
        parts = arg.split(maxsplit=2)
        if len(parts) < 3:
            print("用法: cmd <QQ号> <群号> <命令文本>")
            return
        try:
            user_id = int(parts[0])
            group_id = int(parts[1])
        except ValueError:
            print("QQ号和群号必须是整数")
            return
        msg = parts[2]

        raw = {
            "post_type": "message",
            "message_type": "group",
            "user_id": user_id,
            "group_id": group_id,
            "message_id": f"mock_{user_id}_{id(msg)}",
            "message": msg,
            "sender": {"nickname": f"User{user_id}", "card": f"Test{user_id}"},
        }
        self.adapter.trigger_raw_group_handlers(raw)
        print(f"💬 QQ命令: [{user_id}@{group_id}] {msg}")

    def do_online(self, arg: str):
        """设置在线玩家: online <玩家1> [玩家2] ..."""
        if not arg.strip():
            print("当前在线:", ", ".join(self.adapter.get_online_players()) or "(空)")
            return
        players = arg.split()
        self.adapter.set_online(players)
        print(f"👥 在线玩家: {', '.join(players)}")

    def do_status(self, arg: str):
        """查看 mock 状态。"""
        stats = self.adapter.get_stats()
        print(f"\n{'='*40}")
        print(f"  框架运行: {'✅ 是' if self._running else '❌ 否'}")
        print(f"  游戏就绪: {'✅ 是' if self.adapter.is_active else '❌ 否'}")
        print(f"  在线玩家: {', '.join(self.adapter.get_online_players()) or '(无)'}")
        print(f"  管理员QQ: {stats['admins']}")
        print(f"  发送指令数: {stats['command_count']}")
        print(f"  游戏消息数: {stats['game_msg_count']}")
        if self.host:
            loaded = self.host.module_mgr.get_loaded_modules()
            print(f"  已加载模块: {', '.join(loaded) if loaded else '(无)'}")
        print(f"{'='*40}")

    def do_help(self, arg: str):
        """显示帮助。"""
        print("\n可用命令：")
        print("  test                    运行全部测试")
        print("  mock                    重启 mock 框架")
        print("  send <玩家> <消息>      模拟游戏聊天")
        print("  join <玩家>             模拟玩家加入")
        print("  leave <玩家>            模拟玩家离开")
        print("  prejoin <玩家>          模拟玩家预加入")
        print("  cmd <QQ号> <群号> <命令> 模拟 QQ 群命令")
        print("  online [玩家1 玩家2...] 查看/设置在线玩家")
        print("  active                  模拟游戏连接就绪")
        print("  exit                    模拟框架退出")
        print("  status                  查看 mock 状态")
        print("  quit                    退出")

    def do_quit(self, arg: str):
        """退出测试模式。"""
        print("正在停止框架...")
        self._stop()
        print("再见 👋")
        return True

    do_q = do_quit
    do_EOF = do_quit


def start_mock_cli(data_dir: str = ".", start_framework: bool = True):
    """启动 mock 模式终端。"""
    cli = MockFrameworkCLI(data_dir=data_dir, start_framework=start_framework)
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        cli.do_quit("")


def backup_data(data_dir: str, output: str = None):
    """打包 data_dir 为 tar.gz 备份文件。

    Args:
        data_dir: 数据目录路径。
        output: 输出文件路径（默认 data_dir/../backup_<时间戳>.tar.gz）。
    """
    import tarfile
    import os as _os
    from datetime import datetime

    if not _os.path.isdir(data_dir):
        print(f"❌ 数据目录不存在: {data_dir}")
        return False
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = _os.path.join(_os.path.dirname(data_dir), f"backup_{ts}.tar.gz")
    try:
        with tarfile.open(output, "w:gz") as tar:
            tar.add(data_dir, arcname=_os.path.basename(data_dir))
        size_mb = _os.path.getsize(output) / 1024 / 1024
        print(f"✅ 备份完成: {output} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"❌ 备份失败: {e}")
        return False


def restore_data(backup_file: str, data_dir: str):
    """从 tar.gz 备份恢复数据目录。

    Args:
        backup_file: 备份文件路径。
        data_dir: 目标数据目录。
    """
    import tarfile
    import os as _os
    import shutil

    if not _os.path.isfile(backup_file):
        print(f"❌ 备份文件不存在: {backup_file}")
        return False
    try:
        # 先备份当前数据（安全起见）
        if _os.path.isdir(data_dir):
            old = data_dir + ".old"
            if _os.path.exists(old):
                shutil.rmtree(old)
            shutil.move(data_dir, old)
            print(f"📦 旧数据已移动到: {old}")
        with tarfile.open(backup_file, "r:gz") as tar:
            tar.extractall(path=_os.path.dirname(data_dir))
        print(f"✅ 恢复完成: {backup_file} → {data_dir}")
        return True
    except Exception as e:
        print(f"❌ 恢复失败: {e}")
        return False
