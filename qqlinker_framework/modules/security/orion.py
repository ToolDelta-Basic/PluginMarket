"""猎户座反制系统桥接模块。"""
from typing import Optional, Dict, Any
from ...core.module import Module
from ...core.decorators import command


class OrionService:
    """封装猎户座反制系统 API 调用。"""

    def __init__(self, orion_api):
        """初始化服务。

        Args:
            orion_api: 猎户座插件 API 对象。
        """
        self.api = orion_api

    def ban_player(
        self,
        player_name: str,
        reason: str = "管理员操作",
        duration: int = -1,
    ) -> Dict[str, Any]:
        """封禁玩家。

        Args:
            player_name: 玩家名。
            reason: 原因。
            duration: 秒，-1 为永久。

        Returns:
            结果字典。
        """
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        try:
            return self.api.ban_player(player_name, reason, duration)
        except Exception as e:
            return {"success": False, "message": str(e)}

    def unban_player(self, player_name: str) -> Dict[str, Any]:
        """解除玩家封禁。

        Args:
            player_name: 玩家名。

        Returns:
            结果字典。
        """
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        try:
            return self.api.unban_player(player_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_ban_list(self) -> Dict[str, Any]:
        """获取封禁列表。"""
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        try:
            return self.api.get_ban_list()
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_player_devices(self, player_name: str) -> Dict[str, Any]:
        """查询玩家关联的设备号。

        Args:
            player_name: 玩家名。

        Returns:
            结果字典。
        """
        if not self.api:
            return {"success": False, "message": "猎户座反制系统未接入"}
        if not hasattr(self.api, 'get_player_devices'):
            return {
                "success": False,
                "message": "当前猎户座版本不支持设备查询"
            }
        try:
            return self.api.get_player_devices(player_name)
        except Exception as e:
            return {"success": False, "message": str(e)}


class OrionBridge(Module):
    """提供 .封禁 / .解封 / .设备 命令，对接猎户座反制系统。"""

    name = "orion_bridge"
    version = (1, 0, 0)
    required_services = ["config", "adapter", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self.orion_svc = None  # 初始化属性

    async def on_init(self):
        async def _dbg_status(**kw):
            return str({"connected": self.orion_svc is not None})
        try:
            self.services.get("debug").register_module(self.name, {"status": _dbg_status})
        except KeyError:
            pass
        """尝试获取猎户座 API 并注册命令。"""
        orion_api = None
        try:
            orion_api = self.adapter.get_plugin_api("Orion_System")
        except Exception:
            pass

        if orion_api is None:
            self.orion_svc = None
        else:
            self.orion_svc = OrionService(orion_api)
            self.services.register("orion", self.orion_svc)

        self.register_command(
            ".封禁", self.cmd_ban,
            description="封禁玩家 <玩家名> [原因] [时长(分钟,-1永久)]",
            op_only=True
        )
        self.register_command(
            ".解封", self.cmd_unban,
            description="解除玩家封禁 <玩家名>",
            op_only=True
        )
        self.register_command(
            ".设备", self.cmd_device,
            description="查询玩家设备 <玩家名>",
            op_only=True
        )
        self.register_command(
            ".封禁列表", self.cmd_banlist,
            description="查看当前封禁列表",
            op_only=True
        )

    async def _check_available(self, ctx) -> bool:
        """检查猎户座服务是否可用，不可用时自动回复。

        Args:
            ctx: 命令上下文。

        Returns:
            是否可用。
        """
        if self.orion_svc is None:
            await ctx.reply("猎户座反制系统未接入")
            return False
        return True

    @command(".封禁", op_only=True)
    async def cmd_ban(self, ctx):
        """封禁玩家命令处理。"""
        if not await self._check_available(ctx):
            return
        args = ctx.args
        if len(args) < 1:
            await ctx.reply("用法：.封禁 <玩家名> [原因] [时长(分钟)]")
            return
        player = args[0]
        reason = args[1] if len(args) > 1 else "管理员操作"
        duration = -1
        if len(args) > 2:
            try:
                duration = int(args[2]) * 60
                if duration == 0:
                    duration = -1
            except ValueError:
                duration = -1

        result = self.orion_svc.ban_player(player, reason, duration)
        if result.get("success"):
            await ctx.reply(f"封禁成功：{player}")
        else:
            await ctx.reply(
                f"封禁失败：{result.get('message', '未知错误')}"
            )

    @command(".解封", op_only=True)
    async def cmd_unban(self, ctx):
        """解除封禁命令处理。"""
        if not await self._check_available(ctx):
            return
        if len(ctx.args) < 1:
            await ctx.reply("用法：.unban <玩家名>")
            return
        player = ctx.args[0]
        result = self.orion_svc.unban_player(player)
        if result.get("success"):
            await ctx.reply(f"解封成功：{player}")
        else:
            await ctx.reply(
                f"解封失败：{result.get('message', '未知错误')}"
            )

    @command(".设备", op_only=True)
    async def cmd_device(self, ctx):
        """查询玩家设备命令处理。"""
        if not await self._check_available(ctx):
            return
        if len(ctx.args) < 1:
            await ctx.reply("用法：.设备 <玩家名>")
            return
        player = ctx.args[0]
        result = self.orion_svc.get_player_devices(player)
        if result.get("success"):
            devices = result.get("data", {}).get("devices", [])
            if devices:
                await ctx.reply(
                    f"玩家 {player} 关联的设备号：\n"
                    + "\n".join(devices)
                )
            else:
                await ctx.reply(f"{player} 无关联设备记录")
        else:
            await ctx.reply(
                f"查询失败：{result.get('message', '未知错误')}"
            )

    @command(".封禁列表", op_only=True)
    async def cmd_banlist(self, ctx):
        """查看封禁列表命令处理。"""
        if not await self._check_available(ctx):
            return
        data = self.orion_svc.get_ban_list()
        bans = data.get("data", data) if isinstance(data, dict) else {}
        if isinstance(bans, list):
            if bans:
                lines = [f"封禁列表（共 {len(bans)} 条）："]
                for b in bans[:20]:
                    lines.append(
                        f"  · {b.get('name', b)} "
                        f"[{b.get('reason', '无原因')}]"
                    )
                await ctx.reply("\n".join(lines))
            else:
                await ctx.reply("封禁列表为空")
        else:
            await ctx.reply(f"查询失败：{bans.get('message', str(bans))}")
