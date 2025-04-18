import requests
from typing import Any
from tooldelta import Plugin, fmts, plugin_entry
from tooldelta.plugin_market import market
from tooldelta.plugin_load.exceptions import (
    PluginAPINotFoundError,
    PluginAPIVersionError,
)


class NewPlugin(Plugin):
    name = "插件接口获取修复"
    author = "ToolDelta"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.old_get_plugin_api = self.frame.plugin_group.get_plugin_api
        self.inject()

    def plugin_api_not_found_auto_get(self, api_name: str) -> bool:
        resp = (
            input(fmts.fmt_info("尝试自动从市场下载插件吗 (§ay§r/§cn§r): "))
            .strip()
            .lower()
            or "y"
        )
        if resp == "y":
            try:
                plugin = market.get_plugin_data_from_market(api_name)
            except requests.RequestException:
                fmts.print_err("尝试失败")
                return False
            fmts.print_suc(f"找到 {plugin.name}, 开始下载..")
            market.download_plugin(plugin)
            fmts.print_suc("下载完成")
            return True
        else:
            return False

    def get_plugin_api(
        self, apiName: str, min_version: tuple[int, int, int] | None = None, force=True
    ) -> Any:
        try:
            return self.old_get_plugin_api(apiName, min_version, force)
        except (PluginAPIVersionError, PluginAPINotFoundError) as err:
            if isinstance(err, PluginAPINotFoundError):
                fmts.print_war(f"插件API {apiName} 未找到")
            else:
                fmts.print_war(f"插件API {apiName} 版本过低")
            res = self.plugin_api_not_found_auto_get(apiName)
            if not res:
                raise
            else:
                fmts.print_suc(f"已下载包含接口 {apiName} 的插件, 请重启 ToolDelta")
                raise SystemExit

    def inject(self):
        self.frame.plugin_group.get_plugin_api = self.get_plugin_api


entry = plugin_entry(NewPlugin)
