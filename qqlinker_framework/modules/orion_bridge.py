# modules/orion_bridge.py
from ..core.module import Module
from ..core.decorators import command
from typing import Optional, Dict, Any

class OrionService:
    """安全服务接口，封装猎户座 API 调用"""
    def __init__(self, orion_api):
        self.api = orion_api

    def ban_player(self, player_name: str, reason: str = "管理员操作", duration: int = -1) -> Dict[str, Any]:
        """封禁玩家，duration=-1 表示永久"""
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        try:
            return self.api.ban_player(player_name, reason, duration)
        except Exception as e:
            return {"success": False, "message": str(e)}

    def unban_player(self, player_name: str) -> Dict[str, Any]:
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        try:
            return self.api.unban_player(player_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_ban_list(self) -> Dict[str, Any]:
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        try:
            return self.api.get_ban_list()
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_player_devices(self, player_name: str) -> Dict[str, Any]:
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        if not hasattr(self.api, 'get_player_devices'):
            return {"success": False, "message": "当前猎户座版本不支持设备查询"}
        try:
            return self.api.get_player_devices(player_name)
        except Exception as e:
            return {"success": False, "message": str(e)}


class OrionBridge(Module):
    name = "orion_bridge"
    version = (1, 0, 0)
    required_services = ["config", "adapter", "message"]

    async def on_init(self):
        # 尝试获取猎户座 API 实例
        orion_api = None
        try:
            orion_api = self.adapter.get_plugin_api("Orion_System")
        except Exception as e:
            pass

        if orion_api is None:
            self.orion_svc = None
            # 仍然注册命令（执行时返回不可用提示）
        else:
            self.orion_svc = OrionService(orion_api)
            # 将安全服务注册到容器，供其他模块使用
            self.services.register("orion", self.orion_svc)

        # 注册命令
        self.register_command(".ban", self.cmd_ban, description="封禁玩家 <玩家名> [原因] [时长(分钟,-1永久)]", op_only=True)
        self.register_command(".unban", self.cmd_unban, description="解除玩家封禁 <玩家名>", op_only=True)
        self.register_command(".device", self.cmd_device, description="查询玩家设备 <玩家名>", op_only=True)

    def _check_available(self, ctx) -> bool:
        if self.orion_svc is None:
            ctx.reply("猎户座反制系统未接入")
            return False
        return True

    @command(".ban", op_only=True)
    async def cmd_ban(self, ctx):
        if not self._check_available(ctx):
            return
        args = ctx.args
        if len(args) < 1:
            await ctx.reply("用法：.ban <玩家名> [原因] [时长(分钟)]")
            return
        player = args[0]
        reason = args[1] if len(args) > 1 else "管理员操作"
        duration = -1
        if len(args) > 2:
            try:
                duration = int(args[2]) * 60  # 转换为秒
                if duration == 0:
                    duration = -1
            except ValueError:
                duration = -1

        result = self.orion_svc.ban_player(player, reason, duration)
        if result.get("success"):
            await ctx.reply(f"封禁成功：{player}")
        else:
            await ctx.reply(f"封禁失败：{result.get('message', '未知错误')}")

    @command(".unban", op_only=True)
    async def cmd_unban(self, ctx):
        if not self._check_available(ctx):
            return
        if len(ctx.args) < 1:
            await ctx.reply("用法：.unban <玩家名>")
            return
        player = ctx.args[0]
        result = self.orion_svc.unban_player(player)
        if result.get("success"):
            await ctx.reply(f"解封成功：{player}")
        else:
            await ctx.reply(f"解封失败：{result.get('message', '未知错误')}")

    @command(".device", op_only=True)
    async def cmd_device(self, ctx):
        if not self._check_available(ctx):
            return
        if len(ctx.args) < 1:
            await ctx.reply("用法：.device <玩家名>")
            return
        player = ctx.args[0]
        result = self.orion_svc.get_player_devices(player)
        if result.get("success"):
            devices = result["data"].get("devices", [])
            if devices:
                await ctx.reply(f"玩家 {player} 关联的设备号：\n" + "\n".join(devices))
            else:
                await ctx.reply(f"{player} 无关联设备记录")
        else:
            await ctx.reply(f"查询失败：{result.get('message', '未知错误')}")